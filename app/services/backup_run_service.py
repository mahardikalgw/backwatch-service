"""Business logic for recording backup runs and app status."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app import metrics
from app.models.application import Application
from app.models.backup_run import BackupRun
from app.repositories.application_repository import ApplicationRepository
from app.repositories.backup_run_repository import BackupRunRepository
from app.schemas.application import ApplicationStatus
from app.schemas.backup_run import BackupRunCreate
from app.services.overdue_service import is_overdue


class BackupRunService:
    """Coordinates backup run persistence and metric updates.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._runs = BackupRunRepository(db)
        self._applications = ApplicationRepository(db)

    async def record(self, application: Application, payload: BackupRunCreate) -> BackupRun:
        """Persist a backup result reported by an agent.

        Args:
            application: The authenticated application reporting the run.
            payload: Validated backup result.

        Returns:
            The saved BackupRun.
        """
        status = payload.status.upper()
        run = BackupRun(
            application_id=application.id,
            status=status,
            started_at=payload.started_at,
            finished_at=payload.finished_at,
            duration_seconds=payload.duration_seconds,
            size_bytes=payload.size_bytes,
            storage_provider=payload.storage,
            storage_path=payload.storage_path,
            checksum=payload.checksum,
            error_message=payload.error,
        )
        created = await self._runs.create_run(run)
        await self._update_metrics(application, created)
        return created

    async def get_run(self, backup_id: int) -> BackupRun | None:
        """Fetch a single backup run by id.

        Args:
            backup_id: The backup run id.

        Returns:
            The matching BackupRun or None.
        """
        return await self._runs.get_by_id(backup_id)

    async def _update_metrics(self, application: Application, run: BackupRun) -> None:
        """Refresh Prometheus gauges/counters for an application after a run.

        Args:
            application: The application that ran the backup.
            run: The recorded run.
        """
        labels = {"application": application.name, "database_type": application.database_type}
        if run.status == "SUCCESS":
            metrics._SUCCESS_COUNTER.labels(**labels).inc()
            if run.finished_at is not None:
                metrics.LAST_SUCCESS_TS.labels(application=application.name).set(run.finished_at.timestamp())
            if run.duration_seconds is not None:
                metrics.DURATION_SECONDS.labels(application=application.name).set(run.duration_seconds)
            if run.size_bytes is not None:
                metrics.SIZE_BYTES.labels(application=application.name).set(run.size_bytes)
        elif run.status == "FAILED":
            metrics._FAILURE_COUNTER.labels(**labels).inc()
            if run.finished_at is not None:
                metrics.LAST_FAILURE_TS.labels(application=application.name).set(run.finished_at.timestamp())

    async def application_status(self, application: Application, now: datetime) -> ApplicationStatus:
        """Compute the current status label for a single application.

        Priority is OVERDUE > FAILED > SUCCESS/RUNNING, matching PRD section 8.

        Args:
            application: The application under evaluation.
            now: Current reference time.

        Returns:
            An ApplicationStatus describing the application's latest state.
        """
        last_success = await self._runs.latest_success(application.id)
        latest = await self._runs.latest_run(application.id)

        if is_overdue(application, last_success.started_at if last_success else None, now):
            status = "OVERDUE"
        elif latest is not None and latest.status == "FAILED":
            status = "FAILED"
        elif latest is not None and latest.status == "SUCCESS":
            status = "SUCCESS"
        elif latest is not None and latest.status == "RUNNING":
            status = "RUNNING"
        else:
            status = "NO_BACKUP"

        return ApplicationStatus(
            application_id=application.id,
            application=application.name,
            status=status,
            last_backup_at=latest.started_at if latest else None,
            last_backup_status=latest.status if latest else None,
            last_backup_duration_seconds=latest.duration_seconds if latest else None,
            last_backup_size_bytes=latest.size_bytes if latest else None,
        )

    async def list_runs(
        self,
        application_name: str | None,
        status: str | None,
        database_type: str | None,
        since: datetime | None,
    ) -> list[BackupRun]:
        """Return backup runs across all applications with optional filters.

        Args:
            application_name: Optional application name filter.
            status: Optional status filter.
            database_type: Optional database type filter.
            since: Optional start datetime filter.

        Returns:
            A list of matching BackupRun instances.
        """
        all_runs = await self._runs.list_all()
        if application_name is not None:
            application = await self._applications.get_by_name(application_name)
            if application is None:
                return []
            all_runs = [r for r in all_runs if r.application_id == application.id]
        if status is not None:
            all_runs = [r for r in all_runs if r.status == status.upper()]
        if since is not None:
            all_runs = [r for r in all_runs if r.started_at >= since]
        filtered: list[BackupRun] = []
        for run in all_runs:
            application = await self._applications.get_by_id(run.application_id)
            if application is not None and (database_type is None or application.database_type == database_type):
                filtered.append(run)
        return filtered


def utcnow() -> datetime:
    """Return the current UTC time.

    Returns:
        A timezone-aware datetime.
    """
    return datetime.now(timezone.utc)
