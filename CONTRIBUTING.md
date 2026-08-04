# Contributing to Lakebranch

Thank you for considering a contribution! Lakebranch is a **local-first, Apache Iceberg data lakehouse** — fully open source under the Apache 2.0 license. This guide covers getting started, making changes, and submitting a pull request.

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Local setup](#local-setup)
3. [Verify your setup works](#verify-your-setup-works)
4. [Run the tests](#run-the-tests)
5. [Project layout](#project-layout)
6. [Making changes](#making-changes)
7. [Submitting a pull request](#submitting-a-pull-request)
8. [Reporting bugs](#reporting-bugs)

## Prerequisites

- **Docker** with Docker Compose v2 (`docker compose` command)
- **Python 3.10+**
- **git**

## Local setup

1. **Fork & clone** the repository, then `cd` into it.

2. **Create and activate a virtual environment:**

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

3. **Install the package in editable mode with dev dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```
   This installs the `lakebranch` CLI, `pyiceberg`, `duckdb`, `pandas`, and `pytest`.

4. **Create your `.env` from the template:**
   ```bash
   cp .env.example .env
   ```
   > `.env` is git-ignored and must never be committed — it may hold real credentials.

5. **Start the local data plane (SeaweedFS + Nessie):**
   ```bash
   docker compose -f docker/docker-compose.yml --env-file .env up -d
   ```

## Verify your setup works

```bash
# Load the demo dataset (creates users/orders/events tables)
lakebranch init-demo

# Run the end-to-end Iceberg write/query pipeline
lakebranch pipeline
```

If you want to see the web UI with time travel and snapshot diff:

```bash
lakebranch ui        # then open http://localhost:8787/ui/
```

## Run the tests

```bash
python -m pytest
```

All tests **must pass** before you open a pull request. The test suite covers config loading, the DuckDB run-log, the storage-provider factory, the CLI parser, and API serialization helpers — it is designed to run **without** the Docker stack.

## Project layout

```
src/lakebranch/           # Python core
  cli.py                #   `lakebranch` CLI (up/down/pipeline/runs/ui/init-demo)
  config.py             #   Profile-aware config loader
  runs.py               #   DuckDB run-log (telemetry) layer
  write_iceberg.py      #   End-to-end writer/query pipeline
  init_demo.py          #   Multi-table demo dataset loader
  api/                  #   FastAPI GUI backend (Time Travel + Snapshot Diff)
  ui/                   #   Single-page static GUI (no build step)
  storage/              #   Storage abstraction (SeaweedFS/MinIO/AWS S3/filesystem)
airflow-providers-lakebranch/   # Standalone Apache 2.0 Airflow provider package
docker/                 # Docker Compose profiles
tests/                  # pytest suite (18 tests, no Docker required)
```

For the deeper "AI assistant" orientation, see [`CLAUDE.md`](CLAUDE.md).

## Making changes

- Create a **feature branch** off `master` with a descriptive name:
  ```bash
  git checkout -b feat/your-feature
  # or
  git checkout -b fix/your-bug
  ```
- Keep changes **focused** — one logical change per pull request.
- **Add a test** for new behavior (tests live in `tests/` and mirror the existing style).
- Update the **README** and **CLAUDE.md** if you change user-facing behavior or structure.
- Never commit `.env` or any file containing real credentials.

## Submitting a pull request

1. Push your branch and open a pull request **against `master`**.
   ```bash
   git push -u origin feat/your-feature
   ```
2. In the PR description, explain **what** changed and **why**.
3. Confirm the **checklist**: tests pass, docs updated (if applicable), no `.env` committed.
4. If you're not a maintainer, your PR may be from a fork — that's expected and welcome.

## Reporting bugs

Before opening an issue, please:

1. **Search existing issues** for the same problem.
2. **Include in your report:**
   - Operating system and Python version
   - Output of `docker compose -f docker/docker-compose.yml ps`
   - The exact error message / stack trace
   - Steps to reproduce (minimal is best)

Open a GitHub issue with the **Bug report** template when you're ready.