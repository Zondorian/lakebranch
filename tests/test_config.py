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


def test_default_catalog_profile_nessie(monkeypatch):
    monkeypatch.delenv("CATALOG_PROFILE", raising=False)
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("FS_PATH", "./data/warehouse")
    monkeypatch.setenv("WAREHOUSE", "data/warehouse")
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    cfg = load_config()
    assert cfg["catalog_profile"] == "nessie"
    assert cfg["nessie_uri"] == "http://localhost:19120/iceberg/main"


def test_sqlite_catalog_profile(monkeypatch):
    monkeypatch.setenv("CATALOG_PROFILE", "sqlite")
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("FS_PATH", "./data/warehouse")
    monkeypatch.setenv("WAREHOUSE", "data/warehouse")
    monkeypatch.setenv("CATALOG_URI", "sqlite:///tmp/catalog.db")
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    cfg = load_config()
    assert cfg["catalog_profile"] == "sqlite"
    assert cfg["catalog_uri"] == "sqlite:///tmp/catalog.db"


def test_unknown_catalog_profile_raises(monkeypatch):
    monkeypatch.setenv("CATALOG_PROFILE", "bogus")
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("FS_PATH", "./data/warehouse")
    monkeypatch.setenv("WAREHOUSE", "data/warehouse")
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    with pytest.raises(ValueError, match="Unknown CATALOG_PROFILE"):
        load_config()


def test_sqlite_profile_default_catalog_uri(monkeypatch):
    """The sqlite catalog profile falls back to the documented CATALOG_URI default."""
    monkeypatch.setenv("CATALOG_PROFILE", "sqlite")
    monkeypatch.setenv("STORAGE_PROFILE", "filesystem")
    monkeypatch.setenv("FS_PATH", "./data/warehouse")
    monkeypatch.setenv("WAREHOUSE", "data/warehouse")
    monkeypatch.delenv("CATALOG_URI", raising=False)
    monkeypatch.setattr("src.lakebranch.config.load_dotenv", lambda **kwargs: None)
    cfg = load_config()
    assert cfg["catalog_profile"] == "sqlite"
    assert cfg["catalog_uri"] == "sqlite:///.lakebranch/catalog.db"
