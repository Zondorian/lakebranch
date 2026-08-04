"""Lakebranch — Local filesystem storage provider."""

from __future__ import annotations

import os


class FilesystemProvider:
    """Storage provider for local filesystem backends.

    Nessie handles ``file://`` warehouse locations natively, so no special
    catalog properties are needed beyond the warehouse location itself.
    """

    def __init__(self, config: dict[str, str]) -> None:
        self.fs_path = config["fs_path"]

    def ensure_warehouse(self) -> None:
        """Create the local warehouse directory if it does not exist."""
        os.makedirs(self.fs_path, exist_ok=True)
        print(f"[fs] Ensured warehouse directory: {self.fs_path}")

    def catalog_properties(self) -> dict[str, str]:
        """Return the PyIceberg catalog kwargs for the filesystem backend."""
        # Nessie handles file:// warehouse locations via the WAREHOUSE
        # setting alone; no additional properties are required.
        return {}