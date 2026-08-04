"""Load a small multi-table demo dataset (users, orders, events)."""

from __future__ import annotations

import sys

import pyarrow as pa
from dotenv import load_dotenv
from pyiceberg.io.pyarrow import schema_to_pyarrow
from pyiceberg.schema import Schema
from pyiceberg.types import DoubleType, LongType, NestedField, StringType

from src.lakebranch.catalog import ensure_namespace, ensure_table, init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.runs import log_run
from src.lakebranch.storage import get_provider

load_dotenv()

USERS_SCHEMA = Schema(
    NestedField(field_id=1, name="user_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="email", field_type=StringType(), required=False),
    NestedField(field_id=3, name="created_at", field_type=StringType(), required=False),
)
ORDERS_SCHEMA = Schema(
    NestedField(field_id=1, name="order_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="user_id", field_type=LongType(), required=False),
    NestedField(field_id=3, name="amount_usd", field_type=DoubleType(), required=False),
    NestedField(field_id=4, name="ts", field_type=StringType(), required=False),
)
EVENTS_SCHEMA = Schema(
    NestedField(field_id=1, name="event_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="event_type", field_type=StringType(), required=False),
    NestedField(field_id=3, name="timestamp", field_type=StringType(), required=False),
)

USERS_DATA = [
    {"user_id": 1, "email": "ada@example.com", "created_at": "2026-06-01T09:00:00Z"},
    {"user_id": 2, "email": "grace@example.com", "created_at": "2026-06-02T10:30:00Z"},
    {"user_id": 3, "email": "alan@example.com", "created_at": "2026-06-05T08:15:00Z"},
    {"user_id": 4, "email": "linus@example.com", "created_at": "2026-06-07T14:00:00Z"},
    {"user_id": 5, "email": "margaret@example.com", "created_at": "2026-06-10T11:45:00Z"},
]
ORDERS_DATA = [
    {"order_id": 101, "user_id": 1, "amount_usd": 49.99, "ts": "2026-07-01T10:00:00Z"},
    {"order_id": 102, "user_id": 2, "amount_usd": 129.50, "ts": "2026-07-01T11:00:00Z"},
    {"order_id": 103, "user_id": 1, "amount_usd": 19.99, "ts": "2026-07-03T09:30:00Z"},
    {"order_id": 104, "user_id": 3, "amount_usd": 299.00, "ts": "2026-07-05T16:20:00Z"},
    {"order_id": 105, "user_id": 5, "amount_usd": 9.99, "ts": "2026-07-08T12:10:00Z"},
    {"order_id": 106, "user_id": 2, "amount_usd": 84.25, "ts": "2026-07-12T18:40:00Z"},
]
EVENTS_DATA = [
    {"event_id": 1, "event_type": "login", "timestamp": "2026-07-31T10:00:00Z"},
    {"event_id": 2, "event_type": "purchase", "timestamp": "2026-07-31T10:05:00Z"},
    {"event_id": 3, "event_type": "logout", "timestamp": "2026-07-31T10:10:00Z"},
]


def append_rows(table, rows, required_col):
    """Append dict rows using the Iceberg table's schema for exact type/nullability match."""
    arrow_table = pa.Table.from_pylist(
        rows,
        schema=schema_to_pyarrow(table.schema()),
    )
    table.append(arrow_table)
    print(f"[iceberg] Appended {arrow_table.num_rows} rows to table.")


def main() -> None:
    config = load_config()
    with log_run(
        pipeline="init_demo",
        profile=config["storage_profile"],
        warehouse=config["warehouse"],
    ) as run:
        get_provider(config).ensure_warehouse()
        catalog = init_catalog(config)
        ensure_namespace(catalog, "db")

        users = ensure_table(catalog, "db.users", USERS_SCHEMA)
        append_rows(users, USERS_DATA, "user_id")

        orders = ensure_table(catalog, "db.orders", ORDERS_SCHEMA)
        append_rows(orders, ORDERS_DATA, "order_id")

        events = ensure_table(catalog, "db.events", EVENTS_SCHEMA)
        append_rows(events, EVENTS_DATA, "event_id")

        run.rows_written = len(USERS_DATA) + len(ORDERS_DATA) + len(EVENTS_DATA)

    print("[done] Demo dataset loaded. UI: http://localhost:8787/ui/")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)