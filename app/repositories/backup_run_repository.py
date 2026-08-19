"""Data access for :class:`BackupRun` records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backup_run import BackupRun
from app.repositories.base import BaseRepository


class BackupRunRepository(BaseRepository[BackupRun]):
    """CRUD and queries for backup runs.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)
        self._model = BackupRun

    async def get_by_id(self, backup_id: int) -> BackupRun | None:
        """Fetch a backup run by primary key.

        Args:
            backup_id: The backup run id.

        Returns:
            The matching BackupRun or None.
        """
        return await self.get(self._model, backup_id)

    async def list_for_application(
        self,
        application_id: int,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BackupRun]:
        """List backup runs for a single application with optional filters.

        Args:
            application_id: The application to filter on.
            status: Optional status filter.
            since: Optional start datetime filter.
            limit: Maximum number of runs to return.

        Returns:
            An ordered list of BackupRun instances (newest first).
        """
        statement = select(self._model).where(self._model.application_id == application_id)
        if status is not None:
            statement = statement.where(self._model.status == status)
        if since is not None:
            statement = statement.where(self._model.started_at >= since)

        if status is not None or since is not None or limit is not None:
            statement = statement.order_by(desc(self._model.started_at)).limit(limit)

        result = await self._db.execute(statement)
        return list(result.scalars().all())

    async def list_all(self, model: type[BackupRun] | None = None) -> list[BackupRun]:
        """Return all backup runs across all applications.

        Args:
            model: Ignored; kept for interface compatibility.

        Returns:
            A list of BackupRun instances ordered newest first.
        """
        result = await self._db.execute(select(self._model).order_by(desc(self._model.started_at)))
        return list(result.scalars().all())

    async def create_run(self, run: BackupRun) -> BackupRun:
        """Persist a new backup run.

        Args:
            run: The BackupRun instance to save.

        Returns:
            The saved instance.
        """
        return await self.add(run)

    async def latest_run(self, application_id: int) -> BackupRun | None:
        """Return the most recent run for an application.

        Args:
            application_id: The application id.

        Returns:
            The newest BackupRun or None.
        """
        result = await self._db.execute(
            select(self._model)
            .where(self._model.application_id == application_id)
            .order_by(desc(self._model.started_at))
            .limit(1)
        )
        return result.scalars().first()

    async def latest_success(self, application_id: int) -> BackupRun | None:
        """Return the most recent successful run for an application.

        Args:
            application_id: The application id.

        Returns:
            The newest successful BackupRun or None.
        """
        result = await self._db.execute(
            select(self._model)
            .where(self._model.application_id == application_id, self._model.status == "SUCCESS")
            .order_by(desc(self._model.started_at))
            .limit(1)
        )
        return result.scalars().first()

    async def latest_failure(self, application_id: int) -> BackupRun | None:
        """Return the most recent failed run for an application.

        Args:
            application_id: The application id.

        Returns:
            The newest failed BackupRun or None.
        """
        result = await self._db.execute(
            select(self._model)
            .where(self._model.application_id == application_id, self._model.status == "FAILED")
            .order_by(desc(self._model.started_at))
            .limit(1)
        )
        return result.scalars().first()
