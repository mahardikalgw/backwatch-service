"""API v1 router aggregating all endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import applications, backup_health, backups

api_router = APIRouter()
api_router.include_router(backup_health.router)
api_router.include_router(applications.router)
api_router.include_router(backups.router)