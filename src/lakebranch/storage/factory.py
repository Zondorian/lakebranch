"""Lakebranch — Storage provider factory."""

from __future__ import annotations

from src.lakebranch.storage.base import StorageProvider
from src.lakebranch.storage.filesystem import FilesystemProvider
from src.lakebranch.storage.s3_compat import S3CompatProvider


class GCSProvider:
    """Google Cloud Storage provider (not yet implemented)."""

    def __init__(self, config: dict[str, str]) -> None:
        raise NotImplementedError(
            "The 'gcs' storage profile is not yet implemented. "
            "Use 'seaweedfs', 'minio', 'aws-s3', or 'filesystem'."
        )

    def ensure_warehouse(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def catalog_properties(self) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError


class ADLSProvider:
    """Azure Data Lake Storage Gen2 provider (not yet implemented)."""

    def __init__(self, config: dict[str, str]) -> None:
        raise NotImplementedError(
            "The 'adls' storage profile is not yet implemented. "
            "Use 'seaweedfs', 'minio', 'aws-s3', or 'filesystem'."
        )

    def ensure_warehouse(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def catalog_properties(self) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError


def get_provider(config: dict[str, str]) -> StorageProvider:
    """Return the storage provider for the given configuration.

    Args:
        config: The config dict from ``lakebranch.config.load_config()``.

    Returns:
        A ``StorageProvider`` instance suitable for the configured profile.

    Raises:
        ValueError: If the storage profile is unknown.
        NotImplementedError: If the profile is recognized but not implemented.
    """
    profile = config["storage_profile"]

    if profile in ("seaweedfs", "minio", "aws-s3"):
        return S3CompatProvider(config)
    if profile == "gcs":
        return GCSProvider(config)
    if profile == "adls":
        return ADLSProvider(config)
    if profile == "filesystem":
        return FilesystemProvider(config)

    raise ValueError(f"Unknown storage profile: {profile}")