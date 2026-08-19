"""Storage abstraction for backup files.

The PRD specifies S3-compatible object storage (rustfs/MinIO/AWS S3). This
module defines a ``Storage`` protocol, a default local-filesystem driver for a
runnable MVP, and an S3 driver backed by boto3.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from agent.config import AgentConfig


class Storage(Protocol):
    """Protocol for a backup file store."""

    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload a local file to the store.

        Args:
            local_path: Source file path.
            remote_path: Destination key/path.

        Returns:
            The checksum of the uploaded file.
        """
        ...

    def exists(self, remote_path: str) -> bool:
        """Check whether an object exists in the store.

        Args:
            remote_path: Destination key/path.

        Returns:
            True if present.
        """
        ...

    def sha256(self, path: str) -> str:
        """Compute the SHA-256 checksum of a file.

        Args:
            path: File to hash.

        Returns:
            ``sha256:<hex>`` digest.
        """
        ...


class BaseStorage:
    """Shared helpers for storage drivers.

    Args:
        config: Agent configuration.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    @staticmethod
    def sha256(path: str) -> str:
        """Compute the SHA-256 checksum of a file.

        Args:
            path: File to hash.

        Returns:
            ``sha256:<hex>`` digest.
        """
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"


class LocalStorage(BaseStorage):
    """Store backups on the local filesystem.

    Args:
        config: Agent configuration.
    """

    def upload(self, local_path: str, remote_path: str) -> str:
        """Copy a local file into the configured base directory.

        Args:
            local_path: Source file path.
            remote_path: Relative destination path.

        Returns:
            The SHA-256 checksum of the uploaded file.
        """
        destination = Path(self._config.storage_base_dir) / remote_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).rename(destination)
        return self.sha256(str(destination))

    def exists(self, remote_path: str) -> bool:
        """Check whether a file exists under the base directory.

        Args:
            remote_path: Relative destination path.

        Returns:
            True if the file exists.
        """
        return (Path(self._config.storage_base_dir) / remote_path).is_file()


class S3Storage(BaseStorage):
    """boto3-backed S3-compatible object storage driver.

    Works with any S3-compatible service (MinIO, Ceph RGW, AWS S3, rustfs with
    an S3 API). The boto3 client is created lazily so constructing the driver
    never touches the network.

    Args:
        config: Agent configuration (storage_endpoint/access/secret/bucket).
    """

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)
        self._client = None

    def _get_client(self) -> Any:
        """Return a lazily-created boto3 S3 client.

        Returns:
            The boto3 S3 client for the configured endpoint.
        """
        import boto3

        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self._config.storage_endpoint or None,
                aws_access_key_id=self._config.storage_access_key,
                aws_secret_access_key=self._config.storage_secret_key,
                region_name=self._config.storage_region,
            )
        return self._client

    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload a local file to the configured bucket.

        Args:
            local_path: Source file path.
            remote_path: Destination object key (inside the bucket).

        Returns:
            The SHA-256 checksum of the uploaded file.
        """
        checksum = self.sha256(local_path)
        with open(local_path, "rb") as payload:
            self._get_client().put_object(
                Bucket=self._config.storage_bucket,
                Key=remote_path,
                Body=payload,
            )
        return checksum

    def exists(self, remote_path: str) -> bool:
        """Check whether an object exists in the bucket.

        Args:
            remote_path: Object key.

        Returns:
            True when the object exists and is accessible.
        """
        from botocore.exceptions import ClientError

        try:
            self._get_client().head_object(
                Bucket=self._config.storage_bucket,
                Key=remote_path,
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise


def build_storage(config: AgentConfig) -> Storage:
    """Instantiate the storage driver selected by configuration.

    Args:
        config: Agent configuration.

    Returns:
        A Storage implementation.

    Raises:
        ValueError: For an unknown driver name.
    """
    if config.storage_driver == "local":
        return LocalStorage(config)
    if config.storage_driver == "s3":
        return S3Storage(config)
    raise ValueError(f"Unknown storage driver: {config.storage_driver}")
