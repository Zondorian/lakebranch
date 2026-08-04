"""Lakebranch — Storage provider protocol."""

from __future__ import annotations

from typing import Protocol


class StorageProvider(Protocol):
    """Interface implemented by all storage backends."""

    def ensure_warehouse(self) -> None:
        """Ensure the warehouse (bucket/directory) exists, creating it if absent."""
        ...

    def catalog_properties(self) -> dict[str, str]:
        """Return the PyIceberg catalog kwargs for this storage backend."""
        ...