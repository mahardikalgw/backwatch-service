"""Tests for the aggregate backup health endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backup_run import BackupRun
from app.services.application_service import ApplicationService


async def _seed(db: AsyncSession, name: str, api_key: str) -> None:
    service = ApplicationService(db)
    await service.create(
        name=name,
        environment="production",
        database_type="postgresql",
        schedule="daily",
        is_active=True,
        api_key=api_key,
    )


async def test_backup_health_healthy(client: AsyncClient, db_session: AsyncSession) -> None:
    """With fresh successes, health is healthy."""
    await _seed(db_session, "talenta", "key-a")
    await _seed(db_session, "simaira", "key-b")
    await db_session.commit()

    now = datetime.now(timezone.utc)
    for app in ["talenta", "simaira"]:
        db_session.add(
            BackupRun(
                application_id=1 if app == "talenta" else 2,
                status="SUCCESS",
                started_at=now,
                finished_at=now,
                duration_seconds=100,
                size_bytes=1024,
                storage_provider="rustfs",
            )
        )
    await db_session.commit()

    response = await client.get("/api/v1/health/backups")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["healthy"] == 2
    assert data["failed"] == 0
    assert data["overdue"] == 0
    assert data["status"] == "healthy"


async def test_backup_health_failed(client: AsyncClient, db_session: AsyncSession) -> None:
    """A failed backup reports the health as degraded."""
    await _seed(db_session, "talenta", "key-a")
    await db_session.commit()

    now = datetime.now(timezone.utc)
    db_session.add(
        BackupRun(
            application_id=1,
            status="FAILED",
            started_at=now,
            finished_at=now,
            duration_seconds=10,
            storage_provider="rustfs",
            error_message="pg_dump exited with code 1",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/health/backups")
    data = response.json()
    assert data["status"] == "degraded"
    assert data["failed"] == 1


async def test_backup_health_overdue(client: AsyncClient, db_session: AsyncSession) -> None:
    """An overdue application contributes to the overdue count."""
    await _seed(db_session, "talenta", "key-a")
    await db_session.commit()

    old = datetime.now(timezone.utc) - timedelta(hours=48)
    db_session.add(
        BackupRun(
            application_id=1,
            status="SUCCESS",
            started_at=old,
            finished_at=old,
            duration_seconds=100,
            size_bytes=1024,
            storage_provider="rustfs",
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/health/backups")
    data = response.json()
    assert data["overdue"] == 1
    assert data["status"] == "degraded"
