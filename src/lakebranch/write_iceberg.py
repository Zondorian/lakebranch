"""
Lakebranch — Iceberg Writer
=========================

Connects to the Nessie REST catalog via PyIceberg, ensures the warehouse
(bucket/directory) backing the warehouse exists, creates the `db` namespace,
creates the `db.events` table with a simple schema, appends 3 rows of sample
event data, and queries the table back.

The storage backend is selected via the ``STORAGE_PROFILE`` environment
variable — switching between SeaweedFS, MinIO, AWS S3, or a local filesystem
requires zero changes to this pipeline code.

Each run is recorded (status, duration, rows written, errors) in the local
run-log database at ``.lakebranch/runs.duckdb`` via :mod:`src.lakebranch.runs`.
View recent runs with:

    python -m src.lakebranch.runs

Usage:
    python -m src.lakebranch.write_iceberg
"""

from __future__ import annotations

import sys

import pyarrow as pa
from dotenv import load_dotenv
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import (
    NamespaceAlreadyExistsError,
    NoSuchNamespaceError,
    NoSuchTableError,
)
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

from src.lakebranch.config import load_config
from src.lakebranch.runs import log_run
from src.lakebranch.storage import get_provider

load_dotenv()


# -----------------------------------------------------------------------------
# Catalog & namespace bootstrap
# -----------------------------------------------------------------------------
def init_catalog(config: dict[str, str]):
    """Initialize the PyIceberg REST catalog pointing at Nessie."""
    print(f"[nessie] Initializing REST catalog at {config['nessie_uri']}")

    # Select the storage provider for the configured profile.
    provider = get_provider(config)

    catalog = load_catalog(
        "nessie",
        **{
            "type": "rest",
            "uri": config["nessie_uri"],
            "warehouse": config["warehouse"],
            **provider.catalog_properties(),
        },
    )
    return catalog


def ensure_namespace(catalog, namespace: str = "db") -> None:
    """Load the given namespace, creating it if it does not exist."""
    print(f"[nessie] Ensuring namespace '{namespace}' exists")
    try:
        catalog.load_namespace_properties(namespace)
        print(f"[nessie] Namespace '{namespace}' already exists.")
    except NoSuchNamespaceError:
        try:
            catalog.create_namespace(namespace)
            print(f"[nessie] Created namespace '{namespace}'.")
        except NamespaceAlreadyExistsError:
            # Race-safe: another process created it between check and create.
            print(f"[nessie] Namespace '{namespace}' already exists (created concurrently).")


# -----------------------------------------------------------------------------
# Table operations
# -----------------------------------------------------------------------------
EVENTS_SCHEMA = Schema(
    # Field IDs are required by Iceberg; 1, 2, 3 are conventional.
    NestedField(field_id=1, name="event_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="event_type", field_type=StringType(), required=False),
    NestedField(field_id=3, name="timestamp", field_type=StringType(), required=False),
)


def ensure_events_table(catalog):
    """Load or create the `db.events` table with the events schema."""
    print("[iceberg] Ensuring table 'db.events' exists")
    try:
        table = catalog.load_table("db.events")
        print("[iceberg] Table 'db.events' already exists.")
    except NoSuchTableError:
        table = catalog.create_table(
            "db.events",
            schema=EVENTS_SCHEMA,
        )
        print("[iceberg] Created table 'db.events'.")
    return table


def append_sample_events(table) -> None:
    """Append 3 rows of sample event data to the table via PyArrow."""
    print("[iceberg] Appending 3 sample event rows")

    arrow_table = pa.table(
        {
            "event_id": pa.array([1, 2, 3], type=pa.int64()),
            "event_type": pa.array(["login", "purchase", "logout"], type=pa.string()),
            "timestamp": pa.array(
                ["2026-07-31T10:00:00Z", "2026-07-31T10:05:00Z", "2026-07-31T10:10:00Z"],
                type=pa.string(),
            ),
        },
        schema=pa.schema(
            [
                pa.field("event_id", pa.int64(), nullable=False),
                pa.field("event_type", pa.string()),
                pa.field("timestamp", pa.string()),
            ]
        ),
    )

    table.append(arrow_table)
    print("[iceberg] Data appended successfully.")


def query_events(table) -> int:
    """Scan the table back to a PyArrow table and print the result as a DataFrame.

    Returns the number of rows in the query result, used as ``rows_written``
    for run telemetry.
    """
    print("[iceberg] Scanning table 'db.events'")

    arrow_table = table.scan().to_arrow()
    df = arrow_table.to_pandas()

    print(f"\n{'=' * 60}")
    print(f"Query result ({len(df)} rows):")
    print(f"{'=' * 60}")
    print(df.to_string(index=False))
    print(f"{'=' * 60}\n")

    return len(df)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> None:
    # 1. Load configuration based on STORAGE_PROFILE.
    config = load_config()

    # 2. Run the pipeline, recording run telemetry to the local run-log DB.
    #    The context manager records start/finish times, status, and any
    #    exception message; it re-raises exceptions after logging them.
    with log_run(
        pipeline="write_iceberg",
        profile=config["storage_profile"],
        warehouse=config["warehouse"],
    ) as run:
        # 3. Ensure the warehouse (bucket/directory) exists.
        provider = get_provider(config)
        provider.ensure_warehouse()

        # 4. Initialize the PyIceberg REST catalog.
        catalog = init_catalog(config)

        # 5. Load or create the `db` namespace.
        ensure_namespace(catalog, namespace="db")

        # 6. Load or create the `db.events` table.
        table = ensure_events_table(catalog)

        # 7. Append 3 rows of sample event data.
        append_sample_events(table)

        # 8. Query the table back and print the result, capturing the
        #    number of rows in the result for run telemetry.
        run.rows_written = query_events(table)

    print("[done] All operations completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)