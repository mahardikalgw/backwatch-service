"""Application database model (PRD section 11)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Application(Base):
    """A registered application whose database is backed up.

    Attributes:
        id: Primary key.
        name: Unique application slug (e.g. ``talenta``).
        environment: Deployment environment (e.g. ``production``).
        database_type: ``postgresql`` or ``mysql``.
        schedule: Backup frequency string (e.g. ``daily``).
        is_active: Whether the application is enabled.
        api_key_hash: Salted digest of the application's API key.
        created_at: Row creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    environment: Mapped[str] = mapped_column(String(32), default="production", nullable=False)
    database_type: Mapped[str] = mapped_column(String(16), nullable=False)
    schedule: Mapped[str] = mapped_column(String(32), default="daily", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )