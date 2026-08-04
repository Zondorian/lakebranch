"""GUI API tests for Nessie branch management (list/create/merge/delete).

Exercises the FastAPI branch endpoints against a **fake** Nessie tree-API
client — no live Nessie server, so the suite stays Docker-free and CI-safe.
The ``sqlite_env``-based test verifies the branch APIs degrade gracefully
(400) on the SQLite catalog profile, which has no branches/tags.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from src.lakebranch.nessie import NessieClient, NessieConflictError, NessieNotFoundError

# Reuse the fake session helpers from the client unit tests.
from tests.test_nessie import REF_FEATURE, REF_MAIN, REF_TAG, FakeResponse, FakeSession


@pytest.fixture
def nessie_api_app():
    """A FastAPI app module configured for the (fake) Nessie catalog profile.

    Returns the app module so tests can install a fake Nessie client via
    ``app_module._nessie_client`` before exercising the endpoints.
    """
    import src.lakebranch.api.app as app_module

    yield app_module


@pytest.fixture
def nessie_client(nessie_api_app, monkeypatch):
    """Env configured for the Nessie profile (filesystem storage keeps config light)."""
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("CATALOG_PROFILE", "nessie")
    monkeypatch.setenv("FS_PATH", "./data/warehouse")
    monkeypatch.setenv("WAREHOUSE", "warehouse")
    monkeypatch.setenv("NESSIE_URI", "http://localhost:19120/iceberg/main")
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)

    app_module = nessie_api_app
    app_module._catalog = None
    app_module._reset_nessie_client_for_tests()

    def install(*responses) -> FakeSession:
        session = FakeSession(*responses)
        app_module._nessie_client = NessieClient(
            "http://localhost:19120/api/v2", session=session
        )
        return session

    with TestClient(app_module.app) as client:
        yield client, install


def test_branches_list(nessie_client):
    """GET /api/branches lists branches + tags and the current branch."""
    client, install = nessie_client
    install(FakeResponse(200, [REF_MAIN, REF_FEATURE, REF_TAG]))

    resp = client.get("/api/branches")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == "main"
    # The API strips the raw `type` field, returning {name, hash} entries
    # sorted by name (feature-x, main).
    assert body["branches"] == [
        {"name": "feature-x", "hash": "def456"},
        {"name": "main", "hash": "abc123"},
    ]
    assert body["tags"] == [{"name": "v1.0", "hash": "feed00"}]
    assert body["available"] == body["branches"] + body["tags"]


def test_branches_list_empty(nessie_client):
    """An empty repository still returns a structured, current-tagged response."""
    client, install = nessie_client
    install(FakeResponse(200, {"references": []}))

    resp = client.get("/api/branches")
    assert resp.status_code == 200
    body = resp.json()
    assert body["branches"] == []
    assert body["tags"] == []
    assert body["current"] == "main"


def test_branches_create(nessie_client):
    """POST /api/branches forks a branch from the current branch (201)."""
    client, install = nessie_client
    install(FakeResponse(201, {"name": "dev", "hash": "xyz"}))

    resp = client.post(
        "/api/branches",
        json={"name": "dev", "from_ref": "main"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "dev"
    assert body["hash"] == "xyz"
    assert body["from_ref"] == "main"


def test_branches_create_conflict_409(nessie_client):
    """A duplicate branch name maps to 409."""
    client, install = nessie_client
    install(FakeResponse(409, {"message": "branch already exists"}))

    resp = client.post("/api/branches", json={"name": "main", "from_ref": "main"})
    assert resp.status_code == 409
    assert "Branch creation failed" in resp.json()["detail"]


def test_branches_merge_ok(nessie_client):
    """POST /api/branches/merge merges source -> target."""
    client, install = nessie_client
    install(FakeResponse(200, {"targetBranch": {"name": "main", "hash": "new"}}))

    resp = client.post(
        "/api/branches/merge",
        json={"source": "dev", "target": "main"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["merged"] is True
    assert body["source"] == "dev"
    assert body["target"] == "main"


def test_branches_merge_conflict_409(nessie_client):
    """A merge conflict surfaces as 409 with a readable detail."""
    client, install = nessie_client
    install(
        lambda m, u, k: (_ for _ in ()).throw(
            NessieConflictError("merge conflict on table db.events")
        )
    )

    resp = client.post(
        "/api/branches/merge",
        json={"source": "dev", "target": "main"},
    )
    assert resp.status_code == 409
    assert "Merge failed" in resp.json()["detail"]


def test_branches_delete_ok(nessie_client):
    """DELETE /api/branches/{name} deletes a branch."""
    client, install = nessie_client
    install(FakeResponse(204))

    resp = client.delete("/api/branches/dev")
    assert resp.status_code == 200
    assert resp.json() == {"name": "dev", "deleted": True}


def test_branches_delete_missing_404(nessie_client):
    """Deleting a missing branch maps to 404."""
    client, install = nessie_client
    install(
        lambda m, u, k: (_ for _ in ()).throw(NessieNotFoundError("no such branch"))
    )

    resp = client.delete("/api/branches/nope")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_branches_unavailable_on_sqlite_profile(sqlite_env):
    """On the SQLite catalog profile the branch APIs degrade to 400."""
    import src.lakebranch.api.app as app_module

    app_module._catalog = None
    app_module._reset_nessie_client_for_tests()
    with TestClient(app_module.app) as client:
        resp = client.get("/api/branches")
    assert resp.status_code == 400
    assert "Nessie catalog" in resp.json()["detail"]