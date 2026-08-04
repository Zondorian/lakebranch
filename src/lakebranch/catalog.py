"""
Lakebranch — Shared Catalog Helpers
==================================

Single source of truth for PyIceberg catalog bootstrap: building the Nessie
REST catalog for the configured storage profile, and race-safe namespace /
table creation.

The catalog bootstrap pattern was previously duplicated in four places
(``write_iceberg.py``, ``init_demo.py``, ``api/app.py``, the Airflow demo DAG
and hook) with subtly divergent error handling. Every consumer now uses this
module so new features (GUI writes, branch management, new catalog types) only
need to be wired once.
"""

from __future__ import annotations

import logging

from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import (
    NamespaceAlreadyExistsError,
    NoSuchNamespaceError,
    NoSuchTableError,
    TableAlreadyExistsError,
)

from src.lakebranch.storage import get_provider

log = logging.getLogger(__name__)


def init_catalog(config: dict[str, str]):
    """Build the PyIceberg catalog for the configured storage profile.

    Uses the storage provider (selected via ``STORAGE_PROFILE``) to supply the
    catalog properties (e.g. S3 endpoint/credentials for Nessie), so switching
    backends requires zero changes here.

    Args:
        config: The config dict from ``lakebranch.config.load_config()``.

    Returns:
        A configured PyIceberg catalog instance (Nessie REST catalog).
    """
    provider = get_provider(config)
    log.info("Initializing Nessie REST catalog at %s", config["nessie_uri"])
    return load_catalog(
        "nessie",
        **{
            "type": "rest",
            "uri": config["nessie_uri"],
            "warehouse": config["warehouse"],
            **provider.catalog_properties(),
        },
    )


def ensure_namespace(catalog, namespace: str = "db") -> None:
    """Load the given namespace, creating it if it does not exist.

    Race-safe: a concurrent ``create_namespace`` between the existence check
    and the create is treated as success.
    """
    try:
        catalog.load_namespace_properties(namespace)
    except NoSuchNamespaceError:
        try:
            catalog.create_namespace(namespace)
            log.info("Created namespace '%s'", namespace)
        except NamespaceAlreadyExistsError:
            # Race-safe: another process created it between check and create.
            log.info("Namespace '%s' created concurrently", namespace)


def ensure_table(catalog, table_name: str, schema):
    """Load a table, creating it with ``schema`` if it does not exist.

    Race-safe: a concurrent ``create_table`` between the existence check and
    the create is treated as success.

    Args:
        catalog: The PyIceberg catalog.
        table_name: Fully qualified Iceberg table name (e.g. ``db.events``).
        schema: PyIceberg schema used only when the table must be created.

    Returns:
        The loaded (or newly created) PyIceberg table.
    """
    try:
        return catalog.load_table(table_name)
    except NoSuchTableError:
        namespace = namespace_of(table_name)
        ensure_namespace(catalog, namespace)
        try:
            table = catalog.create_table(table_name, schema=schema)
            log.info("Created table '%s'", table_name)
            return table
        except TableAlreadyExistsError:
            # Race-safe: another process created it between check and create.
            return catalog.load_table(table_name)


def namespace_of(table_name: str) -> str:
    """Return the namespace part of a dotted table identifier.

    ``db.events`` -> ``db``; a bare identifier (no dot) -> ``default``.
    """
    return table_name.rsplit(".", 1)[0] if "." in table_name else "default"