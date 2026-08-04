# CLAUDE.md — Lakebranch

> This file gives AI coding assistants (Cline, Claude Code, etc.) a fast mental model of **what Lakebranch is** and **where it's headed**. It auto-loads at the start of every session. The `README.md` is the source of technical truth — read it for details; this file is the compressed orientation.

## What Lakebranch is

A **local, self-contained Apache Iceberg data lake stack** built on **Nessie** (Iceberg REST catalog) and **SeaweedFS** (S3-compatible object storage). It runs a full end-to-end write/query pipeline entirely on the developer's machine — no cloud accounts, no external services.

**Fully open source (Apache 2.0):** the entire project — core, GUI, Docker profiles, and Airflow provider — is Apache 2.0. Adoption first.

## Architecture (in 5 lines)

- **PyIceberg** (Python client) → **Nessie REST catalog** (`:19120`, Git-like versioning of table metadata) → **SeaweedFS** S3 endpoint (`:9000`, physically stores Parquet/manifests/metadata in the `warehouse` bucket).
- **Storage abstraction layer** (`src/lakebranch/storage/`): a `StorageProvider` protocol (`ensure_warehouse()`, `catalog_properties()`) — swapping SeaweedFS ↔ MinIO ↔ AWS S3 requires **zero pipeline code changes** (selected via `STORAGE_PROFILE` in `.env`; `filesystem` profile exists too).
- **Run-logging (telemetry, not orchestration):** every pipeline run records one row to a local DuckDB file `.lakebranch/runs.duckdb` (`status`, `rows_written`, `duration_ms`, `error`, …). Usable even when Docker containers are down.
- **GUI (developer preview):** FastAPI app (`:8787`) + single-page static UI (`src/lakebranch/ui/index.html`) — tables, row previews, time travel, snapshot diffs, a filter-based query runner, and recent runs. Fully Apache 2.0.
- **Airflow is external and swappable:** Lakebranch provides the wiring (`load_config()`, `get_provider()`, PyIceberg catalog helpers); DAGs are thin and plain-Python. A standalone provider package (`airflow-providers-lakebranch/`) adds a `LakebranchWriteOperator`.

## Current state (what's built)

- Python CLI pipeline `src/lakebranch/write_iceberg.py` (idempotent create/append/query on `db.events`)
- Installable core (`pip install -e .`) with `lakebranch` CLI (`up` / `down` / `pipeline` / `runs` / `ui` / `init-demo`)
- Demo dataset loader `src/lakebranch/init_demo.py` (users, orders, events — multi-table)
- Test suite (`tests/`, run with `pytest`) — config, run-log, storage factory, CLI, API serialization
- Nessie + SeaweedFS + MinIO + AWS S3 (BYOC) Docker Compose profiles
- DuckDB run-logging layer (`python -m src.lakebranch.runs`)
- FastAPI GUI dev preview with **Time Travel** (scan at a past snapshot) and **Snapshot Diff** (added/removed rows between snapshots)
- Airflow reference DAG + standalone provider package with demo DAG
- Profile-aware config loader (`src/lakebranch/config.py`)

## Plans / Roadmap

The README's [CHANGELOG](CHANGELOG.md) tracks the full roadmap. Near-term priorities:

- [ ] GUI: add write support (upload CSV/Parquet, append/overwrite) — today it is read-only
- [ ] GUI: add Nessie branch management (create/merge branches — the "undo/redo for data" story)
- [ ] Add a bundled query engine (e.g. DuckDB via pyiceberg) so quickstart supports SQL out of the box
- [ ] GCS and ADLS storage profiles (currently "planned" in README)
- [ ] SQLite / PostgreSQL catalog support (currently only Nessie is wired)

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
- **Licensing:** everything is Apache 2.0 — the core, the GUI, the Docker profiles, and the Airflow provider. No parts planned for closed-source re-licensing.

## Key file map

```
src/lakebranch/
├── write_iceberg.py        # End-to-end CLI pipeline (the reference pattern)
├── init_demo.py            # Multi-table demo dataset loader
├── cli.py                  # `lakebranch` CLI (up/down/pipeline/runs/ui/init-demo)
├── config.py               # Profile-aware config loader (load_config)
├── runs.py                 # DuckDB run-log (telemetry) layer
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