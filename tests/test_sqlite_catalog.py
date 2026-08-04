"""Docker-free integration tests for the SQLite catalog profile.

These exercise the real PyIceberg SQLite catalog + local filesystem storage
end-to-end (create namespace -> create table -> append -> scan), so the actual
Iceberg write/read path is covered in CI without Docker or Nessie.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from src.lakebranch.catalog import ensure_namespace, ensure_table, init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.write_iceberg import EVENTS_SCHEMA

pytest.importorskip("pyiceberg.catalog.sql")  # requires sql-sqlite extra


def test_sqlite_profile_loads_config(sqlite_env):
    cfg = load_config()
    assert cfg["catalog_profile"] == "sqlite"
    assert cfg["storage_profile"] == "filesystem"
    assert cfg["fs_path"].endswith("warehouse")
    assert cfg["warehouse"].endswith("warehouse")


def test_sqlite_catalog_end_to_end(sqlite_env):
    """Create namespace -> create table -> append -> scan, all Docker-free."""
    cfg = load_config()
    catalog = init_catalog(cfg)

    ensure_namespace(catalog, "db")
    table = ensure_table(catalog, "db.events", EVENTS_SCHEMA)

    assert catalog.list_namespaces() == [("db",)]
    assert catalog.list_tables("db") == [("db", "events")]

    table.append(
        pa.table(
            {
                "event_id": pa.array([1, 2], type=pa.int64()),
                "event_type": pa.array(["login", "purchase"], type=pa.string()),
                "timestamp": pa.array(
                    ["2026-07-31T10:00:00Z", "2026-07-31T10:05:00Z"],
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

    result = table.scan().to_arrow()
    assert result.num_rows == 2
    assert set(result.column("event_type").to_pylist()) == {"login", "purchase"}


def test_sqlite_catalog_idempotent(sqlite_env):
    """Re-running ensure_table on the same catalog/warehouse reuses the table."""
    from src.lakebranch.catalog import ensure_table as ensure_table_helper

    cfg = load_config()
    catalog = init_catalog(cfg)
    ensure_namespace(catalog, "db")

    t1 = ensure_table_helper(catalog, "db.events", EVENTS_SCHEMA)
    t2 = ensure_table_helper(catalog, "db.events", EVENTS_SCHEMA)

    # Same catalog instance -> same table; no duplicate table created.
    assert t1.name() == t2.name() == ("db", "events")
    assert len(catalog.list_tables("db")) == 1


def test_sqlite_catalog_uses_filesystem_warehouse(sqlite_env, tmp_path):
    """The catalog metadata lands inside FS_PATH when storage is filesystem."""
    cfg = load_config()
    catalog = init_catalog(cfg)
    ensure_namespace(catalog, "db")
    ensure_table(catalog, "db.events", EVENTS_SCHEMA)

    # Metadata + data files must live under the filesystem warehouse dir.
    warehouse = tmp_path / "lake" / "warehouse"
    assert (warehouse / "db").is_dir()
    assert (warehouse / "db" / "events").is_dir()
    # A metadata JSON (00000-*.metadata.json) should exist after table creation.
    metadata_dir = warehouse / "db" / "events" / "metadata"
    assert metadata_dir.is_dir()
    assert any(metadata_dir.glob("*.metadata.json"))


# -----------------------------------------------------------------------------
# Time travel & snapshot diffs (Docker-free — real Iceberg snapshot history)
# -----------------------------------------------------------------------------
def _append_rows(table, rows):
    """Append a small arrow table of events rows to an Iceberg table."""
    event_ids = [r[0] for r in rows]
    event_types = [r[1] for r in rows]
    timestamps = [r[2] for r in rows]
    table.append(
        pa.table(
            {
                "event_id": pa.array(event_ids, type=pa.int64()),
                "event_type": pa.array(event_types, type=pa.string()),
                "timestamp": pa.array(timestamps, type=pa.string()),
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


def _snapshot_ids(table):
    """Return the table's snapshot IDs in chronological order."""
    snaps = table.metadata.snapshots
    assert snaps is not None
    ordered = sorted(snaps, key=lambda s: s.timestamp_ms)
    return [s.snapshot_id for s in ordered]


def _scan_rows(table, snapshot_id=None):
    """Scan the table (optionally at a snapshot) and return set of (event_id, event_type)."""
    if snapshot_id is not None:
        arrow = table.scan(snapshot_id=snapshot_id).to_arrow()
    else:
        arrow = table.scan().to_arrow()
    return set(zip(arrow.column("event_id").to_pylist(), arrow.column("event_type").to_pylist()))


def test_sqlite_catalog_time_travel(sqlite_env):
    """Scanning at a past snapshot returns the table as it was then."""
    cfg = load_config()
    catalog = init_catalog(cfg)
    ensure_namespace(catalog, "db")
    table = ensure_table(catalog, "db.events", EVENTS_SCHEMA)

    _append_rows(table, [(1, "login", "2026-07-31T10:00:00Z")])
    first_snapshot = table.metadata.current_snapshot_id
    _append_rows(table, [(2, "purchase", "2026-07-31T10:05:00Z")])
    _append_rows(table, [(3, "logout", "2026-07-31T10:10:00Z")])

    assert _scan_rows(table) == {(1, "login"), (2, "purchase"), (3, "logout")}
    assert _scan_rows(table, snapshot_id=first_snapshot) == {(1, "login")}


def test_sqlite_catalog_snapshot_diff(sqlite_env):
    """The current table minus an older snapshot equals the later-appended rows."""
    cfg = load_config()
    catalog = init_catalog(cfg)
    ensure_namespace(catalog, "db")
    table = ensure_table(catalog, "db.events", EVENTS_SCHEMA)

    _append_rows(table, [(1, "login", "2026-07-31T10:00:00Z"), (2, "purchase", "2026-07-31T10:05:00Z")])
    first_snapshot = table.metadata.current_snapshot_id
    _append_rows(table, [(3, "logout", "2026-07-31T10:10:00Z")])

    ids = _snapshot_ids(table)
    assert ids[0] == first_snapshot

    set_from = _scan_rows(table, snapshot_id=ids[0])
    set_to = _scan_rows(table, snapshot_id=ids[-1])
    assert set_to - set_from == {(3, "logout")}
    assert set_from - set_to == set()
