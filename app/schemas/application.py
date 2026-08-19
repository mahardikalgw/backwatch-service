"""Pydantic schemas for applications."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApplicationBase(BaseModel):
    """Fields shared by create/read application schemas."""

    name: str = Field(..., min_length=1, max_length=64)
    environment: str = Field(default="production", max_length=32)
    database_type: str = Field(..., pattern="^(postgresql|mysql)$")
    schedule: str = Field(default="daily", max_length=32)
    is_active: bool = True


class ApplicationCreate(ApplicationBase):
    """Payload for registering a new application."""

    api_key: str = Field(..., min_length=8, max_length=256)


class ApplicationRead(ApplicationBase):
    """Application representation returned by the API.

    The raw API key is never exposed; only the hash is stored server side.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ApplicationStatus(BaseModel):
    """Latest backup status for a single application."""

    application_id: int
    application: str
    status: str
    last_backup_at: datetime | None = None
    last_backup_status: str | None = None
    last_backup_duration_seconds: int | None = None
    last_backup_size_bytes: int | None = None
