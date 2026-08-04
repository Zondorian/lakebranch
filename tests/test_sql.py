"""Docker-free integration tests for the DuckDB SQL query engine.

Exercises ``src.lakebranch.sql.run_sql`` against the real PyIceberg SQLite
catalog + local filesystem warehouse — no Docker, no Nessie — covering:
sanitized view names, quoted dotted aliases, JOINs, GROUP BY aggregates,
LIMIT truncation, and error handling.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from src.lakebranch.catalog import ensure_namespace, ensure_table, init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.init_demo import EVENTS_SCHEMA, ORDERS_SCHEMA, USERS_SCHEMA
from src.lakebranch.sql import run_sql

pytest.importorskip("pyiceberg.catalog.sql")  # requires sql-sqlite extra


@pytest.fixture
def seeded_catalog(sqlite_env):
    """Create the demo users/orders/events tables and seed matching rows.

    Mirrors ``init_demo``'s multi-table shape (with real Iceberg snapshots)
    so SQL tests can exercise JOINs and GROUP BY across tables.
    """
    cfg = load_config()
    catalog = init_catalog(cfg)
    ensure_namespace(catalog, "db")

    users = ensure_table(catalog, "db.users", USERS_SCHEMA)
    users.append(
        pa.table(
            {
                "user_id": pa.array([1, 2, 3], type=pa.int64()),
                "email": pa.array(
                    ["ada@example.com", "grace@example.com", "alan@example.com"],
                    type=pa.string(),
                ),
                "created_at": pa.array(
                    ["2026-06-01T09:00:00Z", "2026-06-02T10:30:00Z", "2026-06-05T08:15:00Z"],
                    type=pa.string(),
                ),
            },
            schema=pa.schema(
                [
                    pa.field("user_id", pa.int64(), nullable=False),
                    pa.field("email", pa.string()),
                    pa.field("created_at", pa.string()),
                ]
            ),
        )
    )

    orders = ensure_table(catalog, "db.orders", ORDERS_SCHEMA)
    orders.append(
        pa.table(
            {
                "order_id": pa.array([101, 102, 103], type=pa.int64()),
                "user_id": pa.array([1, 2, 1], type=pa.int64()),
                "amount_usd": pa.array([49.99, 129.50, 19.99], type=pa.float64()),
                "ts": pa.array(
                    ["2026-07-01T10:00:00Z", "2026-07-01T11:00:00Z", "2026-07-03T09:30:00Z"],
                    type=pa.string(),
                ),
            },
            schema=pa.schema(
                [
                    pa.field("order_id", pa.int64(), nullable=False),
                    pa.field("user_id", pa.int64()),
                    pa.field("amount_usd", pa.float64()),
                    pa.field("ts", pa.string()),
                ]
            ),
        )
    )

    events = ensure_table(catalog, "db.events", EVENTS_SCHEMA)
    events.append(
        pa.table(
            {
                "event_id": pa.array([1, 2, 3], type=pa.int64()),
                "event_type": pa.array(["login", "purchase", "logout"], type=pa.string()),
                "timestamp": pa.array(
                    ["2026-07-31T10:00:00Z", "2026-07-31T10:05:00Z", "2026-07-31T10:10:00Z"],
                    type=pa.string(),
                ),
            },
            schema=pa.schema(
                [
                    pa.field("event_id", pa.int64(), nullable=False),
                    pa.field("event_type", pa.string()),
                    pa.field("timestamp", pa.string()),
                ]
            ),
        )
    )
    return catalog


def test_sql_returns_tables_mapping(seeded_catalog):
    """Every catalog table is exposed as a sanitized view name."""
    result = run_sql("SELECT * FROM db_events ORDER BY event_id")

    assert result["row_count"] == 3
    assert result["tables"] == {
        "db_events": "db.events",
        "db_orders": "db.orders",
        "db_users": "db.users",
    }
    assert result["columns"][0]["name"] == "event_id"
    assert [row["event_type"] for row in result["rows"]] == ["login", "purchase", "logout"]


def test_sql_quoted_dotted_alias(seeded_catalog):
    """The quoted, dotted Iceberg table name also works as a SQL alias."""
    result = run_sql('SELECT event_id, event_type FROM "db.events" ORDER BY event_id')
    assert result["row_count"] == 3
    assert [row["event_id"] for row in result["rows"]] == [1, 2, 3]


def test_sql_group_by_aggregate(seeded_catalog):
    """GROUP BY / COUNT aggregate over a single table."""
    result = run_sql(
        "SELECT event_type, COUNT(*) AS n FROM db_events GROUP BY 1 ORDER BY 1"
    )
    assert result["row_count"] == 3
    by_type = {row["event_type"]: row["n"] for row in result["rows"]}
    assert by_type == {"login": 1, "logout": 1, "purchase": 1}


def test_sql_join_across_tables(seeded_catalog):
    """Real SQL JOIN between users and orders tables."""
    result = run_sql(
        "SELECT u.email, COUNT(o.order_id) AS orders "
        "FROM db_users u LEFT JOIN db_orders o ON u.user_id = o.user_id "
        "GROUP BY u.email ORDER BY u.email"
    )
    assert result["row_count"] == 3
    by_email = {row["email"]: row["orders"] for row in result["rows"]}
    assert by_email == {
        "ada@example.com": 2,  # orders 101 + 103
        "alan@example.com": 0,  # no orders
        "grace@example.com": 1,  # order 102
    }


def test_sql_limit_truncates_rows(seeded_catalog):
    """The configured limit caps how many result rows are returned."""
    result = run_sql("SELECT * FROM db_events ORDER BY event_id", limit=2)
    assert result["row_count"] == 2
    assert [row["event_id"] for row in result["rows"]] == [1, 2]


def test_sql_empty_query_raises(seeded_catalog):
    with pytest.raises(ValueError, match="empty"):
        run_sql("   ")


def test_sql_unknown_table_raises(seeded_catalog):
    """A reference to a non-existent table surfaces a DuckDB catalog error."""
    import duckdb

    with pytest.raises(duckdb.Error):
        run_sql("SELECT * FROM missing_table")