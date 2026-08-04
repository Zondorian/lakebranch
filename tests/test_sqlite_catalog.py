"""Docker-free integration tests for the SQLite catalog profile.

These exercise the real PyIceberg SQLite catalog + local filesystem storage
end-to-end (create namespace -> create table -> append -> scan), so the actual
Iceberg write/read path is covered in CI without Docker or Nessie.
"""

from __future__ import annotations

import os

import pyarrow as pa
import pytest

from src.lakebranch.catalog import ensure_namespace, ensure_table, init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.write_iceberg import EVENTS_SCHEMA

pytest.importorskip("pyiceberg.catalog.sql")  # requires sql-sqlite extra


@pytest.fixture
def lake_dir(tmp_path):
    """A scratch directory for the SQLite catalog DB + warehouse."""
    return tmp_path / "lake"


@pytest.fixture
def sqlite_env(lake_dir, monkeypatch):
    """Point the SQLite catalog + filesystem warehouse at a temp directory."""
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("CATALOG_PROFILE", "sqlite")
    monkeypatch.setenv("FS_PATH", str(lake_dir / "warehouse"))
    monkeypatch.setenv("WAREHOUSE", str(lake_dir / "warehouse"))
    catalog_uri = "sqlite:///" + str(lake_dir / "catalog.db").replace(os.sep, "/")
    monkeypatch.setenv("CATALOG_URI", catalog_uri)
    # load_config() calls load_dotenv() which reads the repo .env; neutralize.
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    return lake_dir


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