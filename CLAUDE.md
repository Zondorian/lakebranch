# CLAUDE.md — Lakebranch

> This file gives AI coding assistants (Cline, Claude Code, etc.) a fast mental model of **what Lakebranch is** and **where it's headed**. It auto-loads at the start of every session. The `README.md` is the source of technical truth — read it for details; this file is the compressed orientation.

## What Lakebranch is

A **local, self-contained Apache Iceberg data lake stack**. The default stack is built on **Nessie** (Iceberg REST catalog) and **SeaweedFS** (S3-compatible object storage), and a **Docker-free** profile (PyIceberg **SQLite catalog** + local filesystem storage) is also available. It runs a full end-to-end write/query pipeline entirely on the developer's machine — no cloud accounts, no external services, and (optionally) no containers at all.

**Fully open source (Apache 2.0):** the entire project — core, GUI, Docker profiles, and Airflow provider — is Apache 2.0. Adoption first.

## Architecture (in 5 lines)

- **PyIceberg** (Python client) → **catalog** (selected via `CATALOG_PROFILE`) → **storage** (selected via `STORAGE_PROFILE`). Default: **Nessie REST catalog** (`:19120`, Git-like versioning of table metadata) → **SeaweedFS** S3 endpoint (`:9000`, physically stores Parquet/manifests/metadata in the `warehouse` bucket). Docker-free: **SQLite catalog** (local `.db` file via `CATALOG_URI`) → **local filesystem** (`FS_PATH`).
- **Storage abstraction layer** (`src/lakebranch/storage/`): a `StorageProvider` protocol (`ensure_warehouse()`, `catalog_properties()`) — swapping SeaweedFS ↔ MinIO ↔ AWS S3 requires **zero pipeline code changes** (selected via `STORAGE_PROFILE` in `.env`; `filesystem` profile exists too).
- **Catalog abstraction** (`src/lakebranch/catalog.py`): `init_catalog()` routes to Nessie (`nessie`, default) or PyIceberg's SQLite catalog (`sqlite`) based on `CATALOG_PROFILE`. The SQLite catalog pairs with `STORAGE_PROFILE=filesystem` for a fully Docker-free stack.
- **Run-logging (telemetry, not orchestration):** every pipeline run records one row to a local DuckDB file `.lakebranch/runs.duckdb` (`status`, `rows_written`, `duration_ms`, `error`, …). Usable even when Docker containers are down.
- **GUI (developer preview):** FastAPI app (`:8787`) + single-page static UI (`src/lakebranch/ui/index.html`) — tables, row previews, time travel, snapshot diffs, a filter-based query runner, a full **SQL query runner** (JOINs/GROUP BY via DuckDB), **Nessie branch management** (create/merge/delete branches — the "undo/redo for data" story), CSV/Parquet upload + JSON row writes, and recent runs. Fully Apache 2.0.
- **Nessie tree-API client** (`src/lakebranch/nessie.py`): a thin `requests`-based client for Nessie's REST v2 tree API (`/api/v2/trees`) — lists branches/tags, creates branches, merges, and deletes. Separate from PyIceberg's Iceberg REST client (which has no branch APIs). Powers `GET/POST /api/branches`, `POST /api/branches/merge`, `DELETE /api/branches/{name}`, and the GUI Branches panel.
- **Bundled SQL engine** (`src/lakebranch/sql.py`): real SQL over the catalog's Iceberg tables via DuckDB — each table is registered as a sanitized view (`db.events` → `db_events`) plus its quoted dotted alias (`"db.events"`). Docker-independent: works with every catalog/storage profile. Exposed as `lakebranch sql`, `POST /api/sql`, and a GUI panel.
- **Airflow is external and swappable:** Lakebranch provides the wiring (`load_config()`, `get_provider()`, PyIceberg catalog helpers); DAGs are thin and plain-Python. A standalone provider package (`airflow-providers-lakebranch/`) adds a `LakebranchWriteOperator`.

## Current state (what's built)

- Python CLI pipeline `src/lakebranch/write_iceberg.py` (idempotent create/append/query on `db.events`)
- Installable core (`pip install -e .`) with `lakebranch` CLI (`up` / `down` / `pipeline` / `runs` / `ui` / `init-demo`)
- Demo dataset loader `src/lakebranch/init_demo.py` (users, orders, events — multi-table)
- Test suite (`tests/`, run with `pytest`) — config, run-log, storage factory, CLI, API serialization, plus Docker-free SQLite-catalog integration tests
- Nessie + SeaweedFS + MinIO + AWS S3 (BYOC) Docker Compose profiles
- DuckDB run-logging layer (`python -m src.lakebranch.runs`)
- FastAPI GUI dev preview with **Time Travel** (scan at a past snapshot), **Snapshot Diff** (added/removed rows between snapshots), a **SQL query runner** (DuckDB over every Iceberg table), and **Nessie branch management** (create/merge/delete branches in a dedicated Branches panel)
- **DuckDB SQL query engine** (`lakebranch sql` / `POST /api/sql`): real SQL (SELECT/JOIN/GROUP BY/subqueries) over the catalog's Iceberg tables, with a Docker-free test suite
- Airflow reference DAG + standalone provider package with demo DAG
- Profile-aware config loader (`src/lakebranch/config.py`) with `STORAGE_PROFILE` + `CATALOG_PROFILE`
- **Docker-free stack**: `STORAGE_PROFILE=filesystem CATALOG_PROFILE=sqlite` runs the entire pipeline with just `pip install` (no containers)

## Plans / Roadmap

The README's [CHANGELOG](CHANGELOG.md) tracks the full roadmap. Near-term priorities:

- [x] GUI: add write support (upload CSV/Parquet, append/overwrite) — done, via the Import Data panel + `POST /api/tables/{table}/data` / `POST /api/tables/{table}/rows` / `POST /api/namespaces`
- [x] SQLite catalog support — done, via `CATALOG_PROFILE=sqlite` (PyIceberg SQLite catalog); pairs with `STORAGE_PROFILE=filesystem` for a Docker-free stack
- [x] GUI: add Nessie branch management (create/merge branches — the "undo/redo for data" story) — done, via `src/lakebranch/nessie.py` (Nessie REST v2 tree API client) + `GET/POST /api/branches` / `POST /api/branches/merge` / `DELETE /api/branches/{name}` + a GUI Branches panel; tested with a fake HTTP session (Docker-free)
- [x] Add a bundled query engine (e.g. DuckDB via pyiceberg) so quickstart supports SQL out of the box — done, via `src/lakebranch/sql.py` + `lakebranch sql` CLI + `POST /api/sql` + GUI SQL panel
- [ ] GCS and ADLS storage profiles (currently "planned" in README)
- [ ] PostgreSQL catalog support (currently only Nessie + SQLite are wired)

## Commands & conventions

```bash
# Start the stack (SeaweedFS + Nessie), from project root
docker compose -f docker/docker-compose.yml --env-file .env up -d

# Install deps (inside .venv)
pip install -r requirements.txt          # core
pip install -r requirements-gui.txt      # GUI-only (fastapi + uvicorn)

# Run the pipeline (idempotent; appends 3 rows per run)
python -m src.lakebranch.write_iceberg
# ...or the installable CLI:
lakebranch pipeline

# Run the pipeline Docker-free (SQLite catalog + local filesystem, no containers)
STORAGE_PROFILE=filesystem CATALOG_PROFILE=sqlite lakebranch pipeline
# (PowerShell: $env:STORAGE_PROFILE='filesystem'; $env:CATALOG_PROFILE='sqlite')

# Run SQL over Iceberg tables (works with any catalog/storage profile, incl. Docker-free)
lakebranch sql "SELECT event_type, COUNT(*) FROM db_events GROUP BY 1"

# Load the multi-table demo dataset
lakebranch init-demo        # or: python -m src.lakebranch.init_demo

# View recent runs from the DuckDB log (works with Docker down)
python -m src.lakebranch.runs
# ...or: lakebranch runs

# Run the GUI (Time Travel + Snapshot Diff panels)
lakebranch ui               # UI at http://localhost:8787/ui/
# ...or: uvicorn src.lakebranch.api.app:app --port 8787

# Run the test suite
python -m pytest

# Airflow stack (optional, needs data plane up first)
docker compose -f docker/docker-compose.airflow.yml up -d --build
```

- **Python style:** src-layout (`src/lakebranch/`), package-relative imports, tests in `tests/` (run with `pytest`).
- **Env config:** never touch `.env` (git-ignored, secrets); edit `.env.example` for commit-safe changes.
- **Storage profile:** set `STORAGE_PROFILE` in `.env` (`seaweedfs` | `minio` | `aws-s3` | `filesystem`).
- **Catalog profile:** set `CATALOG_PROFILE` in `.env` (`nessie` | `sqlite`). For a Docker-free stack: `STORAGE_PROFILE=filesystem CATALOG_PROFILE=sqlite` → `lakebranch pipeline`.
- **Licensing:** everything is Apache 2.0 — the core, the GUI, the Docker profiles, and the Airflow provider. No parts planned for closed-source re-licensing.

## Key file map

```
src/lakebranch/
├── write_iceberg.py        # End-to-end CLI pipeline (the reference pattern)
├── init_demo.py            # Multi-table demo dataset loader
├── cli.py                  # `lakebranch` CLI (up/down/pipeline/runs/ui/init-demo/sql)
├── catalog.py              # Shared catalog helpers (init_catalog / ensure_namespace / ensure_table) — routes Nessie ↔ SQLite via CATALOG_PROFILE
├── config.py               # Profile-aware config loader (load_config; STORAGE_PROFILE + CATALOG_PROFILE)
├── runs.py                 # DuckDB run-log (telemetry) layer
├── sql.py                  # DuckDB SQL-over-Iceberg engine (run_sql; lakebranch sql + POST /api/sql)
├── nessie.py               # Nessie REST v2 tree-API client (branches/tags: list/create/merge/delete)
├── api/app.py              # FastAPI GUI backend (:8787)
├── ui/index.html           # Single-page GUI (no build step)
└── storage/
    ├── base.py             # StorageProvider protocol
    ├── factory.py          # get_provider() dispatcher
    ├── s3_compat.py        # SeaweedFS / MinIO / AWS S3
    └── filesystem.py       # Local filesystem provider

airflow-providers-lakebranch/           # Standalone Airflow provider package (Apache 2.0)
docker/
├── docker-compose.yml                # SeaweedFS + Nessie (default)
├── docker-compose.minio.yml          # MinIO + Nessie
├── docker-compose.prod-s3.yml        # Nessie + AWS S3 (BYOC)
├── docker-compose.airflow.yml        # Optional Airflow
└── airflow/dags/                     # lakebranch_demo_dag.py, lakebranch_provider_demo.py