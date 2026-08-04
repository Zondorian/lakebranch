# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned

- GUI: write support (upload CSV/Parquet, append/overwrite) — currently read-only
- GUI: Nessie branch management (create/merge branches)
- Bundled query engine (e.g. DuckDB via pyiceberg) so quickstart supports SQL out of the box
- GCS and ADLS storage profiles
- SQLite / PostgreSQL catalog support

## [0.1.0] - 2026-08-04

### Added

- **Local-first Iceberg stack**: a single `docker compose` command brings up Nessie (Iceberg REST catalog) + SeaweedFS (S3-compatible object store), all on your machine.
- **Installable core**: `pyproject.toml` + `pip install -e .` with the `lakebranch` CLI (`up` / `down` / `pipeline` / `runs` / `ui` / `init-demo`).
- **End-to-end pipeline** (`lakebranch pipeline`): idempotent create/append/query on `db.events`.
- **Demo dataset loader** (`lakebranch init-demo`): realistic multi-table sample data (users, orders, events).
- **Storage abstraction layer**: swap SeaweedFS / MinIO / AWS S3 (BYOC) / local filesystem via `STORAGE_PROFILE` with zero code changes.
- **GUI (developer preview)**: FastAPI + single-page UI with table list, row previews, a filter-based query runner, recent runs, **Time Travel** (scan at a past Iceberg snapshot) and **Snapshot Diff** (added/removed rows between snapshots).
- **Run-logging (telemetry) layer**: every pipeline run recorded to a local DuckDB file (`.lakebranch/runs.duckdb`), viewable even when the Docker stack is down.
- **Airflow provider package** (`airflow-providers-lakebranch`): one-operator DAG (`LakebranchWriteOperator`) + `LakebranchHook`, plus a reference demo DAG.
- **Test suite** (`pytest`): 18 tests covering config, run-log, storage factory, CLI, and API serialization. Docker not required for tests.