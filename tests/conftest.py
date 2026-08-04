"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_run_db(tmp_path, monkeypatch):
    """Point the run-log DB at a temp file so tests never touch .lakebranch/."""
    from src.lakebranch import runs

    monkeypatch.setattr(runs, "RUNS_DB_PATH", tmp_path / "runs.duckdb")
    monkeypatch.setattr(runs, "LAKEBRANCH_DIR", tmp_path)
    return runs.RUNS_DB_PATH