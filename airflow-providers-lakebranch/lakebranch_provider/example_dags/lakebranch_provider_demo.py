"""
Lakebranch Airflow Provider — Demo DAG
====================================

A minimal reference DAG showing the Lakebranch operator in action. It runs two
tasks:

1. ``write_events`` — :class:`LakebranchWriteOperator` appends 3 rows to
   ``db.events`` (creating the table if it does not exist).
2. ``verify_rows`` — scans the table back via the :class:`LakebranchHook` and
   logs/pushes the row count, so you can confirm writes landed.

Preconditions
-------------
The Lakebranch data plane must be running so the DAG can reach Nessie + the
object store:

.. code-block:: bash

    docker compose -f docker/docker-compose.yml --env-file .env up -d

In the Airflow stack (``docker/docker-compose.airflow.yml``) this package is
importable via ``PYTHONPATH`` — no pip install is required.
"""

from __future__ import annotations

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from lakebranch_provider.hooks.lakebranch import LakebranchHook
from lakebranch_provider.operators.lakebranch import LakebranchWriteOperator

DEFAULT_ARGS = {
    "owner": "lakebranch",
    "retries": 1,
}

SAMPLE_ROWS = [
    {"event_id": 1, "event_type": "login", "timestamp": "2026-08-01T10:00:00Z"},
    {"event_id": 2, "event_type": "purchase", "timestamp": "2026-08-01T10:05:00Z"},
    {"event_id": 3, "event_type": "logout", "timestamp": "2026-08-01T10:10:00Z"},
]


def verify_rows(**context) -> None:
    """Load the table back and log how many rows it contains."""
    hook = LakebranchHook()
    table = hook.get_table("db.events", create_if_missing=False)
    row_count = table.scan().to_arrow().num_rows
    # Push to XCom for downstream tasks / UI visibility.
    context["ti"].xcom_push(key="row_count", value=row_count)
    print(f"db.events currently has {row_count} rows")


with DAG(
    dag_id="lakebranch_provider_demo",
    default_args=DEFAULT_ARGS,
    description="Lakebranch Airflow provider: write events to Iceberg, then verify.",
    schedule="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["lakebranch", "provider"],
) as dag:
    task_write_events = LakebranchWriteOperator(
        task_id="write_events",
        table_name="db.events",
        mode="append",
        data=SAMPLE_ROWS,
    )

    task_verify_rows = PythonOperator(
        task_id="verify_rows",
        python_callable=verify_rows,
    )

    task_write_events >> task_verify_rows