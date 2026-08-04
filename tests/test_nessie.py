"""Unit tests for the Nessie tree-API client (branches & tags).

These run against a fake ``requests.Session`` — no live Nessie server, so the
full suite stays Docker-free and CI-safe while still exercising the exact
request URLs, query params, payloads, and response/error parsing.
"""

from __future__ import annotations

import pytest
import requests

from src.lakebranch.nessie import (
    NessieClient,
    NessieConflictError,
    NessieError,
    NessieNotFoundError,
    current_branch,
    nessie_api_base,
)


class FakeResponse:
    """A minimal stand-in for ``requests.Response``."""

    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON body")
        return self._payload


class FakeSession:
    """Records the (method, url, kwargs) of every request and returns canned responses.

    ``responses`` is a list of ``FakeResponse`` (or callables) consumed in
    order; a dangling request fails loudly so tests notice unasserted traffic.
    """

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError(f"Unexpected request: {method} {url}")
        resp = self.responses.pop(0)
        if callable(resp):
            return resp(method, url, kwargs)
        return resp


REF_MAIN = {"type": "BRANCH", "name": "main", "hash": "abc123"}
REF_FEATURE = {"type": "BRANCH", "name": "feature-x", "hash": "def456"}
REF_TAG = {"type": "TAG", "name": "v1.0", "hash": "feed00"}


def client_for(*responses) -> tuple[NessieClient, FakeSession]:
    session = FakeSession(*responses)
    return NessieClient("http://localhost:19120/api/v2", session=session), session


# -----------------------------------------------------------------------------
# URL helpers
# -----------------------------------------------------------------------------
def test_nessie_api_base_derived_from_iceberg_uri():
    """``/iceberg/main`` is stripped to give ``/api/v2`` on the same host."""
    assert (
        nessie_api_base("http://localhost:19120/iceberg/main")
        == "http://localhost:19120/api/v2"
    )
    assert (
        nessie_api_base("http://localhost:19120/iceberg/main/")
        == "http://localhost:19120/api/v2"
    )


def test_nessie_api_base_plain_server_url():
    """A plain server URL (no Iceberg prefix) is left intact."""
    assert nessie_api_base("http://localhost:19120") == "http://localhost:19120/api/v2"


def test_current_branch_parsed_from_uri():
    assert current_branch("http://localhost:19120/iceberg/main") == "main"
    assert current_branch("http://localhost:19120/iceberg/feature-x") == "feature-x"
    assert current_branch("http://localhost:19120") == "main"


# -----------------------------------------------------------------------------
# list_references
# -----------------------------------------------------------------------------
def test_list_references_sends_option_all_and_parses_array():
    client, session = client_for(FakeResponse(200, [REF_MAIN, REF_FEATURE, REF_TAG]))
    refs = client.list_references()

    assert refs == [REF_MAIN, REF_FEATURE, REF_TAG]
    method, url, kwargs = session.calls[0]
    assert method == "GET"
    assert url == "http://localhost:19120/api/v2/trees"
    assert kwargs.get("params") == {"option": "ALL"}
    assert kwargs.get("timeout") == 10


def test_list_references_accepts_paginated_envelope():
    client, _ = client_for(
        FakeResponse(200, {"references": [REF_MAIN], "nextPageToken": "abc"})
    )
    assert client.list_references() == [REF_MAIN]


def test_list_references_empty_envelope():
    client, _ = client_for(FakeResponse(200, {"references": []}))
    assert client.list_references() == []


# -----------------------------------------------------------------------------
# create_branch
# -----------------------------------------------------------------------------
def test_create_branch_uses_from_ref_name_and_returns_201():
    client, session = client_for(FakeResponse(201, {"name": "dev", "hash": "xyz"}))
    created = client.create_branch("dev", from_ref="main")

    assert created == {"name": "dev", "hash": "xyz"}
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "http://localhost:19120/api/v2/trees/branch"
    assert kwargs.get("json") == {"name": "dev", "fromRefName": "main"}


def test_create_branch_from_hash_uses_from_hash():
    client, session = client_for(FakeResponse(201, {"name": "dev", "hash": "xyz"}))
    client.create_branch("dev", from_hash="abc123")

    _, _, kwargs = session.calls[0]
    assert kwargs.get("json") == {"name": "dev", "fromHash": "abc123"}


def test_create_branch_conflict_raises():
    client, _ = client_for(FakeResponse(409, {"message": "branch exists"}))
    with pytest.raises(NessieConflictError):
        client.create_branch("main")


# -----------------------------------------------------------------------------
# merge
# -----------------------------------------------------------------------------
def test_merge_posts_to_target_path():
    client, session = client_for(
        FakeResponse(200, {"targetBranch": {"name": "main", "hash": "newhash"}})
    )
    result = client.merge("feature-x", "main")

    assert result["targetBranch"]["hash"] == "newhash"
    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url == "http://localhost:19120/api/v2/trees/branch/main/.../merge"
    assert kwargs.get("json") == {
        "fromRefName": "feature-x",
        "keepIndividualCommits": False,
        "dryRun": False,
        "returnConflictAsResult": False,
    }


def test_merge_with_from_hash_and_keep_commits():
    client, session = client_for(FakeResponse(200, {}))
    client.merge("feature-x", "main", from_hash="abc", keep_individual_commits=True)

    _, _, kwargs = session.calls[0]
    assert kwargs.get("json")["fromHash"] == "abc"
    assert kwargs.get("json")["keepIndividualCommits"] is True


# -----------------------------------------------------------------------------
# delete_branch
# -----------------------------------------------------------------------------
def test_delete_branch_204_ok():
    client, session = client_for(FakeResponse(204))
    client.delete_branch("feature-x")  # no exception

    method, url, _ = session.calls[0]
    assert method == "DELETE"
    assert url == "http://localhost:19120/api/v2/trees/branch/feature-x"


def test_delete_missing_branch_raises_not_found():
    client, _ = client_for(FakeResponse(404))
    with pytest.raises(NessieNotFoundError):
        client.delete_branch("nope")


# -----------------------------------------------------------------------------
# Error mapping
# -----------------------------------------------------------------------------
def test_unexpected_status_raises_nessie_error():
    client, _ = client_for(FakeResponse(500, {"message": "boom"}))
    with pytest.raises(NessieError):
        client.list_references()


def test_network_error_wrapped():
    session = FakeSession()
    session.responses.append(
        lambda m, u, k: (_ for _ in ()).throw(requests.ConnectionError("refused"))
    )
    client = NessieClient("http://localhost:19120/api/v2", session=session)
    with pytest.raises(NessieError, match="refused"):
        client.list_references()