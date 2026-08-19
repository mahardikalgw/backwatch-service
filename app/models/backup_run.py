"""Backup run database model (PRD section 11)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BackupRun(Base):
    """A single recorded backup execution.

    Attributes:
        id: Primary key.
        application_id: Foreign key to :class:`Application`.
        status: One of ``RUNNING``, ``SUCCESS``, ``FAILED``, ``OVERDUE``.
        started_at: When the backup started.
        finished_at: When the backup finished.
        duration_seconds: Total elapsed time in seconds.
        size_bytes: Compressed backup size in bytes.
        storage_provider: Storage backend used (e.g. ``rustfs``).
        storage_path: Object/path where the file was stored.
        checksum: Checksum of the uploaded file (e.g. ``sha256:...``).
        error_message: Error detail when the backup failed.
        created_at: Row creation timestamp.
    """

    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    storage_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )