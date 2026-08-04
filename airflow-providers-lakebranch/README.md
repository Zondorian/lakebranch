# Lakebranch Airflow Provider

**Apache 2.0**

The Lakebranch Airflow provider makes *"write to Iceberg via Lakebranch"* a **one-operator DAG**. It wraps the Lakebranch core (`src.lakebranch.config`, `src.lakebranch.storage`) and the PyIceberg REST catalog so your DAGs don't re-implement storage/catalog wiring.

This package is versioned and released independently from the Lakebranch core, but is fully Apache 2.0 like the rest of the project.

## What's inside

| Module | Purpose |
|--------|---------|
| `lakebranch_provider.hooks.lakebranch.LakebranchHook` | Wraps `load_config()` + `get_provider()` + PyIceberg Nessie catalog; ensures warehouse, namespaces, and tables |
| `lakebranch_provider.operators.lakebranch.LakebranchWriteOperator` | Appends (or overwrites) rows to an Iceberg table as a single Airflow task |
| `lakebranch_provider.example_dags.lakebranch_provider_demo.py` | Canonical demo DAG (write + verify). Re-exported into the stack's DAGs folder as `lakebranch_provider_demo` |

## Install

```bash
pip install -e ./airflow-providers-lakebranch
```

> **Requires Airflow.** This provider imports `apache-airflow` at package import time. If your Python environment doesn't already have Airflow installed (e.g. the Lakebranch dev venv), install it inside the Airflow container instead — see the *Zero-install (Docker)* section below.

### Zero-install (Docker / PYTHONPATH)

The Airflow Docker image sets `PYTHONPATH=/opt/lakebranch:/opt/lakebranch/airflow-providers-lakebranch`. Because the whole repo root is bind-mounted into the Airflow containers, every container (webserver, scheduler, worker, triggerer) can immediately `import lakebranch_provider` with no pip install. Note that this makes the package *importable* but does **not** register it in Airflow's provider plugin registry — entry points only matter if you want the provider listed on the Providers page / auto-registered operators, which isn't required for a demo DAG that imports directly.

> **Core dependency.** The provider wraps the Lakebranch core (`src.lakebranch`). Install the core with `pip install -e .` from the repo root, or rely on the repo root being on `PYTHONPATH` (as it is in the Airflow Docker image).

## Usage

### One-operator DAG

```python
from airflow import DAG
from airflow.utils.dates import days_ago
from lakebranch_provider import LakebranchWriteOperator

with DAG(dag_id="write_events_demo", schedule="@daily", start_date=days_ago(1), catchup=False) as dag:
    write = LakebranchWriteOperator(
        task_id="write_events",
        table_name="db.events",
        mode="append",
        data=[
            {"event_id": 4, "event_type": "signup", "timestamp": "2026-08-01T12:00:00Z"},
            {"event_id": 5, "event_type": "signup", "timestamp": "2026-08-01T12:05:00Z"},
        ],
    )
```

`data` also accepts a JSON-payload string (e.g. from XCom or a variable):

```python
LakebranchWriteOperator(
    task_id="write_events",
    table_name="db.events",
    mode="append",
    data='[{"event_id": 6, "event_type": "click"}]',   # JSON string
)
```

### Full example

See `lakebranch_provider/example_dags/lakebranch_provider_demo.py` — a two-task DAG (write, then verify row count) that appears in the Airflow UI as `lakebranch_provider_demo` once the stack is up.

## Running the demo in the Lakebranch stack

```bash
# 1. Start the data plane (Nessie + SeaweedFS)
docker compose -f docker/docker-compose.yml --env-file .env up -d

# 2. Start Airflow (provider auto-imported via PYTHONPATH)
docker compose -f docker/docker-compose.airflow.yml up -d --build
```

Open http://localhost:8080 — both `lakebranch_demo` (reference DAG) and `lakebranch_provider_demo` (this provider's demo) should be listed. Trigger `lakebranch_provider_demo` and confirm both tasks turn green.

## Licensing

- **Core (`src/lakebranch`)**: Apache 2.0.
- **This provider**: Apache 2.0.
