"""Lakebranch — Google Cloud Storage (GCS) storage provider."""

from __future__ import annotations

from gcsfs import GCSFileSystem


class GCSProvider:
    """Storage provider for Google Cloud Storage.

    Uses the native PyIceberg GCS FileIO (via PyArrow), so no S3-compat
    bridge is needed. Bucket creation uses the ``gcsfs`` package, which is
    installed by the ``pyiceberg[gcsfs]`` extra.
    """

    def __init__(self, config: dict[str, str]) -> None:
        self.bucket = config["gcs_bucket"]
        self.project = config.get("gcs_project", "")
        # Optional: an access token for non-ADC auth. If unset, gcsfs
        # falls back to Application Default Credentials.
        self.token = config.get("gcs_token", "")

    def _get_fs(self) -> GCSFileSystem:
        fs_kwargs: dict[str, object] = {"project": self.project} if self.project else {}
        if self.token:
            fs_kwargs["token"] = self.token
        return GCSFileSystem(**fs_kwargs)

    def ensure_warehouse(self) -> None:
        """Create the GCS bucket if it does not exist."""
        fs = self._get_fs()
        if fs.exists(self.bucket):
            print(f"[gcs] Bucket '{self.bucket}' already exists.")
        else:
            fs.mkdir(self.bucket)
            print(f"[gcs] Created bucket '{self.bucket}'.")

    def catalog_properties(self) -> dict[str, str]:
        """Return the PyIceberg catalog kwargs for GCS.

        Routes GCS URIs (``gs://bucket/...``) to PyIceberg's native GCS
        FileIO (PyArrowFileIO). Credentials come from Application Default
        Credentials unless ``GCS_TOKEN`` is set.
        """
        props: dict[str, str] = {
            "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            "gcs.default-bucket-location": self.bucket,
        }
        if self.project:
            props["gcs.project-id"] = self.project
        if self.token:
            props["gcs.oauth2.token"] = self.token
        return props