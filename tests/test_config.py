"""Tests for the profile-aware config loader."""

from __future__ import annotations

import pytest

from src.lakebranch.config import load_config


def test_default_profile_seaweedfs(monkeypatch):
    monkeypatch.delenv("STORAGE_PROFILE", raising=False)
    monkeypatch.setenv("S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "k")
    monkeypatch.setenv("S3_SECRET_KEY", "s")
    monkeypatch.setenv("S3_BUCKET", "warehouse")
    monkeypatch.setenv("NESSIE_URI", "http://localhost:19120/iceberg/main")
    monkeypatch.setenv("WAREHOUSE", "warehouse")
    cfg = load_config()
    assert cfg["storage_profile"] == "seaweedfs"
    assert cfg["s3_endpoint"] == "http://localhost:9000"
    assert cfg["warehouse"] == "warehouse"


def test_unknown_profile_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_PROFILE", "bogus")
    with pytest.raises(ValueError):
        load_config()


def test_missing_required_vars_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_PROFILE", "seaweedfs")
    # Clear the S3 vars so the required-vars check trips.
    for var in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NESSIE_URI", "http://localhost:19120/iceberg/main")
    monkeypatch.setenv("WAREHOUSE", "warehouse")
    # load_config() calls load_dotenv() which would re-populate the S3 vars
    # from the repo's .env file — neutralize it so the missing check trips.
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    with pytest.raises(RuntimeError, match="Missing required environment variables"):
        load_config()
