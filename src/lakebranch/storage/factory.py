"""Lakebranch — Storage provider factory."""

from __future__ import annotations

from src.lakebranch.storage.adls import ADLSProvider
from src.lakebranch.storage.base import StorageProvider
from src.lakebranch.storage.filesystem import FilesystemProvider
from src.lakebranch.storage.gcs import GCSProvider
from src.lakebranch.storage.s3_compat import S3CompatProvider


def get_provider(config: dict[str, str]) -> StorageProvider:
    """Return the storage provider for the given configuration.

    Args:
        config: The config dict from ``lakebranch.config.load_config()``.

    Returns:
        A ``StorageProvider`` instance suitable for the configured profile.

    Raises:
        ValueError: If the storage profile is unknown.
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