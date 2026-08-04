# =============================================================================
# Lakebranch — Airflow Worker Image
# =============================================================================
# Optional orchestration profile: Airflow is a swappable external execution
# layer, NOT embedded in the Lakebranch core. This image extends the official
# Airflow image with the Lakebranch Python dependencies so DAGs can import
# `src.lakebranch` and drive the same storage provider / PyIceberg stack used
# by the CLI pipeline.
#
# The Lakebranch project root is bind-mounted into the container at runtime
# (../:/opt/lakebranch, see docker-compose.airflow.yml), so no source copy is
# needed here.
# =============================================================================

# Official Airflow 2.x image — 2.10.5 is the current stable 2.x line.
FROM apache/airflow:2.10.5-python3.11

# -----------------------------------------------------------------------------
# Lakebranch Python dependencies
# -----------------------------------------------------------------------------
# Mirror requirements.txt (pyiceberg[s3fs,pyarrow], pandas, duckdb,
# python-dotenv). duckdb is included for parity with the run-logging layer
# (src.lakebranch.runs), so DAGs may also record run telemetry if desired.
#
# IMPORTANT: Do NOT use `USER root` here. The official Airflow image ships a
# pip wrapper that refuses to run as root (it exits 1 immediately). The image
# already defaults to the `airflow` user, whose pip is fully functional.
RUN pip install --no-cache-dir \
        "pyiceberg[s3fs,pyarrow]" \
        python-dotenv \
        pandas \
        duckdb

# -----------------------------------------------------------------------------
# Python path
# -----------------------------------------------------------------------------
# /opt/lakebranch is the bind-mounted project root. The `src/` directory inside
# it is the package root — setting PYTHONPATH=/opt/lakebranch lets DAGs use
# `from src.lakebranch.config import load_config` (the project-wide convention).
#
# The standalone Airflow provider package (airflow-providers-lakebranch/) is also
# bind-mounted under /opt/lakebranch, so adding it to PYTHONPATH makes
# `import lakebranch_provider` work in every Airflow component without a pip
# install. This makes the package importable but does NOT register it in
# Airflow's provider registry (entry points only matter for pip-installed
# providers listing on the Providers page — not needed for direct DAG imports).
ENV PYTHONPATH=/opt/lakebranch:/opt/lakebranch/airflow-providers-lakebranch
