"""
Lakebranch — Pipeline Run Logger
==============================

A lightweight telemetry layer that records pipeline run history (status,
duration, rows written, errors) to a local DuckDB database.

This is run history/status tracking only — it is **not** a DAG orchestrator.
No scheduling, dependencies, retries, or DAG semantics are implied. Airflow
integration is planned as an optional profile later, layered on top of this
run log.

The database lives at ``.lakebranch/runs.duckdb`` and is auto-created on first use.

Usage:
    python -m src.lakebranch.runs   # print the 10 most recent runs
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

# -----------------------------------------------------------------------------
# Run-log database
# -----------------------------------------------------------------------------
LAKEBRANCH_DIR = Path(".lakebranch")
RUNS_DB_PATH = LAKEBRANCH_DIR / "runs.duckdb"

_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS lakebranch_runs (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    pipeline TEXT,
    profile TEXT,
    warehouse TEXT,
    status TEXT,
    rows_written INTEGER,
    duration_ms INTEGER,
    error TEXT
)
"""


def _utcnow() -> datetime:
    """Return a naive UTC timestamp (DuckDB TIMESTAMP is timezone-naive)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _open_db():
    """Open a connection to the run-log DB, creating the directory/schema if needed."""
    LAKEBRANCH_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(RUNS_DB_PATH))
    conn.execute(_RUNS_SCHEMA)
    return conn


# -----------------------------------------------------------------------------
# Run handle / context manager
# -----------------------------------------------------------------------------
class RunHandle:
    """Context-manager handle returned by :func:`log_run`.

    The caller may set :attr:`rows_written` before the block exits; it is
    recorded in the run log as the number of rows the pipeline finalized.
    """

    def __init__(self, pipeline: str, profile: str, warehouse: str) -> None:
        self.pipeline = pipeline
        self.profile = profile
        self.warehouse = warehouse
        self.rows_written: int | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.duration_ms: int | None = None
        self.status: str = "success"
        self.error: str | None = None

    def __enter__(self) -> RunHandle:
        self.started_at = _utcnow()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.finished_at = _utcnow()
        if self.started_at is not None:
            self.duration_ms = int(
                (self.finished_at - self.started_at).total_seconds() * 1000
            )
        if exc_type is not None:
            self.status = "failed"
            self.error = str(exc_value) if exc_value is not None else exc_type.__name__

        _insert_run(self)

        # Do not suppress the exception; let the caller handle it.
        return False


def log_run(pipeline: str, profile: str, warehouse: str) -> RunHandle:
    """Context manager that records a pipeline run in the local run-log DB.

    Usage::

        with log_run(
            pipeline="write_iceberg",
            profile=config["storage_profile"],
            warehouse=config["warehouse"],
        ) as run:
            do_work()
            run.rows_written = n_rows
    """
    return RunHandle(pipeline=pipeline, profile=profile, warehouse=warehouse)


# -----------------------------------------------------------------------------
# Persistence & queries
# -----------------------------------------------------------------------------
def _insert_run(handle: RunHandle) -> None:
    """Insert a completed run row into the run-log DB."""
    conn = _open_db()
    try:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM lakebranch_runs"
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO lakebranch_runs
                (id, started_at, finished_at, pipeline, profile, warehouse,
                 status, rows_written, duration_ms, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                next_id,
                handle.started_at,
                handle.finished_at,
                handle.pipeline,
                handle.profile,
                handle.warehouse,
                handle.status,
                handle.rows_written,
                handle.duration_ms,
                handle.error,
            ],
        )
    finally:
        conn.close()


RUN_COLUMNS = (
    "id",
    "started_at",
    "finished_at",
    "pipeline",
    "profile",
    "warehouse",
    "status",
    "rows_written",
    "duration_ms",
    "error",
)


def recent_runs(limit: int = 10) -> list[dict[str, Any]]:
    """Return the most recent runs as a list of dicts, newest first.

    Only reads the local DuckDB file — no external services are contacted.
    """
    if not RUNS_DB_PATH.exists():
        return []

    conn = _open_db()
    try:
        rows = conn.execute(
            f"""
            SELECT {", ".join(RUN_COLUMNS)}
            FROM lakebranch_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
    finally:
        conn.close()

    return [dict(zip(RUN_COLUMNS, row)) for row in rows]


def print_recent_runs(limit: int = 10) -> None:
    """Print the most recent runs as a formatted table (pandas to_string style)."""
    runs = recent_runs(limit=limit)

    if not runs:
        print(
            "No pipeline runs recorded yet. "
            "Run `python -m src.lakebranch.write_iceberg` first, then re-run this command."
        )
        return

    df = pd.DataFrame(runs)
    print(f"\n{'=' * 60}")
    print(f"Recent pipeline runs ({len(df)} shown):")
    print(f"{'=' * 60}")
    print(df.to_string(index=False))
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    print_recent_runs()