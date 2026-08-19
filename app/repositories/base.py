"""Generic async repository base class."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Thin data-access layer over an async session.

    Args:
        db: The active AsyncSession.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, model: type[ModelT], object_id: int) -> ModelT | None:
        """Fetch a single row by primary key.

        Args:
            model: The ORM model class to query.
            object_id: Primary key value.

        Returns:
            The matching instance or None when not found.
        """
        result = await self._db.get(model, object_id)
        return result

    async def list_all(self, model: type[ModelT]) -> list[ModelT]:
        """Return all rows for a model.

        Args:
            model: The ORM model class to query.

        Returns:
            A list of all instances.
        """
        result = await self._db.execute(select(model))
        return list(result.scalars().all())

    async def add(self, instance: ModelT) -> ModelT:
        """Persist a new instance.

        Args:
            instance: The ORM instance to add.

        Returns:
            The instance after flush.
        """
        self._db.add(instance)
        await self._db.flush()
        return instance
