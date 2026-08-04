# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Shared catalog helper module** (`src/lakebranch/catalog.py`): single source of truth for PyIceberg catalog bootstrap (`init_catalog`, `ensure_namespace`, `ensure_table`). Replaces the catalog logic previously duplicated across the CLI pipeline, demo loader, GUI API, and Airflow DAG/hook. New consumers get race-safe namespace/table creation and consistent error handling by default.
- **Profile-aware config loader** (`src/lakebranch/config.py`): adds `CATALOG_PROFILE` (`nessie` | `sqlite`) and `CATALOG_URI` so the Iceberg catalog backend is selected alongside the storage profile. The Nessie defaults are unchanged.

### Added

- **Nessie branch management** (the "undo/redo for data" story): a new `src/lakebranch/nessie.py` client talks to Nessie's REST **v2 tree API** (`/api/v2/trees`) — separate from PyIceberg's Iceberg REST client, which has no branch APIs — and lists branches/tags, creates branches, merges them, and deletes them. Exposed as `GET /api/branches`, `POST /api/branches`, `POST /api/branches/merge`, and `DELETE /api/branches/{name}`, plus a new GUI **Branches** panel (current-branch badge, list, create, merge, delete). The branch APIs degrade to a 400 with a clear message on the SQLite catalog profile (no branches/tags there). Tested Docker-free with a fake HTTP session and FastAPI `TestClient` (`tests/test_nessie.py`, `tests/test_api_branches.py`).
- **DuckDB SQL query engine** (`src/lakebranch/sql.py`): real SQL (SELECT/JOIN/GROUP BY/subqueries) over the catalog's Iceberg tables via DuckDB. Each table is registered as a sanitized view (`db.events` → `db_events`) plus its quoted dotted alias (`"db.events"`). Docker-independent — works with every catalog (`nessie` / `sqlite`) and storage (`seaweedfs` / `minio` / `aws-s3` / `filesystem`) profile. Exposed as the `lakebranch sql` CLI command and `POST /api/sql` (returns `query`, `row_count`, `columns`, `rows`, `tables` mapping, `duration_ms`).
- **GUI SQL panel**: a "SQL" panel in the single-page UI runs arbitrary SQL over every Iceberg table in the catalog via `POST /api/sql`, renders the result grid, and shows which view names map to which tables.
- **Docker-free SQL engine tests** (`tests/test_sql.py`): cover sanitized view names, quoted dotted aliases, GROUP BY aggregates, real SQL JOINs across tables, `--limit` truncation, and error handling against the SQLite catalog + filesystem warehouse. `POST /api/sql` is also covered in `tests/test_api_integration.py` (valid aggregates, dotted alias, invalid-query 422).
- **SQLite catalog profile** (`CATALOG_PROFILE=sqlite`): PyIceberg `SqlCatalog` backed by a single local `.db` file. Pairs with `STORAGE_PROFILE=filesystem` for a **fully Docker-free stack** — the entire end-to-end write/query pipeline runs with just `pip install`, no containers, no network.
- **`init_catalog()` catalog routing** (`src/lakebranch/catalog.py`): routes to the Nessie REST catalog (`nessie`, default) or the SQLite catalog (`sqlite`) based on `CATALOG_PROFILE`. Handles Windows/macOS/Linux local warehouse paths safely (relative-path rendering with a `file://` cross-drive fallback).
- **Docker-free quickstart** in the README: `STORAGE_PROFILE=filesystem CATALOG_PROFILE=sqlite` → `lakebranch pipeline` works with no Docker at all. The GUI, `init-demo`, run-logging, and Airflow provider all work with this profile.
- **Docker-free integration tests** (`tests/test_sqlite_catalog.py`): exercise the real Iceberg write/read path in CI — create namespace → create table → append → scan — with no Docker or Nessie.
- `pyiceberg[sql-sqlite]` extra added to `pyproject.toml` and `requirements.txt` (SQLAlchemy for the SQLite catalog).
- `CATALOG_PROFILE` / `CATALOG_URI` documented in `.env.example` and the README configuration tables.
- **GUI API integration tests** (`tests/test_api_integration.py`): exercise the real FastAPI app against the Docker-free SQLite catalog + filesystem warehouse via `TestClient` — table listing, write rows (auto-create), **time travel** (`GET /api/tables/{table}/rows?snapshot_id=…`), **snapshot diff** (`GET /api/tables/{table}/diff`), and the filter query runner (`POST /api/query`). All run in CI with no Docker or Nessie. `httpx` added to the `dev` extra (required by FastAPI `TestClient`).
- **GCS storage profile** (`STORAGE_PROFILE=gcs`): new `src/lakebranch/storage/gcs.py` provider backed by `gcsfs` + PyIceberg's native GCS FileIO (via PyArrow). Routes `gs://` warehouse URIs, creates the bucket via `ensure_warehouse()`, and supplies `gcs.*` catalog properties. Auth via Application Default Credentials (or `GCS_TOKEN`). `pyiceberg[gcsfs]` extra added to `pyproject.toml` / `requirements.txt`.
- **ADLS storage profile** (`STORAGE_PROFILE=adls`): new `src/lakebranch/storage/adls.py` provider backed by `adlfs` + PyIceberg's native Azure FileIO (via PyArrow ≥ 20, i.e. `AzureFileSystem`). Routes `abfss://` warehouse URIs, creates the container via `ensure_warehouse()`, and supplies `adls.*` catalog properties. Auth via the Azure credential chain (or `ADLS_ACCOUNT_KEY`). `pyiceberg[adlfs]` extra added to `pyproject.toml` / `requirements.txt`.
- **PostgreSQL catalog profile** (`CATALOG_PROFILE=postgres`): `init_catalog()` now builds PyIceberg's `SqlCatalog` against a PostgreSQL database (`CATALOG_URI`, e.g. `postgresql://user:pass@host:5432/iceberg`) via SQLAlchemy + psycopg2. Server-backed like Nessie (multi-writer) but without branch/tag versioning; works with every storage profile (`seaweedfs`, `minio`, `aws-s3`, `gcs`, `adls`, `filesystem`). `pyiceberg[sql-postgres]` extra added to `pyproject.toml` / `requirements.txt`.

### Fixed

- **`GET /api/tables/{table}/diff` route was unreachable**: the greedy `{table:path}` detail route was registered before it, so `db.events/diff` was swallowed as a (non-existent) table name → 404. The diff route is now registered before the detail route (same pattern as `/rows`).
- **Snapshot diff rows were not JSON-safe**: `added_rows` / `removed_rows` contained numpy scalars from `pandas.iterrows()` and could fail JSON encoding; they are now passed through `_json_safe`.
- **GUI write path failed on auto-created tables** with *"Parquet file does not have field-ids and the Iceberg table does not have 'schema.name-mapping.default' defined"*: tables created from an inferred Arrow schema (no `PARQUET:field_id` metadata) were accepted by `pyarrow_to_schema()` before. `_get_or_create_writable_table` now stamps sequential Iceberg field IDs (1..N) on the inferred schema before conversion, and `_apply_write` re-stamps fields with the table's actual field IDs before append/overwrite. This makes `POST /api/tables/{table}/rows` and `POST /api/tables/{table}/data` (append/overwrite → auto-create) work end-to-end against the Docker-free SQLite catalog.
- **Shared Docker-free test fixtures** (`sqlite_env`, `lake_dir`) moved from `tests/test_sqlite_catalog.py` to `tests/conftest.py` so the catalog and API integration suites share one environment setup.

### Planned

*(none — roadmap complete)*

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