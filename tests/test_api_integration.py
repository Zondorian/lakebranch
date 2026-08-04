"""Docker-free integration tests for the GUI API endpoints.

These exercise the real FastAPI app + PyIceberg SQLite catalog + local
filesystem warehouse end-to-end — no Docker, no Nessie — so the GUI's
signature features (time travel, snapshot diff, query runner, write support)
are covered in CI against real Iceberg snapshot history.

Requires the ``gui`` (fastapi) and ``dev`` (httpx for TestClient) extras.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pyiceberg.catalog.sql")  # requires sql-sqlite extra

from fastapi.testclient import TestClient


@pytest.fixture
def api_client(sqlite_env, tmp_run_db):
    """A FastAPI TestClient backed by the Docker-free SQLite catalog.

    ``sqlite_env`` points the catalog + warehouse at a temp directory and
    ``tmp_run_db`` redirects the GUI write-path run log to a temp DuckDB file,
    so no test ever touches the real ``.lakebranch/`` directory.
    """
    import src.lakebranch.api.app as app_module

    # The API caches its catalog in a module global; reset it so each test
    # builds a fresh catalog from the (patched) environment.
    app_module._catalog = None

    with TestClient(app_module.app) as client:
        yield client


@pytest.fixture
def events_snapshots(api_client):
    """Seed ``db.events`` with 2 rows, then append 1 more.

    Returns ``(client, first_snapshot_id, second_snapshot_id)`` so tests can
    time-travel between real Iceberg snapshots created by the write API.
    """
    client: TestClient = api_client

    first_snapshot = client.post(
        "/api/tables/db.events/rows",
        json={
            "mode": "append",
            "rows": [
                {"event_id": 1, "event_type": "login", "timestamp": "2026-07-31T10:00:00Z"},
                {"event_id": 2, "event_type": "purchase", "timestamp": "2026-07-31T10:05:00Z"},
            ],
        },
    ).json()["snapshot_id"]

    second_snapshot = client.post(
        "/api/tables/db.events/rows",
        json={
            "mode": "append",
            "rows": [
                {"event_id": 3, "event_type": "logout", "timestamp": "2026-07-31T10:10:00Z"},
            ],
        },
    ).json()["snapshot_id"]

    return client, first_snapshot, second_snapshot


def test_api_lists_seeded_table(events_snapshots):
    """The write API creates the table; it appears in the table list."""
    client, _, _ = events_snapshots
    resp = client.get("/api/tables")
    assert resp.status_code == 200
    body = resp.json()
    assert "db.events" in body["tables"]
    assert "db" in body["namespaces"]


def test_api_time_travel(events_snapshots):
    """Rows at a past snapshot differ from the current rows."""
    client, first_snapshot, _ = events_snapshots

    current = client.get("/api/tables/db.events/rows")
    assert current.status_code == 200
    assert current.json()["row_count"] == 3

    past = client.get(
        "/api/tables/db.events/rows",
        params={"snapshot_id": first_snapshot},
    )
    assert past.status_code == 200
    body = past.json()
    assert body["row_count"] == 2
    event_ids = {row["event_id"] for row in body["rows"]}
    assert event_ids == {1, 2}


def test_api_snapshot_diff(events_snapshots):
    """Diff between snapshots reports exactly the appended row."""
    client, first_snapshot, second_snapshot = events_snapshots

    resp = client.get(
        "/api/tables/db.events/diff",
        params={
            "from_snapshot_id": first_snapshot,
            "to_snapshot_id": second_snapshot,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["from_row_count"] == 2
    assert body["to_row_count"] == 3
    assert body["added_rows"] == [
        {"event_id": 3, "event_type": "logout", "timestamp": "2026-07-31T10:10:00Z"}
    ]
    assert body["removed_rows"] == []


def test_api_query_runner(events_snapshots):
    """The filter-based query runner scans Iceberg with a row filter."""
    client, _, _ = events_snapshots

    resp = client.post(
        "/api/query",
        json={"table": "db.events", "filter": "event_id > 1", "limit": 100},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_count"] == 2
    assert {row["event_id"] for row in body["rows"]} == {2, 3}