"""Tests for the shared catalog helper module (no Docker/Nessie needed)."""

from __future__ import annotations

import pytest

from src.lakebranch import catalog
from src.lakebranch.catalog import ensure_namespace, ensure_table, namespace_of


class _FakeCatalog:
    """A minimal fake PyIceberg catalog for testing the helpers."""

    def __init__(self) -> None:
        self.namespaces: set[str] = set()
        self.tables: dict[str, object] = {}
        self.created_namespaces: list[str] = []
        self.created_tables: list[str] = []

    def load_namespace_properties(self, namespace: str):
        if namespace not in self.namespaces:
            raise catalog.NoSuchNamespaceError(f"Namespace does not exist: {namespace}")
        return {}

    def create_namespace(self, namespace: str) -> None:
        if namespace in self.namespaces:
            raise catalog.NamespaceAlreadyExistsError(f"Namespace already exists: {namespace}")
        self.namespaces.add(namespace)
        self.created_namespaces.append(namespace)

    def load_table(self, table_name: str):
        if table_name not in self.tables:
            raise catalog.NoSuchTableError(f"Table does not exist: {table_name}")
        return self.tables[table_name]

    def create_table(self, table_name: str, schema):
        if table_name in self.tables:
            raise catalog.TableAlreadyExistsError(f"Table already exists: {table_name}")
        self.tables[table_name] = {"name": table_name, "schema": schema}
        self.created_tables.append(table_name)
        return self.tables[table_name]


@pytest.fixture
def fake_catalog():
    return _FakeCatalog()


def test_namespace_of_dotted_identifier():
    assert namespace_of("db.events") == "db"
    assert namespace_of("a.b.c") == "a.b"


def test_namespace_of_bare_identifier_uses_default():
    assert namespace_of("events") == "default"


def test_ensure_namespace_created_when_missing(fake_catalog):
    ensure_namespace(fake_catalog, "db")
    assert "db" in fake_catalog.namespaces
    assert fake_catalog.created_namespaces == ["db"]


def test_ensure_namespace_idempotent(fake_catalog):
    ensure_namespace(fake_catalog, "db")
    ensure_namespace(fake_catalog, "db")
    assert fake_catalog.created_namespaces == ["db"]


def test_ensure_namespace_race_safe(fake_catalog):
    """A concurrent create between check and create should not raise."""
    fake_catalog.namespaces.add("db")

    # create_namespace raises NamespaceAlreadyExistsError because the namespace
    # was added concurrently after load_namespace_properties failed.
    def _load(*_args, **_kwargs):
        raise catalog.NoSuchNamespaceError("missing")

    fake_catalog.load_namespace_properties = _load
    ensure_namespace(fake_catalog, "db")  # should not raise


def test_ensure_table_creates_when_missing(fake_catalog):
    schema = object()
    table = ensure_table(fake_catalog, "db.events", schema)
    assert table["name"] == "db.events"
    assert table["schema"] is schema
    # The namespace is auto-created too.
    assert "db" in fake_catalog.namespaces


def test_ensure_table_returns_existing(fake_catalog):
    existing = {"name": "db.events"}
    fake_catalog.tables["db.events"] = existing
    table = ensure_table(fake_catalog, "db.events", object())
    assert table is existing
    assert fake_catalog.created_tables == []


def test_ensure_table_race_safe(fake_catalog):
    """A concurrent create between check and create should return the winner."""
    schema = object()

    def _create(table_name, schema):
        raise catalog.TableAlreadyExistsError("concurrent create")

    fake_catalog.create_table = _create
    # Pre-create the namespace so ensure_namespace won't interfere.
    fake_catalog.namespaces.add("db")
    # Pre-populate the table so the post-race load succeeds.
    fake_catalog.tables["db.events"] = {"name": "db.events"}

    table = ensure_table(fake_catalog, "db.events", schema)
    assert table["name"] == "db.events"