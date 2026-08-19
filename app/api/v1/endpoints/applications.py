"""Application endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.application import Application
from app.schemas.application import ApplicationCreate, ApplicationRead
from app.services.application_service import ApplicationService
from app.services.backup_run_service import BackupRunService, utcnow

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationRead])
async def list_applications(db: AsyncSession = Depends(get_db)) -> list[Application]:
    """List all registered applications.

    Args:
        db: Active database session.

    Returns:
        A list of active applications.
    """
    service = ApplicationService(db)
    return await service.list()


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application(payload: ApplicationCreate, db: AsyncSession = Depends(get_db)) -> object:
    """Register a new application.

    Args:
        payload: Application registration payload.
        db: Active database session.

    Returns:
        The created application.
    """
    service = ApplicationService(db)
    return await service.create(
        name=payload.name,
        environment=payload.environment,
        database_type=payload.database_type,
        schedule=payload.schedule,
        is_active=payload.is_active,
        api_key=payload.api_key,
    )


@router.get("/{application_id}/backup-status")
async def application_backup_status(application_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Return the latest backup status for an application.

    Args:
        application_id: The application id.
        db: Active database session.

    Returns:
        The application status object.

    Raises:
        HTTPException: 404 when the application does not exist.
    """
    service = ApplicationService(db)
    application = await service.get(application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    runs = BackupRunService(db)
    app_status = await runs.application_status(application, utcnow())
    return app_status.model_dump()
