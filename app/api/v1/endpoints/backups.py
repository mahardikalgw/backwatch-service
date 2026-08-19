"""Backup run endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_application
from app.models.application import Application
from app.models.backup_run import BackupRun
from app.schemas.backup_run import BackupRunCreate, BackupRunRead
from app.services.backup_run_service import BackupRunService

router = APIRouter(prefix="/backups", tags=["backups"])


@router.post("", response_model=BackupRunRead, status_code=status.HTTP_201_CREATED)
async def create_backup_run(
    payload: BackupRunCreate,
    db: AsyncSession = Depends(get_db),
    application: Application = Depends(get_current_application),
) -> object:
    """Record a backup result reported by an agent.

    Args:
        payload: Validated backup result.
        db: Active database session.
        application: Authenticated application (from API key).

    Returns:
        The saved backup run.
    """
    service = BackupRunService(db)
    return await service.record(application, payload)


@router.get("", response_model=list[BackupRunRead])
async def list_backup_runs(
    application: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date: datetime | None = Query(default=None),
    database_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[BackupRun]:
    """Retrieve backup history with optional filters.

    Args:
        application: Optional application name filter.
        status_filter: Optional status filter.
        date: Optional start datetime filter.
        database_type: Optional database type filter.
        db: Active database session.

    Returns:
        A list of matching backup runs.
    """
    service = BackupRunService(db)
    runs = await service.list_runs(
        application_name=application,
        status=status_filter,
        database_type=database_type,
        since=date,
    )
    return runs


@router.get("/{backup_id}", response_model=BackupRunRead)
async def get_backup_run(backup_id: int, db: AsyncSession = Depends(get_db)) -> object:
    """Return a single backup run by id.

    Args:
        backup_id: The backup run id.
        db: Active database session.

    Returns:
        The matching backup run.

    Raises:
        HTTPException: 404 when the run does not exist.
    """
    service = BackupRunService(db)
    run = await service.get_run(backup_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup run not found")
    return run
