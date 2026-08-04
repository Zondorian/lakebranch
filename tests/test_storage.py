"""Tests for the storage provider factory."""

from __future__ import annotations

import pytest

from src.lakebranch.storage import get_provider
from src.lakebranch.storage.adls import ADLSProvider
from src.lakebranch.storage.filesystem import FilesystemProvider
from src.lakebranch.storage.gcs import GCSProvider
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


def test_gcs_profile_dispatches_to_gcs():
    cfg = {
        "storage_profile": "gcs",
        "gcs_bucket": "warehouse",
        "gcs_project": "my-project",
    }
    provider = get_provider(cfg)
    assert isinstance(provider, GCSProvider)
    props = provider.catalog_properties()
    assert props["gcs.default-bucket-location"] == "warehouse"
    assert props["gcs.project-id"] == "my-project"
    assert "py-io-impl" in props


def test_gcs_project_optional():
    cfg = {"storage_profile": "gcs", "gcs_bucket": "warehouse"}
    provider = get_provider(cfg)
    props = provider.catalog_properties()
    assert "gcs.project-id" not in props
    assert props["gcs.default-bucket-location"] == "warehouse"


def test_adls_profile_dispatches_to_adls():
    cfg = {
        "storage_profile": "adls",
        "adls_account": "mystore",
        "adls_container": "warehouse",
        "adls_account_key": "sekret",
    }
    provider = get_provider(cfg)
    assert isinstance(provider, ADLSProvider)
    props = provider.catalog_properties()
    assert props["adls.account-name"] == "mystore"
    assert props["adls.account-key"] == "sekret"
    assert "py-io-impl" in props


def test_unknown_profile_raises():
    with pytest.raises(ValueError):
        get_provider({"storage_profile": "bogus"})