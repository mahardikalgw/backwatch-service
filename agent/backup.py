"""Backup orchestration and reporting to the Backup API (PRD sections 5.1, 6, 15)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from agent.config import AgentConfig
from agent.database import DatabaseDumper
from agent.logger import get_logger
from agent.storage import Storage, build_storage
from agent.validator import Validator


@dataclass
class BackupOutcome:
    """Result of a full backup run.

    Attributes:
        status: ``success`` or ``failed``.
        started_at: Start time.
        finished_at: End time.
        storage_path: Remote storage key.
        checksum: Uploaded file checksum.
        size_bytes: Uploaded file size.
        error: Error message when failed.
    """

    status: str
    started_at: datetime
    finished_at: datetime
    storage_path: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> int:
        """Return the elapsed duration in whole seconds.

        Returns:
            The difference between finished and started timestamps.
        """
        return int((self.finished_at - self.started_at).total_seconds())


class BackupEngine:
    """Runs the end-to-end backup pipeline for one application.

    Args:
        config: Agent configuration.
    """

    def __init__(self, config: AgentConfig, storage: Storage | None = None) -> None:
        self._config = config
        self._storage = storage or build_storage(config)
        self._logger = get_logger("backup-agent")
        self._dumper = DatabaseDumper(config)

    def run(self) -> BackupOutcome:
        """Execute a backup.

        Returns:
            A BackupOutcome describing success or failure.
        """
        started_at = datetime.now(timezone.utc)
        self._logger.info("backup started", application=self._config.application)

        dump = self._dumper.dump(started_at)
        if dump.local_path is None:
            return self._finish(started_at, "failed", error=dump.error)

        local_path = dump.local_path
        remote_path = self._remote_path(started_at, local_path)

        validator = Validator(self._storage)
        validation = validator.validate_local(local_path)
        if not validation.valid:
            error = validation.error or "validation failed"
            self._logger.error("backup failed validation", error=error)
            return self._finish(started_at, "failed", error=error)

        self._logger.info("upload started", path=remote_path)
        try:
            self._storage.upload(local_path, remote_path)
        except Exception as exc:  # noqa: BLE001 - reported as a failed backup
            self._logger.error("upload failed", error=str(exc))
            return self._finish(started_at, "failed", error=f"upload failed: {exc}")

        if not validator.verify_object(remote_path):
            error = "object does not exist in storage"
            self._logger.error("backup failed validation", error=error)
            return self._finish(started_at, "failed", error=error, storage_path=remote_path)

        self._logger.info("upload completed", path=remote_path)
        self._logger.info("checksum verified", checksum=validation.checksum)
        self._logger.info("backup completed")
        return BackupOutcome(
            status="success",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            storage_path=remote_path,
            checksum=validation.checksum,
            size_bytes=validation.size_bytes,
        )

    def _remote_path(self, started_at: datetime, local_path: str) -> str:
        """Build the remote storage key from the dump filename.

        Args:
            started_at: The backup start time.
            local_path: The compressed dump filename.

        Returns:
            A key like ``<bucket>/<app>/<YYYY>/<MM>/<DD>/<name>.gz``.
        """
        name = Path(local_path).name
        return "/".join(
            [
                self._config.storage_bucket,
                self._config.application,
                started_at.strftime("%Y/%m/%d"),
                name,
            ]
        )

    def _finish(
        self,
        started_at: datetime,
        status: str,
        *,
        error: str | None = None,
        storage_path: str | None = None,
    ) -> BackupOutcome:
        """Build a completed BackupOutcome and log the result.

        Args:
            started_at: The backup start time.
            status: ``success`` or ``failed``.
            error: Failure message, when applicable.
            storage_path: Remote storage key, when available.

        Returns:
            The final BackupOutcome.
        """
        outcome = BackupOutcome(
            status=status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            storage_path=storage_path,
            error=error,
        )
        if status == "failed":
            self._logger.error("backup failed", error=error)
        return outcome


class Reporter:
    """Reports a backup outcome to the Backup API.

    Args:
        config: Agent configuration.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def report(self, outcome: BackupOutcome) -> bool:
        """Send the outcome to ``POST /api/v1/backups``.

        Args:
            outcome: The completed backup outcome.

        Returns:
            True when the API accepted the report (2xx).
        """
        payload = {
            "application": self._config.application,
            "database_type": self._config.database_type,
            "database_name": self._config.db_name,
            "status": outcome.status,
            "started_at": outcome.started_at.isoformat(),
            "finished_at": outcome.finished_at.isoformat(),
            "duration_seconds": outcome.duration_seconds,
            "size_bytes": outcome.size_bytes,
            "storage": self._config.storage_driver,
            "storage_path": outcome.storage_path,
            "checksum": outcome.checksum,
            "error": outcome.error,
        }
        url = f"{self._config.api_url.rstrip('/')}/api/v1/backups"
        try:
            response = httpx.post(
                url, json=payload, headers={"X-API-Key": self._config.api_key}, timeout=30
            )
        except httpx.HTTPError as exc:
            self._log_failure(f"request failed: {exc}")
            return False
        if response.status_code >= 300:
            self._log_failure(f"status {response.status_code}: {response.text[:200]}")
            return False
        return True

    def _log_failure(self, message: str) -> None:
        """Log a report failure.

        Args:
            message: Human-readable failure detail.
        """
        logger = get_logger("backup-agent.reporter")
        logger.error("backup result reporting failed", error=message)


def cleanup(file_path: str | None) -> None:
    """Remove a temporary backup file if present.

    Args:
        file_path: Path to remove, or None to no-op.
    """
    if file_path:
        Path(file_path).unlink(missing_ok=True)


def prune(retention_days: int, base_dir: str) -> int:
    """Delete local backups older than the retention window (PRD section 13).

    Args:
        retention_days: Number of days to retain.
        base_dir: Directory containing per-application backup folders.

    Returns:
        The number of removed files.
    """
    import time

    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    root = Path(base_dir)
    removed = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".gz", ".dump"} and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed