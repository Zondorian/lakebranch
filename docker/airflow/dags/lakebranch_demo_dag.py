"""
Lakebranch — Airflow Demo DAG
============================

Reference pattern for orchestrating Lakebranch pipelines with Airflow.

This DAG is intentionally minimal and well-commented so that users can copy
the pattern for their own pipelines. It runs three sequential tasks:

1. ``ensure_warehouse`` — create the configured warehouse (bucket/directory).
2. ``append_events``   — append 3 sample rows to the ``db.events`` table.
3. ``verify_rows``     — scan the table back and push the row count to XCom.

Airflow is a *swappable external execution layer*: Lakebranch itself contains no
orchestrator. The DAG reuses the exact same ``src.lakebranch`` APIs as the CLI
pipeline (``python -m src.lakebranch.write_iceberg``):
- ``src.lakebranch.config.load_config``   — profile-aware configuration
- ``src.lakebranch.storage.get_provider`` — storage provider for ``STORAGE_PROFILE``
- ``pyiceberg.catalog.load_catalog``    — Nessie REST catalog

The project root is bind-mounted at ``/opt/lakebranch`` inside the Airflow
containers and ``PYTHONPATH=/opt/lakebranch``, so imports use the project-wide
``from src.lakebranch.*`` convention.
"""

from __future__ import annotations

import logging

import pyarrow as pa
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

from src.lakebranch.catalog import ensure_namespace, ensure_table, init_catalog
from src.lakebranch.config import load_config
from src.lakebranch.storage import get_provider

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "lakebranch",
    "retries": 1,
}

# The same schema used by the CLI writer (src/lakebranch/write_iceberg.py).
EVENTS_SCHEMA = Schema(
    NestedField(field_id=1, name="event_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="event_type", field_type=StringType(), required=False),
    NestedField(field_id=3, name="timestamp", field_type=StringType(), required=False),
)


# -----------------------------------------------------------------------------
# Shared helpers (delegate to the Lakebranch core catalog module)
# -----------------------------------------------------------------------------
def _get_catalog(config: dict[str, str]):
    """Build a Nessie REST catalog using the configured storage provider."""
    return init_catalog(config)


def _ensure_namespace(catalog, namespace: str = "db") -> None:
    """Load the namespace, creating it if it does not exist."""
    ensure_namespace(catalog, namespace)


def _ensure_events_table(catalog):
    """Load or create the ``db.events`` table with the events schema."""
    return ensure_table(catalog, "db.events", EVENTS_SCHEMA)


# -----------------------------------------------------------------------------
# Task callables
# -----------------------------------------------------------------------------
def ensure_warehouse() -> None:
    """Task 1: ensure the configured warehouse (bucket/directory) exists."""
    config = load_config()
    provider = get_provider(config)
    provider.ensure_warehouse()
    log.info("Warehouse '%s' ready (profile=%s)", config["warehouse"], config["storage_profile"])


def append_events() -> None:
    """Task 2: append 3 sample event rows via PyIceberg + PyArrow."""
    config = load_config()
    catalog = _get_catalog(config)

    _ensure_namespace(catalog, namespace="db")
    table = _ensure_events_table(catalog)

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
    log.info("Appended %d sample rows to db.events", arrow_table.num_rows)


def verify_rows(ti) -> None:
    """Task 3: scan the table back and push the row count to XCom."""
    config = load_config()
    catalog = _get_catalog(config)
    table = catalog.load_table("db.events")

    arrow_table = table.scan().to_arrow()
    row_count = arrow_table.num_rows

    # Push to XCom for downstream tasks / UI visibility, and log it.
    ti.xcom_push(key="row_count", value=row_count)
    log.info("db.events currently has %d rows", row_count)


# -----------------------------------------------------------------------------
# DAG definition
# -----------------------------------------------------------------------------
with DAG(
    dag_id="lakebranch_demo",
    default_args=DEFAULT_ARGS,
    description="Lakebranch reference pipeline: ensure warehouse, append events, verify rows.",
    schedule="@daily",           # daily schedule
    start_date=days_ago(1),      # start yesterday so the DAG is immediately schedulable
    catchup=False,               # don't backfill missed days
    tags=["lakebranch", "demo"],
) as dag:
    task_ensure_warehouse = PythonOperator(
        task_id="ensure_warehouse",
        python_callable=ensure_warehouse,
    )

    task_append_events = PythonOperator(
        task_id="append_events",
        python_callable=append_events,
    )

    task_verify_rows = PythonOperator(
        task_id="verify_rows",
        python_callable=verify_rows,
    )

    # Linear pipeline: warehouse → append → verify.
    task_ensure_warehouse >> task_append_events >> task_verify_rows