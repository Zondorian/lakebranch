"""
Lakebranch — Airflow Hook
=======================

Wraps the Lakebranch core APIs (``src.lakebranch.config.load_config`` and
``src.lakebranch.storage.get_provider``) plus the PyIceberg REST catalog so
Airflow tasks can write to Iceberg in a few lines.

The hook deliberately reuses the *exact* patterns verified in the reference
DAG (``docker/airflow/dags/lakebranch_demo_dag.py``) and the CLI pipeline
(``src/lakebranch/write_iceberg.py``): profile-aware config, storage-provider
selection, Nessie REST catalog via PyIceberg, namespace/table creation with
race-safe guards, and append/overwrite via PyArrow.

All ``src.lakebranch`` imports are lazy so that importing this package does not
require the Lakebranch core on ``PYTHONPATH`` — the requirement only surfaces
when a hook method actually runs.
"""

from __future__ import annotations

import logging

from airflow.hooks.base import BaseHook
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

log = logging.getLogger(__name__)

# The same sample schema used by the reference DAG / CLI writer. A generic
# provider could derive the schema from the incoming rows instead; keeping a
# well-known schema makes the bundled demo deterministic.
DEFAULT_EVENTS_SCHEMA = Schema(
    NestedField(field_id=1, name="event_id", field_type=LongType(), required=True),
    NestedField(field_id=2, name="event_type", field_type=StringType(), required=False),
    NestedField(field_id=3, name="timestamp", field_type=StringType(), required=False),
)


class LakebranchHook(BaseHook):
    """Airflow hook that wraps Lakebranch's profile-aware storage + PyIceberg.

    The hook follows Airflow's convention of exposing configuration through a
    ``conn_id``. Lakebranch reads the storage profile from the environment (via
    ``STORAGE_PROFILE`` and friends), so the default connection is a logical
    placeholder: set ``conn_id`` to any string (or omit it) unless you later
    add a real connection-type backend. All real configuration comes from the
    Lakebranch environment, exactly like the CLI pipeline.
    """

    conn_name_attr = "lakebranch_conn_id"
    default_conn_name = "lakebranch_default"
    conn_type = "lakebranch"
    hook_name = "Lakebranch"

    def __init__(self, conn_id: str = default_conn_name, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.lakebranch_conn_id = conn_id
        self._config = None
        self._provider = None
        self._catalog = None

    # ------------------------------------------------------------------
    # Lazy core imports (src.lakebranch is NOT bundled with this package)
    # ------------------------------------------------------------------
    @staticmethod
    def _core_imports():
        """Import the Lakebranch core lazily.

        Raises ImportError with a clear message when the repo root is not on
        ``PYTHONPATH``. In the Lakebranch Docker image the core lives at
        ``/opt/lakebranch`` on ``PYTHONPATH``; for local ``pip install -e`` use,
        the repo root must be added to ``PYTHONPATH`` too.
        """
        try:
            from src.lakebranch.catalog import (
                ensure_namespace as catalog_ensure_namespace,
                ensure_table as catalog_ensure_table,
                init_catalog,
            )
            from src.lakebranch.config import load_config
            from src.lakebranch.storage import get_provider
        except ImportError as exc:  # pragma: no cover - defensive
            raise ImportError(
                "Lakebranch core not importable. Ensure the Lakebranch repo root is "
                "on PYTHONPATH (in the Docker image it is /opt/lakebranch). "
                "Original error: %s" % exc
            ) from exc
        return load_config, get_provider, init_catalog, catalog_ensure_namespace, catalog_ensure_table

    # ------------------------------------------------------------------
    # Configuration & providers
    # ------------------------------------------------------------------
    def get_config(self) -> dict[str, str]:
        """Load the profile-aware Lakebranch configuration (cached)."""
        if self._config is None:
            load_config, _, _, _, _ = self._core_imports()
            self._config = load_config()
        return self._config

    def get_provider(self):
        """Return the storage provider for the configured ``STORAGE_PROFILE``."""
        if self._provider is None:
            _, get_provider, _, _, _ = self._core_imports()
            self._provider = get_provider(self.get_config())
        return self._provider

    def ensure_warehouse(self) -> None:
        """Ensure the warehouse (bucket/directory) for the configured profile exists."""
        self.get_provider().ensure_warehouse()
        config = self.get_config()
        log.info("Warehouse '%s' ready (profile=%s)", config["warehouse"], config["storage_profile"])

    # ------------------------------------------------------------------
    # PyIceberg catalog + tables
    # ------------------------------------------------------------------
    def get_catalog(self):
        """Build (and cache) the PyIceberg REST catalog pointing at Nessie."""
        if self._catalog is None:
            _, _, init_catalog, _, _ = self._core_imports()
            config = self.get_config()
            self._catalog = init_catalog(config)
            log.info("Initialized Nessie REST catalog at %s", config["nessie_uri"])
        return self._catalog

    def ensure_namespace(self, namespace: str = "db") -> None:
        """Load the namespace, creating it if it does not exist (race-safe)."""
        _, _, _, catalog_ensure_namespace, _ = self._core_imports()
        catalog_ensure_namespace(self.get_catalog(), namespace)

    def get_table(self, table_name: str, schema: Schema | None = None, create_if_missing: bool = True):
        """Load a table, creating it with ``schema`` if it does not exist.

        Args:
            table_name: Fully qualified Iceberg table name (e.g. ``db.events``).
            schema: PyIceberg schema used only when the table must be created.
            create_if_missing: If the table is absent, create it (requires
                ``schema``). If False, raise ``NoSuchTableError`` instead.

        Returns:
            The loaded PyIceberg table.
        """
        catalog = self.get_catalog()
        if not create_if_missing:
            # Preserve the original semantics: raise when the table is absent.
            return catalog.load_table(table_name)
        if schema is None:
            raise ValueError(
                f"Table '{table_name}' does not exist and no schema was provided to create it."
            )
        _, _, _, _, catalog_ensure_table = self._core_imports()
        return catalog_ensure_table(catalog, table_name, schema)

    # ------------------------------------------------------------------
    # Airflow connection handling (logical placeholder)
    # ------------------------------------------------------------------
    def get_conn(self):
        """Return the Airflow connection (empty placeholder).

        Lakebranch reads configuration from the environment (``STORAGE_PROFILE``,
        ``NESSIE_URI``, ``S3_*``) exactly like the CLI pipeline. The connection
        is a logical handle for Airflow UI bookkeeping; no credentials are
        stored in the connection.
        """
        return self.get_connection(self.lakebranch_conn_id)

    @classmethod
    def get_ui_field_behaviour(cls) -> dict:
        """Return custom UI field behavior for the Airflow connection form."""
        return {
            "hidden_fields": ["host", "schema", "login", "password", "port", "extra"],
            "relabeling": {},
        }