"""
Lakebranch — Shared Catalog Helpers
==================================

Single source of truth for PyIceberg catalog bootstrap: building the catalog
for the configured catalog + storage profiles, and race-safe namespace / table
creation.

Three catalog backends are supported, selected via ``CATALOG_PROFILE``:

- ``nessie`` (default) — Nessie REST catalog, typically backed by SeaweedFS /
  MinIO / AWS S3 via the storage provider.
- ``sqlite`` — PyIceberg SQLite catalog (a single local ``.db`` file via
  SQLAlchemy). Pairs naturally with ``STORAGE_PROFILE=filesystem`` for a fully
  Docker-free stack: no containers, no network, everything on disk.
- ``postgres`` — PyIceberg SQL catalog backed by a PostgreSQL database (via
  SQLAlchemy + psycopg2). Server-backed like Nessie, but without branch/tag
  versioning; works with every storage profile.

The catalog bootstrap pattern was previously duplicated in four places
(``write_iceberg.py``, ``init_demo.py``, ``api/app.py``, the Airflow demo DAG
and hook) with subtly divergent error handling. Every consumer now uses this
module so new features (GUI writes, branch management, new catalog types) only
need to be wired once.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import (
    NamespaceAlreadyExistsError,
    NoSuchNamespaceError,
    NoSuchTableError,
    TableAlreadyExistsError,
)

from src.lakebranch.storage import get_provider

log = logging.getLogger(__name__)


def _init_nessie_catalog(config: dict[str, str]):
    """Build the PyIceberg Nessie REST catalog for the configured storage profile.

    Uses the storage provider (selected via ``STORAGE_PROFILE``) to supply the
    catalog properties (e.g. S3 endpoint/credentials), so switching backends
    requires zero changes here.
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


def _sqlite_warehouse_location(warehouse_dir: Path) -> str:
    """Render a local warehouse directory for the SqlCatalog.

    PyIceberg's PyArrowFileIO passes every file location through urlparse()
    before resolving it. Absolute Windows paths ("C:\\...") are then misread as
    a URI scheme ("c") and fail with "Unrecognized filesystem type in URI: c".

    Relative paths (no scheme) are resolved against the CWD internally by
    pyiceberg and work on every platform, so they are preferred. When the
    warehouse is not on the same drive as the CWD (e.g. pytest tmp_path on C:
    while the repo is on D:), fall back to a file:// URI with the drive letter
    in the netloc ("file://C:/..."), which PyArrowFileIO reconstructs back to a
    valid local path.
    """
    try:
        return os.path.relpath(warehouse_dir, os.getcwd())
    except ValueError:
        # relpath raises on Windows when the paths are on different mounts.
        pass
    uri = warehouse_dir.as_uri()  # e.g. file:///C:/Users/... or file:///abs/...
    if os.name == "nt" and warehouse_dir.drive:
        # "file:///C:/Users/..." -> "file://C:/Users/..." (drive as netloc).
        # urlparse sees netloc="C:" + path="/Users/...", which pyiceberg
        # reconstructs as "C:/Users/..." — a valid Windows local path.
        return f"file://{uri[len('file:///'):]}"
    return uri


def _init_sqlite_catalog(config: dict[str, str]):
    """Build the PyIceberg SQLite catalog (Docker-free, local file-based).

    The catalog database URI (e.g. ``sqlite:///.lakebranch/catalog.db``) comes
    from ``CATALOG_URI`` and the metadata warehouse location from ``WAREHOUSE``.
    PyIceberg writes table metadata using the ``file://`` IO when the warehouse
    is a local path, so no storage provider or network is needed.

    When paired with ``STORAGE_PROFILE=filesystem`` (the natural Docker-free
    combo), the warehouse location is derived from ``FS_PATH`` so that
    ``ensure_warehouse()`` and the catalog metadata point at the same
    directory.
    """
    from pyiceberg.catalog.sql import SqlCatalog

    warehouse = config["warehouse"]
    if config.get("storage_profile") == "filesystem":
        # Keep the catalog metadata in the same directory the filesystem
        # provider created (FS_PATH), so pipeline + GUI agree on location.
        warehouse = config["fs_path"]

    # Create the warehouse directory here: the GUI API builds the catalog
    # lazily without a prior ensure_warehouse() call, and SQLite will not create
    # parent directories itself.
    warehouse_dir = Path(warehouse).resolve()
    os.makedirs(warehouse_dir, exist_ok=True)

    # Render the warehouse in a pyiceberg-safe form (relative path preferred;
    # file:// with the drive in the netloc when on a different mount).
    warehouse_location = _sqlite_warehouse_location(warehouse_dir)

    # Ensure the SQLite database's parent directory exists. SQLite will not
    # create parent directories itself (unlike DuckDB), so a fresh clone would
    # otherwise fail with "unable to open database file".
    db_path = config["catalog_uri"].removeprefix("sqlite:///")
    if db_path and db_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    log.info("Initializing SQLite catalog at %s (warehouse=%s)", config["catalog_uri"], warehouse_location)
    return SqlCatalog(
        "lakebranch",
        type="sql",
        uri=config["catalog_uri"],
        warehouse=warehouse_location,
        init_catalog_tables="true",
    )


def _init_postgres_catalog(config: dict[str, str]):
    """Build the PyIceberg SQL catalog backed by a PostgreSQL database.

    The catalog database URI (e.g. ``postgresql://user:pass@host:5432/lakebranch``)
    comes from ``CATALOG_URI``. The warehouse location is a cloud object-store
    URI (``s3://``, ``gs://``, ``abfss://``) or a local path, supplied by the
    storage provider via the ``WAREHOUSE`` setting.

    PostgreSQL is server-backed: multiple writers can share one catalog, and it
    works with every storage profile. Unlike Nessie it has no branch/tag
    versioning.
    """
    from pyiceberg.catalog.sql import SqlCatalog

    warehouse = config["warehouse"]
    if config.get("storage_profile") == "filesystem":
        warehouse = config["fs_path"]

    # PostgreSQL requires its own server; parent-directory creation and the
    # file:// rendering dance needed for SQLite do not apply.
    log.info("Initializing PostgreSQL catalog at %s (warehouse=%s)", config["catalog_uri"], warehouse)
    return SqlCatalog(
        "lakebranch",
        type="sql",
        uri=config["catalog_uri"],
        warehouse=warehouse,
        init_catalog_tables="true",
    )


def init_catalog(config: dict[str, str]):
    """Build the PyIceberg catalog for the configured catalog + storage profiles.

    Selects between the Nessie REST catalog, the SQLite catalog, and the
    PostgreSQL SQL catalog based on ``CATALOG_PROFILE`` (``nessie`` |
    ``sqlite`` | ``postgres``). The Nessie path uses the storage provider
    (selected via ``STORAGE_PROFILE``) to supply the catalog properties (e.g.
    S3 endpoint/credentials).

    Args:
        config: The config dict from ``lakebranch.config.load_config()``.

    Returns:
        A configured PyIceberg catalog instance.

    Raises:
        ValueError: If ``CATALOG_PROFILE`` is unknown.
    """
    profile = config["catalog_profile"]
    if profile == "nessie":
        return _init_nessie_catalog(config)
    if profile == "sqlite":
        return _init_sqlite_catalog(config)
    if profile == "postgres":
        return _init_postgres_catalog(config)
    raise ValueError(
        f"Unknown catalog profile '{profile}'. Valid values: nessie, sqlite, postgres"
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