"""Lakebranch — S3-compatible storage provider (SeaweedFS, MinIO, AWS S3)."""

from __future__ import annotations

import s3fs


class S3CompatProvider:
    """Storage provider for S3-compatible object stores.

    Handles SeaweedFS, MinIO, and AWS S3 uniformly. The S3 API is the
    abstraction boundary — switching between these backends requires
    zero changes to pipeline code.
    """

    def __init__(self, config: dict[str, str]) -> None:
        self.endpoint = config["s3_endpoint"]
        self.access_key = config["s3_access_key"]
        self.secret_key = config["s3_secret_key"]
        self.bucket = config["s3_bucket"]

    def _get_fs(self) -> s3fs.S3FileSystem:
        """Create a configured s3fs filesystem instance."""
        return s3fs.S3FileSystem(
            key=self.access_key,
            secret=self.secret_key,
            client_kwargs={
                "endpoint_url": self.endpoint,
                "aws_access_key_id": self.access_key,
                "aws_secret_access_key": self.secret_key,
            },
            config_kwargs={
                "s3": {"addressing_style": "path"},
                "signature_version": "s3v4",
            },
        )

    def ensure_warehouse(self) -> None:
        """Connect to the S3 endpoint and create the warehouse bucket if absent.

        Uses path-style addressing (not virtual-host-style), which is
        required for self-hosted S3-compatible stores like SeaweedFS and
        MinIO. We configure botocore via ``client_kwargs`` with
        ``endpoint_url`` and explicitly set ``addressing_style='path'``
        to ensure correct request routing.
        """
        print(f"[s3] Connecting to S3 endpoint: {self.endpoint}")
        print(f"[s3]   access-key : {self.access_key}")
        print(f"[s3]   bucket     : {self.bucket}")

        fs = self._get_fs()

        if fs.exists(self.bucket):
            print(f"[s3] Bucket '{self.bucket}' already exists.")
        else:
            # s3fs mkdir with create_parents=False creates a top-level bucket.
            fs.mkdir(self.bucket, create_parents=False)
            print(f"[s3] Created bucket '{self.bucket}'.")

        # Verify the bucket is now listed. s3fs returns paths like "bucket/" or
        # detail dicts with a "Key"/"name" field depending on the version, so we
        # normalize by stripping trailing slashes and comparing.
        listing = fs.ls("", detail=True)
        buckets = []
        for entry in listing:
            if isinstance(entry, dict):
                name = entry.get("Name") or entry.get("Key") or entry.get("name") or ""
            else:
                name = str(entry)
            buckets.append(name.rstrip("/"))
        if self.bucket in buckets:
            print(f"[s3] Verified bucket '{self.bucket}' is present.")
        else:
            print(f"[s3] WARNING: bucket '{self.bucket}' not found in listing: {buckets}")

    def catalog_properties(self) -> dict[str, str]:
        """Return the PyIceberg catalog kwargs for this S3 backend."""
        return {
            "s3.endpoint": self.endpoint,
            "s3.access-key-id": self.access_key,
            "s3.secret-access-key": self.secret_key,
        }