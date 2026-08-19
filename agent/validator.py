"""Backup validation (PRD section 14).

A completed backup is not considered valid until it has a non-empty file, a
checksum, and its object exists in storage. Size/checksum are computed on the
local file before upload; object existence is verified after upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.storage import Storage


@dataclass
class ValidationResult:
    """Result of validating a backup file.

    Attributes:
        valid: Whether all checks passed.
        checksum: Computed checksum (``sha256:...``) when available.
        size_bytes: Size of the file in bytes.
        error: Error message when validation failed.
    """

    valid: bool = False
    checksum: str | None = None
    size_bytes: int | None = None
    error: str | None = None


class Validator:
    """Validates a produced backup file against MVP rules.

    Args:
        storage: The storage driver used for hashing and the exists check.
    """

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def validate_local(self, local_path: str) -> ValidationResult:
        """Validate the local backup file before upload.

        Args:
            local_path: Local path of the compressed backup.

        Returns:
            A ValidationResult with size/checksum when the file is valid.
        """
        path = Path(local_path)
        if not path.is_file():
            return ValidationResult(error="file not created")
        size = path.stat().st_size
        if size <= 0:
            return ValidationResult(error="file size is zero", size_bytes=0)
        checksum = self._storage.sha256(local_path)
        return ValidationResult(valid=True, checksum=checksum, size_bytes=size)

    def verify_object(self, remote_path: str) -> bool:
        """Verify the uploaded object exists in storage.

        Args:
            remote_path: Remote key where the object was uploaded.

        Returns:
            True when the object exists.
        """
        return self._storage.exists(remote_path)
