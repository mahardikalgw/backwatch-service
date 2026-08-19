"""Pydantic schemas for backup runs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

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
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = Field(default=None, ge=0)
    size_bytes: Optional[int] = Field(default=None, ge=0)
    storage: str = Field(default="rustfs", max_length=32)
    storage_path: Optional[str] = None
    checksum: Optional[str] = None
    error: Optional[str] = None


class BackupRunRead(BaseModel):
    """Backup run representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    size_bytes: Optional[int] = None
    storage_provider: Optional[str] = None
    storage_path: Optional[str] = None
    checksum: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime


class BackupHealth(BaseModel):
    """Aggregate backup health across all applications (PRD section 10)."""

    status: str
    total: int
    healthy: int
    failed: int
    overdue: int