"""Lakebranch — Azure Data Lake Storage Gen2 (ADLS) storage provider."""

from __future__ import annotations

from adlfs import AzureBlobFileSystem


class ADLSProvider:
    """Storage provider for Azure Data Lake Storage Gen2.

    Uses the native PyIceberg Azure FileIO (via PyArrow, ``pyarrow>=20``),
    so no S3-compat bridge is needed. Containers are created with the
    ``adlfs`` package, installed by the ``pyiceberg[adlfs]`` extra.
    """

    def __init__(self, config: dict[str, str]) -> None:
        self.account = config["adls_account"]
        self.container = config["adls_container"]
        # Optional credential: storage account key. If unset, auth falls back
        # to the Azure credential chain (DefaultAzureCredential-equivalent
        # via adlfs / pyarrow).
        self.account_key = config.get("adls_account_key", "")

    def _get_fs(self) -> AzureBlobFileSystem:
        fs_kwargs: dict[str, object] = {"account_name": self.account}
        if self.account_key:
            fs_kwargs["account_key"] = self.account_key
        return AzureBlobFileSystem(**fs_kwargs)

    def ensure_warehouse(self) -> None:
        """Create the ADLS container if it does not exist."""
        fs = self._get_fs()
        if fs.exists(self.container):
            print(f"[adls] Container '{self.container}' already exists.")
        else:
            fs.mkdir(self.container, create_parents=False)
            print(f"[adls] Created container '{self.container}'.")

    def catalog_properties(self) -> dict[str, str]:
        """Return the PyIceberg catalog kwargs for ADLS.

        Routes ADLS URIs (``abfss://container@account.dfs.core.windows.net``)
        to PyIceberg's native Azure FileIO (PyArrowFileIO). The warehouse
        must use the ``abfss://`` scheme, which PyIceberg parses into the
        account name and container for the Azure filesystem.
        """
        props: dict[str, str] = {
            "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            "adls.account-name": self.account,
        }
        if self.account_key:
            props["adls.account-key"] = self.account_key
        return props