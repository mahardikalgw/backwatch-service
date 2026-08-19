"""Optional backup event log model (PRD section 11)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BackupEvent(Base):
    """A granular event emitted during a backup run.

    Attributes:
        id: Primary key.
        backup_run_id: Foreign key to :class:`BackupRun`.
        event: Event name (e.g. ``STARTED``, ``UPLOAD_COMPLETED``).
        message: Human-readable detail.
        timestamp: When the event occurred.
    """

    __tablename__ = "backup_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    backup_run_id: Mapped[int] = mapped_column(
        ForeignKey("backup_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )