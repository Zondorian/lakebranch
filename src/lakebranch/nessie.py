"""
Lakebranch — Nessie Tree API Client (Branches & Tags)
====================================================

Thin client for Nessie's REST **v2** tree API — the "Git-like versioning of
table metadata" layer. It lists branches/tags, creates branches, merges one
branch into another, and deletes branches. This is what powers the GUI's
**Branches** panel and delivers the *"undo/redo for data"* story: create a
branch before destructive writes, then merge it back.

Why this module is separate from PyIceberg:

- PyIceberg's ``RestCatalog`` (what ``load_catalog("nessie", ...)`` returns)
  talks only to the **Iceberg REST** endpoint (``.../iceberg/{ref}``) and has
  **no branch/tree APIs**.
- This client talks to Nessie's **tree API** (``/api/v2/trees``) on the same
  server, which is what actually manages branches, tags, and commits.

Targets Nessie 0.104.x (the version pinned in ``docker/docker-compose.yml``).
The client is dependency-light (``requests``, already a transitive dependency
of the stack) and accepts an injectable ``requests.Session`` so tests can run
against a fake session with no live Nessie server.
"""

from __future__ import annotations

import json as _json
from typing import Any
from urllib.parse import quote, urlsplit

import requests

DEFAULT_TIMEOUT = 10


class NessieError(Exception):
    """Raised when Nessie returns an unexpected status, or the request fails."""


class NessieNotFoundError(NessieError):
    """Raised when the referenced branch/tag (or server path) does not exist."""


class NessieConflictError(NessieError):
    """Raised when a create/merge conflicts with the catalog's current state."""


def nessie_api_base(nessie_uri: str) -> str:
    """Derive the Nessie REST v2 tree-API base from an Iceberg REST URI.

    ``NESSIE_URI`` points at the Iceberg REST endpoint on the Nessie server
    (e.g. ``http://localhost:19120/iceberg/main``). The tree API lives on the
    same server under ``/api/v2``, so the ``/iceberg`` prefix is stripped:
    ``http://localhost:19120/iceberg/main`` -> ``http://localhost:19120/api/v2``.

    A plain server URL (no ``/iceberg`` path) is left intact, so the helper is
    robust for both of Nessie's URL conventions.
    """
    parsed = urlsplit(nessie_uri)
    path = parsed.path
    idx = path.find("/iceberg")
    if idx != -1:
        path = path[:idx]
    root = parsed._replace(path=path.rstrip("/") or "/").geturl().rstrip("/")
    return f"{root}/api/v2"


def current_branch(nessie_uri: str) -> str:
    """Return the branch name encoded in a Nessie Iceberg REST URI.

    ``http://localhost:19120/iceberg/main`` -> ``"main"``. Falls back to
    ``"main"`` when the URI carries no ``/iceberg/{ref}`` suffix.
    """
    path = urlsplit(nessie_uri).path
    marker = "/iceberg/"
    if marker in path:
        ref = path.split(marker, 1)[1].rstrip("/")
        if ref:
            return ref
    return "main"


def _body(resp: requests.Response) -> str:
    """Best-effort human-readable body for error messages."""
    try:
        data = resp.json()
        if isinstance(data, dict) and "message" in data:
            return str(data["message"])
        return _json.dumps(data)[:300]
    except Exception:  # noqa: BLE001 — best-effort error message extraction
        return (resp.text or "")[:300]


def _quote_path(ref_name: str) -> str:
    """Percent-encode a reference name for a URL path, preserving '/' segments.

    Top-level branches have no slashes (``quote(seg, safe="")`` handles them),
    while namespaced/merged refs under a path keep their ``/`` structure.
    """
    return "/".join(quote(seg, safe="") for seg in ref_name.split("/"))


class NessieClient:
    """Minimal Nessie REST v2 tree-API client (branches & tags).

    Args:
        base_url: The tree-API base — typically ``nessie_api_base(NESSIE_URI)``
            (``http://host:19120/api/v2``).
        session: Optional ``requests.Session`` (or a test double) to use for
            HTTP calls. Defaults to a fresh ``requests.Session()``.
    """

    def __init__(self, base_url: str, session: requests.Session | None = None):
        self.base_url = base_url.rstrip("/")
        self._session = session if session is not None else requests.Session()

    # ------------------------------------------------------------------
    # Low-level request helper
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        expected: int = 200,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.request(
                method, url, params=params, json=json_body, timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise NessieError(f"Nessie request failed: {exc}") from exc

        if resp.status_code == 404:
            raise NessieNotFoundError(f"Nessie 404: {method} {url}")
        if resp.status_code == 409:
            raise NessieConflictError(f"Nessie 409: {method} {url}: {_body(resp)}")
        if resp.status_code != expected:
            raise NessieError(
                f"Nessie {resp.status_code} for {method} {url}: {_body(resp)}"
            )
        return resp

    # ------------------------------------------------------------------
    # References (branches & tags)
    # ------------------------------------------------------------------
    def list_references(self) -> list[dict[str, Any]]:
        """List every branch and tag in the repository.

        Returns the reference objects (``type``, ``name``, ``hash``,
        ``metadata``). Both the plain-array and the paginated-envelope
        response shapes are accepted.
        """
        resp = self._request("GET", "/trees", params={"option": "ALL"})
        data = resp.json()
        if isinstance(data, list):
            return data
        # Paginated v2 envelope: {"references": [...], "nextPageToken": ...}
        return data.get("references") or data.get("branches") or []

    def create_branch(
        self,
        name: str,
        from_ref: str = "main",
        from_hash: str | None = None,
    ) -> dict[str, Any]:
        """Create a new branch forked from an existing branch/tag.

        Args:
            name: The new branch name.
            from_ref: Source branch/tag to fork from (used when ``from_hash``
                is omitted).
            from_hash: Optional source hash — forks the exact commit instead
                of the tip of ``from_ref``.
        """
        body: dict[str, Any] = {"name": name}
        if from_hash:
            body["fromHash"] = from_hash
        else:
            body["fromRefName"] = from_ref
        resp = self._request("POST", "/trees/branch", json_body=body, expected=201)
        data = resp.json()
        return data if isinstance(data, dict) else {"name": name}

    def merge(
        self,
        source: str,
        target: str = "main",
        *,
        from_hash: str | None = None,
        keep_individual_commits: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Merge a source branch into a target branch.

        Args:
            source: Branch to merge FROM.
            target: Branch to merge INTO.
            from_hash: Optional source hash to merge (defaults to the tip).
            keep_individual_commits: Keep the source's commits in the target
                (``False`` squashes them).
            dry_run: Validate without applying the merge.

        Returns the raw ``MergeResponse`` (target branch, conflicts, ...).
        """
        body: dict[str, Any] = {
            "fromRefName": source,
            "keepIndividualCommits": keep_individual_commits,
            "dryRun": dry_run,
            "returnConflictAsResult": False,
        }
        if from_hash:
            body["fromHash"] = from_hash
        target_path = _quote_path(target)
        resp = self._request(
            "POST", f"/trees/branch/{target_path}/.../merge", json_body=body
        )
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def delete_branch(self, name: str) -> None:
        """Delete a branch by name (204 on success; 404 if it does not exist)."""
        self._request(
            "DELETE", f"/trees/branch/{_quote_path(name)}", expected=204
        )