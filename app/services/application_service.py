"""Business logic for application registration."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.models.application import Application
from app.repositories.application_repository import ApplicationRepository


class ApplicationService:
    """Manages applications.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._repository = ApplicationRepository(db)

    async def create(
        self,
        name: str,
        environment: str,
        database_type: str,
        schedule: str,
        is_active: bool,
        api_key: str,
    ) -> Application:
        """Register a new application with a per-application API key.

        Args:
            name: Unique application slug.
            environment: Deployment environment.
            database_type: Database type (``postgresql``/``mysql``).
            schedule: Backup frequency.
            is_active: Whether the application is enabled.
            api_key: Raw API key; only its digest is stored.

        Returns:
            The created Application.

        Raises:
            HTTPException: 409 when the application name already exists.
        """
        if await self._repository.get_by_name(name) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Application exists")

        application = Application(
            name=name,
            environment=environment,
            database_type=database_type,
            schedule=schedule,
            is_active=is_active,
            api_key_hash=hash_api_key(api_key),
        )
        return await self._repository.add(application)

    async def list(self) -> list[Application]:
        """Return all active applications.

        Returns:
            A list of active Application instances.
        """
        return await self._repository.list_active()

    async def get(self, application_id: int) -> Application | None:
        """Fetch a single application by id.

        Args:
            application_id: The application id.

        Returns:
            The matching Application or None.
        """
        return await self._repository.get_by_id(application_id)