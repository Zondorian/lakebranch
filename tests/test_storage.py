"""Tests for the storage provider factory."""

from __future__ import annotations

import pytest

from src.lakebranch.storage import get_provider
from src.lakebranch.storage.filesystem import FilesystemProvider
from src.lakebranch.storage.s3_compat import S3CompatProvider


def test_s3_profiles_dispatch_to_s3compat():
    for profile in ("seaweedfs", "minio", "aws-s3"):
        cfg = {
            "storage_profile": profile,
            "s3_endpoint": "http://localhost:9000",
            "s3_access_key": "k",
            "s3_secret_key": "s",
            "s3_bucket": "warehouse",
        }
        assert isinstance(get_provider(cfg), S3CompatProvider)


def test_filesystem_profile_dispatches_to_filesystem():
    cfg = {"storage_profile": "filesystem", "fs_path": "./data/warehouse"}
    assert isinstance(get_provider(cfg), FilesystemProvider)


def test_unimplemented_gcs_raises():
    with pytest.raises(NotImplementedError):
        get_provider({"storage_profile": "gcs"})


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        get_provider({"storage_profile": "bogus"})