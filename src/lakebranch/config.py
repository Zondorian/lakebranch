"""
Lakebranch — Profile-Aware Configuration Loader
=============================================

Loads configuration from environment variables / .env file, selecting the
appropriate variables based on the ``STORAGE_PROFILE`` setting.

Supported profiles:
    seaweedfs  - SeaweedFS (default, Apache 2.0, local dev)
    minio      - MinIO (AGPLv3, local dev)
    aws-s3     - AWS S3 (production / BYOC)
    gcs        - Google Cloud Storage (not yet implemented)
    adls       - Azure Data Lake Storage Gen2 (not yet implemented)
    filesystem - Local filesystem (embedded / testing)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Valid storage profiles
VALID_PROFILES = ("seaweedfs", "minio", "aws-s3", "gcs", "adls", "filesystem")

# Required environment variables per profile
PROFILE_REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    "seaweedfs": ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"),
    "minio": ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"),
    "aws-s3": ("S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"),
    "gcs": ("GCS_BUCKET", "GCS_PROJECT"),
    "adls": ("ADLS_ACCOUNT", "ADLS_CONTAINER"),
    "filesystem": ("FS_PATH",),
}

# Shared variables required by all profiles
SHARED_REQUIRED_VARS = ("NESSIE_URI", "WAREHOUSE")


def load_config() -> dict[str, str]:
    """Load configuration from environment / .env file.

    Returns a dict with ``storage_profile``, ``nessie_uri``, ``warehouse``,
    plus profile-specific keys. Raises ``RuntimeError`` if required
    environment variables are missing.
    """
    load_dotenv()

    storage_profile = os.getenv("STORAGE_PROFILE", "seaweedfs").strip().lower()
    if storage_profile not in VALID_PROFILES:
        raise ValueError(
            f"Unknown STORAGE_PROFILE '{storage_profile}'. "
            f"Valid values: {', '.join(VALID_PROFILES)}"
        )

    config: dict[str, str] = {
        "storage_profile": storage_profile,
        "nessie_uri": os.getenv("NESSIE_URI", "http://localhost:19120/iceberg/main"),
        "warehouse": os.getenv("WAREHOUSE", "warehouse"),
    }

    # Load profile-specific variables
    for var in PROFILE_REQUIRED_VARS[storage_profile]:
        config[var.lower()] = os.getenv(var, "")

    # Validate required variables
    missing = []
    for var in SHARED_REQUIRED_VARS:
        if not config.get(var.lower()):
            missing.append(var)
    for var in PROFILE_REQUIRED_VARS[storage_profile]:
        if not config.get(var.lower()):
            missing.append(var)

    if missing:
        raise RuntimeError(
            f"Missing required environment variables for profile '{storage_profile}': "
            f"{', '.join(missing)}"
        )

    return config