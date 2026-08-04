"""
Lakebranch — DuckDB SQL-over-Iceberg query engine
=================================================

Runs real SQL (SELECT / JOIN / GROUP BY / subqueries / …) over the Iceberg
tables in the configured catalog by loading each table's current snapshot
into an in-memory PyArrow table and registering it as a DuckDB view.

This is **Docker-independent**: it works with both catalog profiles (Nessie
REST catalog or the SQLite catalog) and every storage profile (SeaweedFS,
MinIO, AWS S3, or local filesystem), because it uses PyIceberg's catalog
abstraction — no DuckDB ``iceberg`` extension, no S3 credential plumbing.

Each table is registered twice:

- Under a sanitized view name (``db.events`` → ``db_events``) — the canonical
  name for SQL.
- Under its quoted, dotted Iceberg table name (``"db.events"``) as an alias,
  so ``SELECT * FROM "db.events"`` also works.

Usage (Python):

    from src.lakebranch.sql import run_sql
    result = run_sql("SELECT event_type, COUNT(*) FROM db_events GROUP BY 1")

Usage (CLI):

    python -m src.lakebranch.sql "SELECT * FROM db_events"
    lakebranch sql "SELECT event_type, COUNT(*) FROM db_events GROUP BY 1"
"""

from __future__ import annotations

import time
from typing import Any

import duckdb
import pyarrow as pa

from src.lakebranch.catalog import init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.jsonutil import df_to_rows

DEFAULT_LIMIT = 1000


def list_iceberg_tables(catalog) -> list[tuple[str, ...]]:
    """Return the dotted identifiers of every table in the catalog.

    ``(("db", "events"), ("db", "users"), ...)`` — ordered by namespace
    then table name for a stable UI/CLI listing.
    """
    identifiers: list[tuple[str, ...]] = []
    for namespace in catalog.list_namespaces():
        identifiers.extend(catalog.list_tables(namespace))
    return sorted(identifiers)


def _sanitize(table_id: str) -> str:
    """Map a dotted Iceberg table id to a valid, predictable SQL view name.

    ``db.events`` -> ``db_events``. The mapping is returned to callers so
    they can display the original dotted name.
    """
    return table_id.replace(".", "_").replace("-", "_")


def _register_table(conn: duckdb.DuckDBPyConnection, catalog, table_id: str) -> str:
    """Register one Iceberg table as a DuckDB view; returns its view name."""
    table = catalog.load_table(table_id)
    arrow_table: pa.Table = table.scan().to_arrow()

    view_name = _sanitize(table_id)
    # Drop any stale view from a previous registration (e.g. same table id).
    conn.execute(f'DROP VIEW IF EXISTS "{view_name}"')
    # register() binds an in-memory Arrow table under the sanitized name.
    conn.register(view_name, arrow_table)
    # A quoted alias so `SELECT * FROM "db.events"` works as well.
    alias = f'"{table_id}"'
    try:
        conn.execute(f'DROP VIEW IF EXISTS {alias}')
        conn.execute(f'CREATE VIEW {alias} AS SELECT * FROM "{view_name}"')
    except duckdb.Error:
        # Some identifiers may not form valid quoted aliases; the canonical
        # sanitized view name always works.
        pass
    return view_name


def _register_all_tables(conn: duckdb.DuckDBPyConnection, catalog) -> dict[str, str]:
    """Register every catalog table as a DuckDB view.

    Returns the ``{view_name: original_table_id}`` mapping.
    """
    mapping: dict[str, str] = {}
    for identifier in list_iceberg_tables(catalog):
        table_id = ".".join(identifier)
        view_name = _register_table(conn, catalog, table_id)
        if view_name in mapping:
            raise RuntimeError(
                f"Table name collision: '{mapping[view_name]}' and '{table_id}' "
                f"both map to SQL view '{view_name}'. Rename one of the tables."
            )
        mapping[view_name] = table_id
    return mapping


def run_sql(query: str, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Execute a SQL query over the configured catalog's Iceberg tables.

    Args:
        query: A SQL statement. Iceberg tables are visible under sanitized
            view names (``db.events`` → ``db_events``) and their quoted
            dotted names (``"db.events"``).
        limit: Maximum number of result rows to return. The user's query is
            wrapped in ``SELECT * FROM (<query>) ... LIMIT n`` so DuckDB only
            streams up to ``limit`` rows back to Python.

    Returns:
        A dict with ``query``, ``row_count``, ``columns``, ``rows`` (JSON-safe),
        ``tables`` (the view-name → table-id mapping), and ``duration_ms``.
    """
    started = time.monotonic()
    config = load_config()
    catalog = init_catalog(config)

    query = query.strip()
    if not query:
        raise ValueError("SQL query must not be empty.")

    conn = duckdb.connect()
    try:
        tables = _register_all_tables(conn, catalog)
        wrapped = f'SELECT * FROM (\n{query}\n) AS __lakebranch_result LIMIT {int(limit)}'
        arrow_result = conn.execute(wrapped).to_arrow_table()
    finally:
        conn.close()

    df = arrow_result.to_pandas()
    columns = [{"name": name, "type": str(dtype)} for name, dtype in df.dtypes.items()]
    rows = df_to_rows(df)
    duration_ms = int((time.monotonic() - started) * 1000)

    return {
        "query": query,
        "row_count": len(rows),
        "columns": columns,
        "rows": rows,
        "tables": tables,
        "duration_ms": duration_ms,
    }


def print_sql_result(result: dict[str, Any]) -> None:
    """Pretty-print a :func:`run_sql` result like the CLI pipeline does."""
    print(f"\n{'=' * 60}")
    print(
        f"SQL result ({result['row_count']} row(s) in {result['duration_ms']} ms):"
    )
    print(f"{'=' * 60}")
    if not result["rows"]:
        print("(no rows)")
    else:
        import pandas as pd

        df = pd.DataFrame(result["rows"], columns=[c["name"] for c in result["columns"]])
        print(df.to_string(index=False))
    print(f"{'=' * 60}\n")

    if result["tables"]:
        print("Iceberg tables available as SQL views:")
        for view_name, table_id in sorted(result["tables"].items()):
            print(f"  {view_name}  ->  {table_id}")
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="lakebranch sql",
        description="Run a SQL query over Lakebranch's Iceberg tables via DuckDB.",
    )
    parser.add_argument("query", help="SQL query, e.g. \"SELECT * FROM db_events\"")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max result rows (default: {DEFAULT_LIMIT})",
    )
    args = parser.parse_args()

    print_sql_result(run_sql(args.query, limit=args.limit))