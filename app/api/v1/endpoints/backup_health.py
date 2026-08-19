"""Global backup health endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.backup_run import BackupHealth
from app.services.backup_health_service import BackupHealthService
from app.services.backup_run_service import utcnow

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/backups", response_model=BackupHealth)
async def backup_health(db: AsyncSession = Depends(get_db)) -> BackupHealth:
    """Return the health status of all backups.

    Args:
        db: Active database session.

    Returns:
        A BackupHealth summary across all applications.
    """
    service = BackupHealthService(db)
    return await service.compute(utcnow())
