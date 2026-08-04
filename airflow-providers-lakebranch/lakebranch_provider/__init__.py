"""
Lakebranch Airflow provider.

A standalone, optional (Apache 2.0) Airflow provider that makes "write to
Iceberg via Lakebranch" a one-operator DAG. The package is versioned and
released independently from the Lakebranch core.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export the operator and hook for ergonomic imports.
from lakebranch_provider.hooks.lakebranch import LakebranchHook
from lakebranch_provider.operators.lakebranch import LakebranchWriteOperator

__all__ = [
    "LakebranchHook",
    "LakebranchWriteOperator",
    "__version__",
]


def get_provider_info() -> dict:
    """Return provider metadata for Airflow's provider registry.

    This is consumed by the ``apache_airflow_provider`` entry point declared in
    ``pyproject.toml``. It makes the provider appear on the Airflow Providers
    page with its name, version, and the hooks/operators it ships. Airflow
    treats the package as a *provider* only when installed via pip (entry
    points); the PYTHONPATH / zero-install approach used in the Lakebranch
    Docker image imports the package directly and does not need this.
    """
    return {
        "package-name": "apache-airflow-providers-lakebranch",
        "name": "Lakebranch",
        "description": "Write to Iceberg via Lakebranch in a one-operator DAG.",
        "version": __version__,
        "hooks": ["lakebranch_provider.hooks.lakebranch.LakebranchHook"],
        "operators": ["lakebranch_provider.operators.lakebranch.LakebranchWriteOperator"],
    }