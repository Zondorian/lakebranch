# Lakebranch

[![CI](https://github.com/USERNAME/lakebranch/actions/workflows/ci.yml/badge.svg)](https://github.com/USERNAME/lakebranch/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Lakebranch** is a local, self-contained Iceberg data lake stack. The default stack is built on **Nessie** (Iceberg REST catalog) and **SeaweedFS** (S3-compatible object storage), but a **Docker-free** profile (SQLite catalog + local filesystem) is also available. It provides a fully working end-to-end pipeline for writing and querying Apache Iceberg tables entirely on your local machine — no cloud accounts, no external services.

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│  PyIceberg  │────▶│    Nessie    │────▶│     SeaweedFS      │
│  (Client)   │     │ REST Catalog │     │  S3 Object Store   │
│             │     │  :19120      │     │  :9000 / :9333     │
└─────────────┘     └──────────────┘     └────────────────────┘

   ── or, Docker-free (no containers at all) ──
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  PyIceberg  │────▶│  SQLite Catalog  │────▶│  Local Filesystem│
│  (Client)   │     │  (CATALOG_URI)   │     │  (FS_PATH)       │
└─────────────┘     └──────────────────┘     └──────────────────┘
```

## Architecture

| Component | Role | Ports |
|-----------|------|-------|
| **SeaweedFS** | S3-compatible object storage that physically stores Iceberg table data (Parquet files, manifests, metadata) | `9000` (S3 API), `9333` (Master), `8080` (Volume) |
| **Nessie** | Git-like Iceberg REST catalog server that tracks table metadata, schemas, and snapshots | `19120` (REST API) |
| **PyIceberg** | Python client that talks to the catalog via the Iceberg protocol and reads/writes data through the storage layer | — |
| **SQLite catalog** *(optional)* | Local file-based Iceberg catalog (PyIceberg `SqlCatalog`) — no server needed; pairs with `STORAGE_PROFILE=filesystem` | — |

The warehouse is a single SeaweedFS bucket named `warehouse`. Nessie is configured to use this bucket as the default warehouse location, and PyIceberg connects to Nessie's REST endpoint to manage namespaces and tables. With the SQLite catalog profile, the warehouse is a local directory and the catalog metadata lives in a local `catalog.db` file.

## Prerequisites

- **Docker** with Docker Compose v2 (`docker compose` command)
- **Python 3.10+**
- **pip** (or your preferred Python package manager)

## Quick Start

### 1. Spin up the services

From the project root, start SeaweedFS and Nessie:

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

This command:

1. Reads environment variables from `.env` (object store credentials, Nessie URI, S3 connection settings).
2. Starts the **SeaweedFS** container (`lakebranch-seaweedfs`) with the S3 API on port `9000`, master on `9333`, and volume on `8080`.
3. Starts the **Nessie** container (`lakebranch-nessie`) on port `19120`, waiting for SeaweedFS to become healthy first.

Verify both containers are running:

```bash
docker compose -f docker/docker-compose.yml ps
```

You should see both `lakebranch-seaweedfs` and `lakebranch-nessie` in a `running` (healthy) state.

### 2. Set up a Python virtual environment (recommended)

It is **strongly recommended** to install the Python dependencies inside a virtual environment to avoid polluting your system Python and to keep project dependencies isolated. From the project root:

**Windows (PowerShell / cmd):**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your shell prompt should now show `(.venv)` at the beginning, indicating the virtual environment is active.

### 3. Install Python dependencies

With the virtual environment active, install the project dependencies:

```bash
pip install -r requirements.txt
```

This installs `pyiceberg[s3fs,pyarrow,sql-sqlite]`, `pandas`, `duckdb`, and `python-dotenv`.

> **Note:** The `.venv/` directory is already excluded via `.gitignore`, so it won't be committed to version control.

### 4. Run the test writer/query script

```bash
python -m src.lakebranch.write_iceberg
```

The script performs the following end-to-end operations:

1. **Ensures the object store bucket** `warehouse` exists (creates it if absent) via `s3fs`.
2. **Initializes the PyIceberg REST catalog** pointing at Nessie (`http://localhost:19120/iceberg/main`).
3. **Creates the `db` namespace** if it doesn't already exist.
4. **Creates the `db.events` table** with a simple schema (`event_id`, `event_type`, `timestamp`) if it doesn't already exist.
5. **Appends 3 rows** of sample event data via PyArrow.
6. **Queries the table back** and prints the result as a pandas DataFrame.

Expected output (abbreviated):

```
[s3] Connecting to S3 endpoint: http://localhost:9000
[s3] Bucket 'warehouse' already exists.
[nessie] Initializing REST catalog at http://localhost:19120/iceberg/main
[nessie] Ensuring namespace 'db' exists
[iceberg] Ensuring table 'db.events' exists
[iceberg] Appending 3 sample event rows
[iceberg] Data appended successfully.
[iceberg] Scanning table 'db.events'

============================================================
Query result (3 rows):
============================================================
   event_id event_type              timestamp
0         1      login  2026-07-31T10:00:00Z
1         2   purchase  2026-07-31T10:05:00Z
2         3     logout  2026-07-31T10:10:00Z
============================================================

[done] All operations completed successfully.
```

> **Note:** The script is idempotent. Re-running it will reuse the existing bucket, namespace, and table, and append 3 more rows each time.

## Docker-Free Quick Start (SQLite Catalog + Local Filesystem)

Lakebranch can run the **entire end-to-end pipeline with no Docker and no containers at all** — just `pip install`. This pairs the [SQLite catalog](https://py.iceberg.apache.org/) (a single local `catalog.db` file) with the local filesystem storage provider (`STORAGE_PROFILE=filesystem`). It is ideal for quick prototyping, tests, and CI.

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the environment

Set the two profile variables in your `.env` (or export them in your shell):

```bash
STORAGE_PROFILE=filesystem
CATALOG_PROFILE=sqlite
FS_PATH=./data/warehouse          # local warehouse directory (git-ignored)
CATALOG_URI=sqlite:///.lakebranch/catalog.db   # local SQLite catalog (git-ignored)
WAREHOUSE=data/warehouse
```

### 3. Run the pipeline

```bash
python -m src.lakebranch.write_iceberg
# ...or the installable CLI:
lakebranch pipeline
```

Expected output (abbreviated):

```
[fs] Ensured warehouse directory: data/warehouse
[iceberg] Ensuring table 'db.events' exists
[iceberg] Table 'db.events' ready.
[iceberg] Appending 3 sample event rows
[iceberg] Data appended successfully.
[iceberg] Scanning table 'db.events'

Query result (3 rows):
   event_id event_type              timestamp
0         1      login  2026-07-31T10:00:00Z
1         2   purchase  2026-07-31T10:05:00Z
2         3     logout  2026-07-31T10:10:00Z

[done] All operations completed successfully.
```

The same pipeline code works unchanged — only the catalog/storage profile selection differs. The `lakebranch init-demo`, GUI, run-logging, and Airflow provider all work with this profile too.

> **Note:** The SQLite catalog is a **single-user, file-based catalog** — no network, no server. It is perfect for local dev, tests, and CI. For production or multi-writer scenarios, use the Nessie profile (see [Quick Start](#quick-start)).

## Nessie UI (Catalog Explorer)

Nessie 0.104.x ships with a built-in **Web UI** — the "Nessie Repository Manager" — served by the Nessie server itself. **No extra container is needed.** Open it at:

```
http://localhost:19120/
```

The Nessie UI shows **catalog metadata only** — it is a *Catalog Explorer*, not a data browser or query runner. You can browse:

- **Namespaces** (e.g., `db`)
- **Tables** (e.g., `db.events`) and their schemas
- **Snapshots** for each table
- **Git-like branches & commits** — Nessie's versioned history of catalog changes

The UI works with **all storage profiles** (SeaweedFS, MinIO, AWS S3), because it talks to the Nessie REST API on port `19120`, which is independent of the underlying object store. To explore the data files themselves, use the **MinIO console** (see Storage Profiles) or your preferred Iceberg query engine.

## Pipeline Run Logging

Lakebranch ships a **lightweight run-logging (telemetry) layer** that records every pipeline run's history and status to a local **DuckDB** database. It is *not* a DAG orchestrator — see the note below.

### What it records

Each pipeline execution writes one row to the `lakebranch_runs` table with:

| Column | Description |
|--------|-------------|
| `id` | Auto-incrementing run ID |
| `started_at` / `finished_at` | UTC timestamps for the run |
| `pipeline` | Pipeline name (e.g., `write_iceberg`) |
| `profile` | Storage profile used (`seaweedfs`, `minio`, `aws-s3`, …) |
| `warehouse` | Warehouse name (e.g., `warehouse`) |
| `status` | `success` or `failed` |
| `rows_written` | Number of rows in the query result at the end of the run |
| `duration_ms` | Run duration in milliseconds |
| `error` | Exception message if the run failed, otherwise `NULL` |

### Where the database lives

The run log is a single DuckDB file at **`.lakebranch/runs.duckdb`** (created automatically, and git-ignored). Because it's a local file, you can inspect run history even when the Docker containers are **down** — reading the run log never contacts Nessie, SeaweedFS, or any other service.

### How to view recent runs

```bash
python -m src.lakebranch.runs
```

This prints the 10 most recent runs as a pandas-formatted table:

```
Recent pipeline runs (2 shown):
  id           started_at          finished_at      pipeline    profile  warehouse    status  rows_written  duration_ms  error
   1  2026-08-02 15:44:10  2026-08-02 15:44:11  write_iceberg  seaweedfs  warehouse   success             3          1234   None
   2  2026-08-02 15:45:02  2026-08-02 15:45:03  write_iceberg  seaweedfs  warehouse   success             6          1102   None
```

The `write_iceberg` pipeline uses the logger internally via a context manager; the logging itself is silent (all existing console output is unchanged).

> **Important — this is telemetry, not orchestration.** The run logger records *what happened* after the fact. It does **not** schedule, chain, retry, or manage dependencies between runs — that would be a DAG orchestrator, which Lakebranch deliberately does not include. Airflow remains a swappable *external* execution layer (see [Orchestration (Airflow)](#orchestration-airflow)); Lakebranch provides the run log that Airflow-driven pipelines write to. Failed runs are recorded with `status=failed` and the exception message in `error`; the exception is still raised to the caller as normal.

## SQL Query Engine (DuckDB)

Lakebranch bundles a **SQL query engine** (`src/lakebranch/sql.py`) that runs real SQL over the catalog's Iceberg tables via **DuckDB** — plain `SELECT`, `JOIN`s across tables, `GROUP BY` aggregates, subqueries, and anything else DuckDB supports. It is **Docker-independent**: it works with both catalog profiles (`nessie` / `sqlite`) and every storage profile (`seaweedfs` / `minio` / `aws-s3` / `filesystem`), because it loads each table's current snapshot via PyIceberg's catalog abstraction — no DuckDB `iceberg` extension, no S3 credential plumbing.

Each Iceberg table is registered as a DuckDB view under two names:

- A **sanitized view name** — `db.events` → `db_events` (the canonical name for SQL)
- A **quoted, dotted alias** — `"db.events"`, so `SELECT * FROM "db.events"` also works

### Run from the CLI

```bash
lakebranch sql "SELECT event_type, COUNT(*) AS n FROM db_events GROUP BY 1 ORDER BY 1"
# ...or as a module:
python -m src.lakebranch.sql "SELECT u.email, COUNT(o.order_id) AS orders FROM db_users u LEFT JOIN db_orders o ON u.user_id = o.user_id GROUP BY u.email"
```

Pass `--limit N` to cap the number of result rows (default: 1000). The engine also drives the GUI's **SQL** panel and the `POST /api/sql` endpoint, so the quickstart supports SQL out of the box — Docker-free included.

## Nessie Branch Management (undo/redo for data)

Nessie's Git-like versioning of the catalog is exposed in the GUI as a **Branches** panel. A new client module — `src/lakebranch/nessie.py` — talks to Nessie's REST **v2 tree API** (`/api/v2/trees`), which is *separate* from the Iceberg REST endpoint that PyIceberg uses (PyIceberg's `RestCatalog` has no branch APIs). It can:

- **List** every branch and tag in the repository, plus the currently selected branch (`GET /api/branches`)
- **Create** a branch from an existing branch/tag — the "undo/redo" enabler: fork before a destructive write, experiment, then merge back or delete (`POST /api/branches`)
- **Merge** one branch into another (`POST /api/branches/merge`)
- **Delete** a branch (`DELETE /api/branches/{name}`)

Branch management requires the Nessie catalog profile (`CATALOG_PROFILE=nessie`, the default). On the Docker-free SQLite catalog (which has no branches/tags) the branch APIs return a clear 400. The client is dependency-light (`requests`) and injectable, so the whole feature is tested Docker-free with a fake HTTP session (`tests/test_nessie.py`, `tests/test_api_branches.py`).

## Lakebranch GUI (Developer Preview)

Lakebranch ships a **web-based developer preview** — a FastAPI backend + a single-page static UI that makes the lakehouse explorable *and writable* in the browser: tables, row previews, time travel, snapshot diffs, a query runner, CSV/Parquet/JSON import, and run history. It is intentionally minimal and clearly marked as a dev preview: no auth, no user management, no production hardening.

> **Open-source note:** the GUI is part of the Apache 2.0 core — FastAPI + a single-page static UI, both open and free.

### What it shows

- **Table list** — all namespaces and tables in the Nessie REST catalog (`GET /api/tables`)
- **Table detail** — schema, metadata (location, snapshots, properties), and a preview of the first 100 rows (`GET /api/tables/{table}` and `GET /api/tables/{table}/rows`)
- **Time Travel** — Lakebranch's signature feature: pick a past Iceberg snapshot and view the table as it was then (`GET /api/tables/{table}/rows?snapshot_id=…`). No other local OSS tool exposes Iceberg snapshot history in a UI.
- **Snapshot Diff** — compare two snapshots and see exactly which rows were added/removed between them (`GET /api/tables/{table}/diff?from_snapshot_id=…&to_snapshot_id=…`)
- **Query runner** — run an Iceberg scan with a SQL-like row filter (`POST /api/query`, e.g. `event_id > 1` or `event_type = 'login'`)
- **SQL query runner** — run arbitrary SQL (JOINs, GROUP BY, subqueries) over **every** table in the catalog via DuckDB (`POST /api/sql`). Tables are exposed as sanitized views (`db.events` → `db_events`) and quoted dotted aliases (`"db.events"`)
- **Branches** — manage Nessie's Git-like branch/tag versioning: fork a branch before destructive writes (the "undo/redo for data" story), merge it back, or delete it (`GET`/`POST /api/branches`, `POST /api/branches/merge`, `DELETE /api/branches/{name}`). Requires the Nessie catalog profile; degrades to a clear 400 on the SQLite profile
- **Import Data** — upload a CSV/Parquet file or paste JSON rows and write them to a table (`append` / `overwrite`), creating the table automatically (schema inferred) if it does not exist. Writes are recorded in the run log (`POST /api/tables/{table}/data`, `POST /api/tables/{table}/rows`, `POST /api/namespaces`)
- **Recent runs** — the pipeline run-log entries from [Pipeline Run Logging](#pipeline-run-logging) (`GET /api/runs`)

### Install

The GUI dependencies are **isolated** in `requirements-gui.txt` (they are *not* added to the core `requirements.txt`):

```bash
pip install -r requirements.txt      # core (already needed)
pip install -r requirements-gui.txt  # GUI-only: fastapi + uvicorn
```

### Run

Start the Docker stack (SeaweedFS + Nessie), then from the project root:

```bash
uvicorn src.lakebranch.api.app:app --port 8787
```

Open the UI at **http://localhost:8787/ui/** (the root `/` redirects there). Swagger/OpenAPI docs are at **http://localhost:8787/docs**.

Verify the API directly:

```bash
curl http://localhost:8787/api/tables   # tables from Nessie
curl http://localhost:8787/api/runs     # run-log entries (requires the run-logging layer)
```

### API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tables` | List namespaces + tables via the Nessie REST catalog |
| `GET` | `/api/tables/{table}` | Table schema + metadata + snapshot history |
| `GET` | `/api/tables/{table}/rows?limit=100` | Scan first N rows → pandas → JSON |
| `GET` | `/api/tables/{table}/rows?snapshot_id=…` | **Time travel** — scan the table as it was at a past Iceberg snapshot |
| `GET` | `/api/tables/{table}/diff?from_snapshot_id=…&to_snapshot_id=…` | **Snapshot diff** — rows added/removed between two snapshots |
| `POST` | `/api/query` | Run an Iceberg scan with a filter expression (body: `{"table": "db.events", "filter": "event_id > 1", "limit": 100}`) |
| `POST` | `/api/sql` | Run arbitrary SQL (JOINs, GROUP BY, subqueries) over every Iceberg table via DuckDB (body: `{"query": "SELECT event_type, COUNT(*) AS n FROM db_events GROUP BY 1", "limit": 1000}`). Returns the result rows/columns plus the view-name → table-id mapping |
| `GET` | `/api/branches` | List every Nessie branch/tag and the currently selected branch (`CATALOG_PROFILE=nessie`) |
| `POST` | `/api/branches` | Create a Nessie branch from an existing branch/tag — the "undo/redo for data" enabler (body: `{"name": "experiment", "from_ref": "main"}`) |
| `POST` | `/api/branches/merge` | Merge a source branch into a target (body: `{"source": "experiment", "target": "main"}`) |
| `DELETE` | `/api/branches/{name}` | Delete a Nessie branch |
| `POST` | `/api/namespaces` | Create a namespace (idempotent) |
| `POST` | `/api/tables/{table}/rows` | Write JSON rows (append/overwrite) — creates the table (schema inferred) if missing |
| `POST` | `/api/tables/{table}/data` | Upload a CSV/Parquet file and append/overwrite — creates the table if missing (multipart: `file`, `mode`) |
| `GET` | `/api/runs` | Recent run-log entries (delegates to `src.lakebranch.runs.recent_runs()`) |

## Orchestration (Airflow)

Airflow is an **optional, swappable execution layer** for Lakebranch — it is *not* embedded in the core. Lakebranch provides the building blocks (profile-aware config, a storage abstraction, PyIceberg wiring) and Airflow supplies scheduling, retries, dependencies, and observability on top.

### Start the Airflow stack

```bash
docker compose -f docker/docker-compose.airflow.yml up -d --build
```

This starts a standalone Airflow 2.x stack (Postgres for the metadata DB, Redis as the Celery broker, and the webserver, scheduler, worker, and triggerer components), builds a Lakebranch-aware Airflow image, and binds the project root to `/opt/lakebranch` so DAGs can `from src.lakebranch.* import ...`.

Open the Airflow web UI at **http://localhost:8080** — credentials: **admin / admin**.

> **Note:** The Airflow compose file is self-contained (it brings its own Postgres + Redis), but the demo DAG talks to the Lakebranch *data plane* — start **SeaweedFS + Nessie** first with `docker compose -f docker/docker-compose.yml --env-file .env up -d`.

### The demo DAG: `lakebranch_demo`

A reference DAG lives at `docker/airflow/dags/lakebranch_demo_dag.py`. It is intentionally minimal and well-commented so you can copy the pattern:

| Task | What it does |
|------|--------------|
| `ensure_warehouse` | Calls the storage provider's `ensure_warehouse()` to make sure the warehouse (bucket/directory) exists |
| `append_events` | Loads config, gets the `db.events` table via PyIceberg (creating it if needed), and appends 3 sample rows |
| `verify_rows` | Scans the table back and pushes the row count to Airflow XCom / task logs |

The DAG runs on a daily schedule (`@daily`). Trigger it manually from the Airflow UI (play button on the `lakebranch_demo` row) or via the CLI:

```bash
docker compose -f docker/docker-compose.airflow.yml exec airflow-scheduler \
  airflow dags trigger lakebranch_demo
```

### Integration philosophy

- **Airflow is external and swappable.** The DAG is plain Python that imports the same `src.lakebranch` APIs as the CLI pipeline — nothing in the Lakebranch core knows about Airflow.
- **Lakebranch provides the wiring.** `load_config()`, `get_provider()`, and the PyIceberg catalog helpers are the reference pattern; new DAGs copy them rather than re-implementing storage/catalog logic.
- **No vendor lock-in.** If you prefer Prefect, Dagster, or plain `cron`, the same `src.lakebranch` APIs work unchanged — the DAG layer is thin by design.

### Lakebranch Airflow Provider (standalone package)

[`airflow-providers-lakebranch/`](airflow-providers-lakebranch/) is a **standalone, optional** package (outside the Apache 2.0 core) that makes *"write to Iceberg via Lakebranch"* a **one-operator DAG**. It ships `LakebranchWriteOperator` (`table_name`, `mode` — `append`/`overwrite`, `data`) and `LakebranchHook`, which wrap the same `load_config()` / `get_provider()` / PyIceberg catalog APIs as the reference DAG.

**A 3-line DAG:**

```python
from airflow import DAG
from airflow.utils.dates import days_ago
from lakebranch_provider import LakebranchWriteOperator

with DAG(dag_id="write_events_demo", schedule="@daily", start_date=days_ago(1), catchup=False) as dag:
    write = LakebranchWriteOperator(
        task_id="write_events",
        table_name="db.events",
        mode="append",
        data=[{"event_id": 4, "event_type": "signup", "timestamp": "2026-08-01T12:00:00Z"}],
    )
```

**Install:**

```bash
pip install -e ./airflow-providers-lakebranch
```

In the Airflow Docker image the provider is **zero-install**: the repo root is bind-mounted at `/opt/lakebranch` and the image sets `PYTHONPATH=/opt/lakebranch:/opt/lakebranch/airflow-providers-lakebranch`, so every container can `import lakebranch_provider` immediately. (Importable via PYTHONPATH, but not registered on Airflow's Providers page — entry points only apply to pip-installed providers.)

The provider demo DAG appears in the UI as `lakebranch_provider_demo` (write + verify). See `airflow-providers-lakebranch/README.md` for the full guide.

> **Open-source note:** the provider is Apache 2.0, packaged separately from the core so it can version and release independently.

## Storage Profiles

Lakebranch supports multiple object storage backends via the `STORAGE_PROFILE` environment variable in `.env`. The S3 API is the abstraction boundary — switching backends requires **zero changes** to your pipeline code.

| Profile | Backend | Compose File | License | Use Case |
|---------|---------|--------------|---------|----------|
| `seaweedfs` (default) | SeaweedFS | `docker/docker-compose.yml` | Apache 2.0 | Local development (default) |
| `minio` | MinIO | `docker/docker-compose.minio.yml` | AGPLv3 | Local development (prefer MinIO web console) |
| `aws-s3` | AWS S3 | `docker/docker-compose.prod-s3.yml` | — | Production / BYOC |
| `gcs` | Google Cloud Storage | — | — | Cloud (not yet implemented) |
| `adls` | Azure Data Lake Storage Gen2 | — | — | Cloud (not yet implemented) |
| `filesystem` | Local filesystem | — | — | Embedded / testing |

> **Visualization:** For a data preview (schema, first N rows, query runner) covering **all** storage profiles, use the **Lakebranch GUI** at [http://localhost:8787/ui/](http://localhost:8787/ui/) (see [Lakebranch GUI (Developer Preview)](#lakebranch-gui-developer-preview)). For catalog metadata (namespaces, tables, snapshots, branches/commits), use the **Nessie UI** at [http://localhost:19120](http://localhost:19120). For browsing the *data files* themselves, MinIO offers a web console at [http://localhost:9001](http://localhost:9001) (via `docker-compose.minio.yml`); the default SeaweedFS profile has no object-store file browser.

### SeaweedFS (default)

```bash
docker compose -f docker/docker-compose.yml --env-file .env up -d
```

SeaweedFS is **Apache 2.0 licensed**, making it the safest default for local development. It runs master + volume + S3 gateway in a single process. S3 credentials are configured via `docker/seaweedfs/s3.json` (mounted read-only).

### MinIO (alternative)

```bash
docker compose -f docker/docker-compose.minio.yml --env-file .env up -d
```

MinIO offers a polished web console at [http://localhost:9001](http://localhost:9001) (default credentials: `minioadmin` / `minioadmin`). Note that MinIO is **AGPLv3 licensed** — fine for local development, but review licensing implications before using it in a hosted/SaaS product.

### AWS S3 (production / BYOC)

```bash
docker compose -f docker/docker-compose.prod-s3.yml up -d
```

The **BYOC (Bring Your Own Cloud)** template runs Nessie only — no object-store container. Nessie points directly at AWS S3. Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `S3_BUCKET` in your environment. The S3 bucket must already exist.

## Storage & Catalog Flexibility

### How does the storage abstraction layer work?

Lakebranch ships a clean storage abstraction layer in `src/lakebranch/storage/` that decouples pipeline code from the underlying object store. The architecture:

```
┌──────────────────────────────────────────────┐
│         Lakebranch Pipeline (write_iceberg)    │
└────────────────────┬─────────────────────────┘
                     │ load_config() + get_provider() + init_catalog()
┌────────────────────▼─────────────────────────┐
│         Storage Abstraction Layer            │
│   src/lakebranch/storage/                      │
│   ├── base.py       → StorageProvider        │
│   ├── factory.py    → get_provider()         │
│   ├── s3_compat.py  → SeaweedFS/MinIO/AWS    │
│   ├── filesystem.py → Local filesystem       │
│   └── (gcs/adls)    → Not yet implemented    │
└────────────────────┬─────────────────────────┘
                     │ S3 API / local path
┌────────────────────▼─────────────────────────┐
│  Catalog (selected via CATALOG_PROFILE)      │
│  ├── Nessie REST Catalog (:19120)   [nessie] │
│  └── SQLite Catalog (local file)    [sqlite] │
└──────────────────────────────────────────────┘
```

Every backend implements the `StorageProvider` protocol with two methods:

| Method | Purpose |
|--------|---------|
| `ensure_warehouse()` | Creates the warehouse (bucket/directory) if it does not exist |
| `catalog_properties()` | Returns the PyIceberg catalog kwargs for this backend |

The `STORAGE_PROFILE` environment variable selects the backend at runtime — switching between SeaweedFS, MinIO, AWS S3, or a local filesystem requires **zero changes** to your pipeline code.

### Does Lakebranch require AWS S3?

**No.** Lakebranch does **not** require an AWS S3 bucket. The default iteration uses **SeaweedFS**, a self-hosted, S3-compatible object store running locally via Docker. SeaweedFS speaks the same S3 API as AWS S3, so the Iceberg stack treats it identically to a cloud S3 bucket — but everything stays on your machine.

### Can I use a different storage backend?

Yes, with some configuration changes. Iceberg separates the **catalog** (metadata) from the **storage** (data files). Lakebranch's default stack uses:

- **Catalog:** Nessie (Iceberg REST catalog) — or SQLite (`CATALOG_PROFILE=sqlite`) for a Docker-free stack
- **Storage:** SeaweedFS (S3-compatible object storage) — or the local filesystem (`STORAGE_PROFILE=filesystem`)

You can swap out the storage layer for other S3-compatible or cloud options:

| Storage Option | Type | How to Use | Profile |
|----------------|------|------------|---------|
| **SeaweedFS** (default) | Local, S3-compatible | Already configured — no changes needed | `seaweedfs` |
| **MinIO** | Local, S3-compatible | Use `docker-compose.minio.yml` — no code changes | `minio` |
| **AWS S3** | Cloud, S3-native | Use `docker-compose.prod-s3.yml` — no code changes | `aws-s3` |
| **Google Cloud Storage (GCS)** | Cloud, S3-compatible | Use the GCS S3 interoperability endpoint (`https://storage.googleapis.com`) with GCS HMAC keys | `gcs` (planned) |
| **Azure Blob Storage** | Cloud, S3-compatible | Use the Azure Blob S3-compatible endpoint with Azure storage account credentials | `adls` (planned) |
| **Local filesystem** | Local, non-S3 | Set `CATALOG_PROFILE=sqlite` + `STORAGE_PROFILE=filesystem` for a Docker-free stack; catalog metadata lives in a local `catalog.db` and data in `FS_PATH` | `filesystem` |

### Can I use a local database instead of Nessie?

Yes. Nessie is one of several Iceberg catalog implementations. PyIceberg supports multiple catalog types:

| Catalog | Profile | Type | Notes |
|---------|---------|------|-------|
| **Nessie** (default) | `nessie` | REST catalog with Git-like versioning | Already configured — no changes needed |
| **SQLite** | `sqlite` | Local file-based catalog | Simple, single-user, no server needed; pairs with `STORAGE_PROFILE=filesystem` for a Docker-free stack |
| **PostgreSQL** | — | Database-backed catalog | Requires a running PostgreSQL instance |
| **Hive Metastore** | — | Traditional Hive catalog | Requires a Hive Metastore service |
| **Glue** | — | AWS-managed catalog | Requires AWS account |
| **In-memory** | — | Ephemeral catalog | Data lost on process exit; useful for testing only |

Switch catalogs by setting `CATALOG_PROFILE` in `.env` (`nessie` | `sqlite`); `src/lakebranch/catalog.py` routes to the right PyIceberg catalog automatically. The default setup is wired for Nessie + SeaweedFS as the simplest fully-local combination, and `sqlite` + `filesystem` as the Docker-free combination.

## Configuration

### Environment variables (`.env`)

All configuration is driven by the `.env` file at the project root:

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_PROFILE` | Object storage backend (`seaweedfs`, `minio`, `aws-s3`, `gcs`, `adls`, `filesystem`) | `seaweedfs` |
| `CATALOG_PROFILE` | Iceberg catalog backend (`nessie` \| `sqlite`) | `nessie` |
| `MINIO_ROOT_USER` | Object store root access key (also used by Nessie via AWS credentials) | `minioadmin` |
| `MINIO_ROOT_PASSWORD` | Object store root secret key (also used by Nessie via AWS credentials) | `minioadmin` |
| `NESSIE_URI` | Nessie REST catalog endpoint used by PyIceberg (profile: `nessie`) | `http://localhost:19120/iceberg/main` |
| `CATALOG_URI` | SQLAlchemy URI for the SQLite catalog DB (profile: `sqlite`) | `sqlite:///.lakebranch/catalog.db` |
| `WAREHOUSE` | Name of the warehouse (maps to the object store bucket or local directory) | `warehouse` |
| `S3_ENDPOINT` | S3 API endpoint used by PyIceberg/s3fs | `http://localhost:9000` |
| `S3_ACCESS_KEY` | S3 access key for PyIceberg/s3fs | `minioadmin` |
| `S3_SECRET_KEY` | S3 secret key for PyIceberg/s3fs | `minioadmin` |
| `S3_BUCKET` | Object store bucket backing the warehouse | `warehouse` |

> **Security:** Do not commit `.env` to version control if it contains real secrets. The `.gitignore` file excludes it.

### Quarkus/S3 environment variables for Nessie (`docker-compose.yml`)

Nessie runs as a Quarkus application and needs server-side S3 configuration to manage table locations. The relevant environment variables in `docker/docker-compose.yml` are:

| Environment Variable | Purpose |
|----------------------|---------|
| `AWS_ACCESS_KEY_ID` | S3 access key (set from `${MINIO_ROOT_USER}`) |
| `AWS_SECRET_ACCESS_KEY` | S3 secret key (set from `${MINIO_ROOT_PASSWORD}`) |
| `AWS_REGION` | AWS region (set to `us-east-1`) |

These are consumed by Nessie's Quarkus catalog service via `JDK_JAVA_OPTIONS` system properties:

| System Property | Purpose |
|-----------------|---------|
| `-Dnessie.catalog.default-warehouse=warehouse` | Sets the default warehouse name |
| `-Dnessie.catalog.warehouses.warehouse.location=s3://warehouse` | Maps the warehouse to the `warehouse` bucket in SeaweedFS |
| `-Dnessie.catalog.service.s3.default-options.endpoint=http://seaweedfs:9000` | Internal S3 endpoint (container-to-container) |
| `-Dnessie.catalog.service.s3.default-options.external-endpoint=http://host.docker.internal:9000` | External S3 endpoint told to client SDKs (pyiceberg). `host.docker.internal` is reachable both from the host CLI and from Airflow containers |
| `-Dnessie.catalog.service.s3.default-options.path-style-access=true` | Enables path-style addressing (required for SeaweedFS/MinIO) |
| `-Dnessie.catalog.service.s3.default-options.auth-type=APPLICATION_GLOBAL` | Uses the default AWS credentials provider chain, picking up `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from the environment |

## Project Structure

```
Lakebranch/
├── .env                          # Environment variables (not committed)
├── .env.example                  # Commit-safe env template (all profiles)
├── .gitattributes                # Line-ending normalization (Windows/macOS/Linux)
├── .github/                      # CI workflow, issue templates, PR template
├── .gitignore                    # Git ignore rules
├── .promptignore                 # AI assistant context exclusions
├── CHANGELOG.md                  # Keep-a-Changelog changelog
├── CODE_OF_CONDUCT.md            # Contributor Covenant
├── CONTRIBUTING.md               # Contribution guide
├── LICENSE                       # Apache License 2.0
├── README.md                     # This file
├── SECURITY.md                   # Vulnerability reporting + threat model
├── pyproject.toml                # Core package metadata + `lakebranch` CLI entry point
├── requirements.txt              # Python dependencies
├── requirements-gui.txt          # GUI-only dependencies (fastapi + uvicorn)
├── tests/                        # Test suite (run with `pytest`)
├── airflow-providers-lakebranch/   # Standalone Airflow provider package
│   ├── pyproject.toml            # apache-airflow-providers-lakebranch package
│   ├── README.md                 # Provider install / usage / license guide
│   └── lakebranch_provider/
│       ├── __init__.py           # Operator + hook exports, provider metadata
│       ├── hooks/lakebranch.py     # LakebranchHook (config + storage + PyIceberg)
│       ├── operators/lakebranch.py # LakebranchWriteOperator (append / overwrite)
│       └── example_dags/
│           └── lakebranch_provider_demo.py  # Provider demo DAG (write + verify)
├── docker/
│   ├── docker-compose.yml        # SeaweedFS + Nessie (default dev profile)
│   ├── docker-compose.minio.yml  # MinIO + Nessie (alternative profile)
│   ├── docker-compose.prod-s3.yml# Nessie + AWS S3 (production / BYOC template)
│   ├── docker-compose.airflow.yml# Optional Airflow orchestration profile
│   ├── airflow/
│   │   ├── Dockerfile            # Airflow image with Lakebranch deps + provider PYTHONPATH
│   │   └── dags/
│   │       ├── lakebranch_demo_dag.py          # Reference demo DAG
│   │       └── lakebranch_provider_demo.py     # Re-export wrapper for the provider demo DAG
│   └── seaweedfs/
│       └── s3.json               # SeaweedFS S3 credentials config
└── src/
    ├── __init__.py               # Source root package
    └── lakebranch/
        ├── __init__.py           # Lakebranch package
        ├── api/                  # GUI API (developer preview)
        │   ├── __init__.py       # GUI API package
        │   └── app.py            # FastAPI app (tables, rows, diff, query, runs; :8787)
        ├── ui/                   # Static GUI (developer preview)
        │   └── index.html        # Single-page UI (no build step)
        ├── cli.py                # `lakebranch` CLI (up/down/pipeline/runs/ui/init-demo/sql)
        ├── config.py             # Profile-aware config loader
        ├── catalog.py            # Shared catalog helpers (init_catalog / ensure_namespace / ensure_table)
        ├── init_demo.py          # Multi-table demo dataset loader
        ├── runs.py               # Pipeline run-log (telemetry) layer
        ├── sql.py                # DuckDB SQL-over-Iceberg engine (lakebranch sql / POST /api/sql)
        ├── nessie.py             # Nessie REST v2 tree-API client (branches/tags: list/create/merge/delete)
        ├── write_iceberg.py      # End-to-end writer/query script
        └── storage/
            ├── __init__.py       # Storage abstraction exports
            ├── base.py           # StorageProvider protocol
            ├── factory.py        # get_provider() dispatcher
            ├── s3_compat.py      # SeaweedFS / MinIO / AWS S3 provider
            └── filesystem.py     # Local filesystem provider
```

## Stopping the Services

To stop the containers:

```bash
docker compose -f docker/docker-compose.yml down
```

To stop and remove the SeaweedFS data volume (destroys all table data):

```bash
docker compose -f docker/docker-compose.yml down -v
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Connection refused` on port `19120` | Nessie not yet healthy | Wait a few seconds and check `docker compose ps` |
| `Connection refused` on port `9000` | SeaweedFS not yet healthy | Wait for SeaweedFS healthcheck to pass |
| `NoSuchBucket` errors | `warehouse` bucket missing | The script auto-creates it; ensure SeaweedFS is reachable first |
| Credential errors from Nessie | `.env` credentials changed after containers started | Restart containers: `docker compose -f docker/docker-compose.yml --env-file .env up -d --force-recreate` |
| Port conflicts | Another service on `9000`, `9333`, `8080`, or `19120` | Change the host port mapping in `docker-compose.yml` |
| `Connection refused` on port `8787` | Lakebranch GUI server not running | Start it: `uvicorn src.lakebranch.api.app:app --port 8787` |
| `ModuleNotFoundError: No module named 'fastapi'` | GUI dependencies not installed | Run `pip install -r requirements-gui.txt` |
| `502`/`422` errors on `/api/tables/{table}/rows` or `/api/query` | Nessie advertises an S3 endpoint unreachable from the host (e.g. `host.docker.internal:9000`) | Verify the Nessie `external-endpoint` in `docker-compose.yml` is reachable from the host (e.g. `localhost:9000`) |

## Licensing

Lakebranch is **fully open source** under the **Apache License 2.0** — a permissive, business-friendly license that maximizes adoption. This applies to the entire project: the Python core, the FastAPI GUI, the Docker Compose profiles, the Airflow provider package, and the documentation. See the [LICENSE](LICENSE) file for the full license text.

### Third-Party Component Licenses

| Component | License |
|-----------|---------|
| **SeaweedFS** | Apache 2.0 |
| **Nessie** | Apache 2.0 |
| **PyIceberg** | Apache 2.0 |
| **MinIO** (optional profile) | AGPLv3 — fine for local development, review before hosted/SaaS use |
| **DuckDB** | MIT |
| **Polars / PyArrow** | Apache 2.0 |
| **FastAPI** (GUI, `requirements-gui.txt`) | MIT |
| **Uvicorn** (GUI, `requirements-gui.txt`) | BSD-3-Clause |
