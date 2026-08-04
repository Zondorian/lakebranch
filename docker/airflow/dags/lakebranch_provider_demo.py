"""
Lakebranch Airflow Provider — DAG re-export wrapper
=================================================

The Airflow stack only parses DAGs under ``AIRFLOW__CORE__DAGS_FOLDER``
(``/opt/lakebranch/docker/airflow/dags``). The provider's canonical demo DAG
lives in the standalone package at
``/opt/lakebranch/airflow-providers-lakebranch/lakebranch_provider/example_dags/``.

This thin module re-exports that ``dag`` object so the provider demo DAG is
parsed by the scheduler with zero duplication and zero pip install (the
provider package is on ``PYTHONPATH``).
"""

from __future__ import annotations

from lakebranch_provider.example_dags.lakebranch_provider_demo import dag

__all__ = ["dag"]