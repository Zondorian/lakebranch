"""
Lakebranch — GUI API (Developer Preview)
======================================

FastAPI backend for the Lakebranch web UI, an **open-source developer preview**.

This API exposes:

- ``GET  /api/tables``            — list namespaces and tables via the Nessie REST catalog
- ``GET  /api/tables/{table}``    — table schema + metadata + snapshot history
- ``GET  /api/tables/{table}/rows?limit=100`` — scan the first N rows to pandas → JSON
- ``GET  /api/tables/{table}/rows?snapshot_id=…`` — time-travel scan at a past snapshot
- ``GET  /api/tables/{table}/diff?from_snapshot_id=…&to_snapshot_id=…`` — diff two snapshots
- ``POST /api/query``             — run an Iceberg scan with a filter expression
- ``POST /api/namespaces``        — create a namespace
- ``POST /api/tables/{table}/data`` — upload CSV/Parquet and append/overwrite (creates the table if missing)
- ``POST /api/tables/{table}/rows`` — write JSON rows (append/overwrite; creates the table if missing)
- ``GET  /api/runs``              — pipeline run-log entries (from ``src.lakebranch.runs``)

The static UI lives at ``src/lakebranch/ui/index.html`` and is served at ``/ui/``.

Run:
    uvicorn src.lakebranch.api.app:app --port 8787
"""

from __future__ import annotations

import io
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import pyarrow as pa
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pyiceberg.exceptions import NoSuchTableError
from pyiceberg.io.pyarrow import pyarrow_to_schema, schema_to_pyarrow
from pyiceberg.table import Table

from src.lakebranch.catalog import ensure_namespace, init_catalog, namespace_of
from src.lakebranch.config import load_config
from src.lakebranch.runs import log_run, recent_runs

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

app = FastAPI(
    title="Lakebranch GUI (Developer Preview)",
    description=(
        "Development-preview API for the Lakebranch web UI. "
        "Lakebranch is fully open source under Apache 2.0."
    ),
    version="0.1.0-dev",
)

# Permissive CORS for local development only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Catalog helper (built lazily so the API can start even if services are down)
# -----------------------------------------------------------------------------
_catalog = None


def _get_catalog():
    """Load (once) and return the PyIceberg REST catalog for the configured profile."""
    global _catalog
    if _catalog is None:
        try:
            config = load_config()
            _catalog = init_catalog(config)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to connect to the Nessie catalog: {exc}",
            ) from exc
    return _catalog


def _load_table(table_name: str) -> Table:
    """Load a table by dotted identifier (e.g. ``db.events``), raising a 404 if absent."""
    try:
        return _get_catalog().load_table(table_name)
    except NoSuchTableError as exc:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Catalog error: {exc}") from exc


# -----------------------------------------------------------------------------
# JSON-friendly serialization helpers
# -----------------------------------------------------------------------------
def _json_safe(value: Any) -> Any:
    """Convert a pandas/arrow/scalar value into a JSON-serializable Python value."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    # numpy scalar types (int64, float64, bool, …) expose .item()
    converter = getattr(value, "item", None)
    if callable(converter):
        try:
            converted = converter()
        except (ValueError, TypeError):
            return str(value)
        return _json_safe(converted)
    return value


def _df_to_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a pandas DataFrame into a list of JSON-safe row dicts."""
    df = df.where(pd.notnull(df), None)  # NaN → None
    records = df.to_dict(orient="records")
    return [{k: _json_safe(v) for k, v in row.items()} for row in records]


# -----------------------------------------------------------------------------
# API routes
# -----------------------------------------------------------------------------
@app.get("/api/tables")
def list_tables() -> dict[str, list[str]]:
    """List all namespaces and tables in the Nessie REST catalog."""
    try:
        catalog = _get_catalog()
        namespaces: list[tuple[str, ...]] = list(catalog.list_namespaces())
        table_ids: list[tuple[str, ...]] = []
        for namespace in namespaces:
            table_ids.extend(catalog.list_tables(namespace))

        def dotted(identifier: tuple[str, ...]) -> str:
            return ".".join(identifier)

        return {
            "namespaces": sorted(dotted(ns) for ns in namespaces),
            "tables": sorted(dotted(tbl) for tbl in table_ids),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Catalog error: {exc}") from exc


@app.get("/api/tables/{table:path}/rows")
def table_rows(
    table: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Max rows to scan"),
    snapshot_id: int | None = Query(
        default=None,
        description="Iceberg snapshot ID to scan (time travel). Defaults to the current snapshot.",
    ),
) -> dict[str, Any]:
    """Scan the first N rows of a table (optionally at a specific snapshot).

    NOTE: registered BEFORE the ``{table:path}`` detail route so that the
    ``/rows`` suffix is not swallowed by the greedy path converter.
    """
    iceberg_table = _load_table(table)
    try:
        scan_kwargs: dict[str, Any] = {"limit": limit}
        if snapshot_id is not None:
            scan_kwargs["snapshot_id"] = snapshot_id
        # pyiceberg's Table.scan() takes limit / snapshot_id (and row_filter)
        # as keyword args directly.
        arrow_table = iceberg_table.scan(**scan_kwargs).to_arrow()
        df = arrow_table.to_pandas()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scan failed: {exc}") from exc

    return {
        "table": table,
        "limit": limit,
        "snapshot_id": snapshot_id,
        "row_count": len(df),
        "columns": [{"name": col, "type": str(dtype)} for col, dtype in df.dtypes.items()],
        "rows": _df_to_rows(df),
    }


@app.get("/api/tables/{table:path}")
def table_detail(table: str) -> dict[str, Any]:
    """Return a table's schema and high-level metadata."""
    iceberg_table = _load_table(table)
    schema = iceberg_table.schema()
    metadata = iceberg_table.metadata

    snapshots = []
    if metadata.snapshots is not None:
        for snap in metadata.snapshots:
            # pyiceberg stores the operation (append/overwrite/delete) in the
            # snapshot summary, not as a direct attribute.
            summary = snap.summary or {}
            snapshots.append(
                {
                    "snapshot_id": snap.snapshot_id,
                    "timestamp_ms": snap.timestamp_ms,
                    "operation": summary.get("operation", "unknown"),
                    "manifest_list": snap.manifest_list,
                }
            )

    return {
        # pyiceberg exposes Table.name as a method, not a property.
        "name": iceberg_table.name(),
        "location": metadata.location,
        "schema_id": schema.schema_id,
        "fields": [
            {
                "field_id": field.field_id,
                "name": field.name,
                "type": str(field.field_type),
                "required": field.required,
                "doc": field.doc,
            }
            for field in schema.fields
        ],
        "properties": dict(metadata.properties or {}),
        "current_snapshot_id": metadata.current_snapshot_id,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots[-5:],  # last 5 snapshots for a compact overview
    }


@app.get("/api/tables/{table:path}/diff")
def table_diff(
    table: str,
    from_snapshot_id: int = Query(..., description="Baseline snapshot ID"),
    to_snapshot_id: int = Query(..., description="Target snapshot ID"),
    limit: int = Query(default=100, ge=1, le=1000, description="Max rows per side"),
) -> dict[str, Any]:
    """Compare two snapshots of a table (time-travel diff).

    Scans the table at each snapshot and reports rows that were added or
    removed between them (matched by row equality), plus per-side row counts.
    Iceberg's snapshot history makes this possible — no other local OSS tool
    exposes it in a UI.
    """
    iceberg_table = _load_table(table)
    try:
        arrow_from = iceberg_table.scan(snapshot_id=from_snapshot_id, limit=limit).to_arrow()
        arrow_to = iceberg_table.scan(snapshot_id=to_snapshot_id, limit=limit).to_arrow()
        df_from = arrow_from.to_pandas()
        df_to = arrow_to.to_pandas()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Diff failed: {exc}") from exc

    # Diff by row-set equality (order-insensitive) on the common columns.
    common_cols = [col for col in df_to.columns if col in df_from.columns]
    set_from = {tuple(r[col] for col in common_cols) for _, r in df_from.iterrows()} if len(df_from) else set()
    set_to = {tuple(r[col] for col in common_cols) for _, r in df_to.iterrows()} if len(df_to) else set()

    removed_rows = [
        dict(zip(common_cols, row))
        for row in sorted(set_from - set_to)
    ]
    added_rows = [
        dict(zip(common_cols, row))
        for row in sorted(set_to - set_from)
    ]

    return {
        "table": table,
        "from_snapshot_id": from_snapshot_id,
        "to_snapshot_id": to_snapshot_id,
        "from_row_count": len(df_from),
        "to_row_count": len(df_to),
        "added_rows": added_rows,
        "removed_rows": removed_rows,
    }


class QueryRequest(BaseModel):
    """Body for ``POST /api/query`` — an Iceberg scan with a filter expression."""

    table: str = Field(..., description="Dotted table identifier, e.g. 'db.events'")
    filter: str = Field(
        default="",
        description=(
            "Iceberg SQL row filter, e.g. \"event_id > 1\" or "
            "\"event_type = 'login'\". Empty = no filter."
        ),
    )
    limit: int = Field(default=100, ge=1, le=1000, description="Max rows to return")


@app.post("/api/query")
def run_query(request: QueryRequest) -> dict[str, Any]:
    """Run an Iceberg scan with an optional filter expression and return rows as JSON."""
    iceberg_table = _load_table(request.table)
    try:
        scan_kwargs: dict[str, Any] = {"limit": request.limit}
        if request.filter.strip():
            scan_kwargs["row_filter"] = request.filter.strip()
        arrow_table = iceberg_table.scan(**scan_kwargs).to_arrow()
        df = arrow_table.to_pandas()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Query failed — check the filter expression. Error: {exc}",
        ) from exc

    return {
        "table": request.table,
        "filter": request.filter,
        "limit": request.limit,
        "row_count": len(df),
        "columns": [{"name": col, "type": str(dtype)} for col, dtype in df.dtypes.items()],
        "rows": _df_to_rows(df),
    }


# -----------------------------------------------------------------------------
# Write support (upload CSV/Parquet, append/overwrite, JSON rows)
# -----------------------------------------------------------------------------
VALID_WRITE_MODES = ("append", "overwrite")


class WriteRowsRequest(BaseModel):
    """Body for ``POST /api/tables/{table}/rows`` — write JSON rows."""

    mode: str = Field(default="append", description="'append' or 'overwrite'")
    rows: list[dict[str, Any]] = Field(..., description="List of row dicts to write")


def _get_or_create_writable_table(table_name: str, arrow_schema: pa.Schema) -> tuple[Table, bool]:
    """Load an existing table, or create it from the given Arrow schema.

    Returns:
        A ``(table, created)`` tuple where ``created`` is True when the table
        was newly created from the inferred Arrow schema.
    """
    catalog = _get_catalog()
    try:
        return catalog.load_table(table_name), False
    except NoSuchTableError:
        iceberg_schema = pyarrow_to_schema(arrow_schema)
        ensure_namespace(catalog, namespace_of(table_name))
        return catalog.create_table(table_name, schema=iceberg_schema), True


def _parse_upload(file: UploadFile) -> pa.Table:
    """Parse an uploaded CSV or Parquet file into a PyArrow table."""
    raw = file.file.read()
    name = (file.filename or "").lower()
    if name.endswith((".parquet", ".pq")):
        return pa.parquet.read_table(io.BytesIO(raw))
    # Default to CSV; pandas gives the most tolerant CSV parsing.
    df = pd.read_csv(io.BytesIO(raw))
    return pa.Table.from_pandas(df)


def _apply_write(table_name: str, arrow_table: pa.Table, mode: str, pipeline: str) -> dict[str, Any]:
    """Append/overwrite ``arrow_table`` to ``table_name``, recording a run row."""
    if mode not in VALID_WRITE_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid mode '{mode}'. Valid modes: {', '.join(VALID_WRITE_MODES)}",
        )
    config = load_config()
    with log_run(
        pipeline=pipeline,
        profile=config["storage_profile"],
        warehouse=config["warehouse"],
    ) as run:
        table, created = _get_or_create_writable_table(table_name, arrow_table.schema)
        # Match the Iceberg table's exact schema (names/types/nullability) so
        # PyIceberg accepts the append/overwrite.
        arrow_table = arrow_table.cast(schema_to_pyarrow(table.schema()))
        if mode == "append":
            table.append(arrow_table)
        else:
            table.overwrite(arrow_table)
        run.rows_written = arrow_table.num_rows
    return {
        "table": table_name,
        "mode": mode,
        "rows_written": arrow_table.num_rows,
        "created": created,
        "snapshot_id": table.metadata.current_snapshot_id,
    }


@app.post("/api/namespaces")
def create_namespace_api(namespace: str = Query(..., description="Namespace to create, e.g. 'db'")) -> dict[str, Any]:
    """Create a namespace (idempotent)."""
    try:
        ensure_namespace(_get_catalog(), namespace)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Catalog error: {exc}") from exc
    return {"namespace": namespace, "created": True}


@app.post("/api/tables/{table:path}/rows")
def write_rows(table: str, request: WriteRowsRequest) -> dict[str, Any]:
    """Write JSON rows to a table (append/overwrite), creating it if missing."""
    if not request.rows:
        raise HTTPException(status_code=422, detail="'rows' must not be empty.")
    try:
        arrow_table = pa.Table.from_pylist(request.rows)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not infer a schema from the rows. Error: {exc}",
        ) from exc
    try:
        return _apply_write(table, arrow_table, request.mode, pipeline="gui_write_rows")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Write failed: {exc}") from exc


@app.post("/api/tables/{table:path}/data")
async def upload_data(
    table: str,
    file: Annotated[UploadFile, File(..., description="CSV or Parquet file")],
    mode: Annotated[str, Form(description="'append' or 'overwrite'")] = "append",
) -> dict[str, Any]:
    """Upload a CSV/Parquet file and append/overwrite it to a table.

    The table is created automatically (with a schema inferred from the file)
    if it does not already exist. The write is recorded in the run log.
    """
    try:
        arrow_table = _parse_upload(file)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse uploaded file as CSV/Parquet. Error: {exc}",
        ) from exc
    if arrow_table.num_rows == 0:
        raise HTTPException(status_code=422, detail="Uploaded file contains no rows.")
    try:
        return _apply_write(table, arrow_table, mode, pipeline="gui_upload")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Write failed: {exc}") from exc


@app.get("/api/runs")
def runs(limit: int = Query(default=10, ge=1, le=100)) -> dict[str, Any]:
    """Return recent pipeline run-log entries (from the local DuckDB run log)."""
    entries = recent_runs(limit=limit)
    return {
        "count": len(entries),
        "runs": [{k: _json_safe(v) for k, v in run.items()} for run in entries],
    }


# -----------------------------------------------------------------------------
# Static UI
# -----------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect the root path to the Lakebranch UI."""
    return RedirectResponse(url="/ui/")


app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.lakebranch.api.app:app", host="0.0.0.0", port=8787, reload=True)