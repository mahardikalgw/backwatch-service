"""Pydantic schemas for backup runs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BackupRunCreate(BaseModel):
    """Payload sent by a backup agent to record a completed backup.

    Matches the structured record in PRD section 7.
    """

    application: str = Field(..., min_length=1)
    database_type: str = Field(..., pattern="^(postgresql|mysql)$")
    database_name: str = Field(..., min_length=1)
    status: str = Field(..., pattern="^(success|failed|running)$")
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)
    storage: str = Field(default="rustfs", max_length=32)
    storage_path: str | None = None
    checksum: str | None = None
    error: str | None = None


class BackupRunRead(BaseModel):
    """Backup run representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    size_bytes: int | None = None
    storage_provider: str | None = None
    storage_path: str | None = None
    checksum: str | None = None
    error_message: str | None = None
    created_at: datetime


class BackupHealth(BaseModel):
    """Aggregate backup health across all applications (PRD section 10)."""

    status: str
    total: int
    healthy: int
    failed: int
    overdue: int
