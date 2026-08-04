"""Tests for the DuckDB run-log layer."""

from __future__ import annotations

from src.lakebranch.runs import log_run, recent_runs


def test_successful_run_records_row(tmp_run_db):
    with log_run(pipeline="test_pipeline", profile="seaweedfs", warehouse="warehouse") as run:
        run.rows_written = 42

    runs = recent_runs()
    assert len(runs) == 1
    r = runs[0]
    assert r["pipeline"] == "test_pipeline"
    assert r["profile"] == "seaweedfs"
    assert r["warehouse"] == "warehouse"
    assert r["status"] == "success"
    assert r["rows_written"] == 42
    assert r["duration_ms"] is not None
    assert r["error"] is None


def test_failed_run_records_error(tmp_run_db):
    try:
        with log_run(pipeline="test_pipeline", profile="seaweedfs", warehouse="warehouse"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    runs = recent_runs()
    assert len(runs) == 1
    r = runs[0]
    assert r["status"] == "failed"
    assert r["error"] == "boom"


def test_recent_runs_newest_first(tmp_run_db):
    with log_run(pipeline="a", profile="seaweedfs", warehouse="w"):
        pass
    with log_run(pipeline="b", profile="seaweedfs", warehouse="w"):
        pass
    runs = recent_runs()
    assert [r["pipeline"] for r in runs] == ["b", "a"]


def test_no_db_returns_empty(tmp_run_db):
    assert recent_runs() == []