"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def tmp_run_db(tmp_path, monkeypatch):
    """Point the run-log DB at a temp file so tests never touch .lakebranch/."""
    from src.lakebranch import runs

    monkeypatch.setattr(runs, "RUNS_DB_PATH", tmp_path / "runs.duckdb")
    monkeypatch.setattr(runs, "LAKEBRANCH_DIR", tmp_path)
    return runs.RUNS_DB_PATH


@pytest.fixture
def lake_dir(tmp_path):
    """A scratch directory for the SQLite catalog DB + warehouse."""
    return tmp_path / "lake"


@pytest.fixture
def sqlite_env(lake_dir, monkeypatch):
    """Point the SQLite catalog + filesystem warehouse at a temp directory.

    Shared by the Docker-free catalog integration tests and the GUI API
    integration tests, so both can run in CI without Docker or Nessie.
    """
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("CATALOG_PROFILE", "sqlite")
    monkeypatch.setenv("FS_PATH", str(lake_dir / "warehouse"))
    monkeypatch.setenv("WAREHOUSE", str(lake_dir / "warehouse"))
    catalog_uri = "sqlite:///" + str(lake_dir / "catalog.db").replace(os.sep, "/")
    monkeypatch.setenv("CATALOG_URI", catalog_uri)
    # load_config() calls load_dotenv() which reads the repo .env; neutralize.
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    return lake_dir
