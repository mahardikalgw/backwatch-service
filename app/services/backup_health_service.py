"""Aggregate backup health (PRD sections 10 and 16)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.application_repository import ApplicationRepository
from app.schemas.backup_run import BackupHealth
from app.services.backup_run_service import BackupRunService


class BackupHealthService:
    """Computes global backup health across all applications.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._applications = ApplicationRepository(db)
        self._runs = BackupRunService(db)

    async def compute(self, now: datetime) -> BackupHealth:
        """Compute the overall health summary.

        Args:
            now: Current reference time.

        Returns:
            A BackupHealth summary with counts per status bucket.
        """
        applications = await self._applications.list_active()
        total = len(applications)
        healthy = 0
        failed = 0
        overdue = 0

        for application in applications:
            app_status = await self._runs.application_status(application, now)
            if app_status.status == "OVERDUE":
                overdue += 1
            elif app_status.status == "FAILED":
                failed += 1
            else:
                healthy += 1

        if overdue > 0 or failed > 0:
            status = "degraded"
        elif total == 0:
            status = "unknown"
        else:
            status = "healthy"

        return BackupHealth(
            status=status,
            total=total,
            healthy=healthy,
            failed=failed,
            overdue=overdue,
        )

    async def all_statuses(self, now: datetime) -> list[dict[str, Any]]:
        """Return per-application status plus the OVERDUE metric flag.

        Args:
            now: Current reference time.

        Returns:
            A list of status dicts for each active application.
        """
        applications = await self._applications.list_active()
        result: list[dict[str, object]] = []
        for app in applications:
            app_status = await self._runs.application_status(app, now)
            result.append(
                {
                    "application": app.name,
                    "status": app_status.status,
                    "overdue": 1 if app_status.status == "OVERDUE" else 0,
                }
            )
        return result

    async def refresh_overdue_metrics(self, now: datetime) -> None:
        """Set the ``backup_overdue`` gauge for every active application.

        Args:
            now: Current reference time.
        """
        from app import metrics

        statuses = await self.all_statuses(now)
        for item in statuses:
            metrics.OVERDUE.labels(application=str(item["application"])).set(float(item["overdue"]))
