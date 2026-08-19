"""Data access for :class:`Application` records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    """CRUD and lookups for applications.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:

        super().__init__(db)
        self._model = Application

    async def get_by_id(self, application_id: int) -> Application | None:
        """Fetch an application by primary key.

        Args:
            application_id: The application id.

        Returns:
            The matching Application or None.
        """
        return await self.get(self._model, application_id)

    async def get_by_name(self, name: str) -> Application | None:
        """Fetch an application by its unique name.

        Args:
            name: Unique application slug.

        Returns:
            The matching Application or None.
        """
        result = await self._db.execute(select(self._model).where(self._model.name == name))
        return result.scalars().first()

    async def find_by_api_key_hash(self, api_key_hash: str) -> Application | None:
        """Fetch an application by its stored API key digest.

        Args:
            api_key_hash: Salted SHA-256 digest of the API key.

        Returns:
            The matching active-or-not Application or None.
        """
        result = await self._db.execute(select(self._model).where(self._model.api_key_hash == api_key_hash))
        return result.scalars().first()

    async def list_active(self) -> list[Application]:
        """Return all active applications.

        Returns:
            A list of active Application instances.
        """
        result = await self._db.execute(
            select(self._model).where(self._model.is_active.is_(True)).order_by(self._model.name)
        )
        return list(result.scalars().all())
