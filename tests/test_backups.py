"""Tests for backup run endpoints and overdue detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application
from app.models.backup_run import BackupRun
from app.services.application_service import ApplicationService


async def _seed(db: AsyncSession, name: str = "talenta") -> Application:
    service = ApplicationService(db)
    return await service.create(
        name=name,
        environment="production",
        database_type="postgresql",
        schedule="daily",
        is_active=True,
        api_key=f"key-{name}",
    )


def _payload(status: str = "success", app: str = "talenta") -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "application": app,
        "database_type": "postgresql",
        "database_name": app,
        "status": status,
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
        "duration_seconds": 100,
        "size_bytes": 1024,
        "storage": "rustfs",
        "storage_path": f"{app}/backup.sql.gz",
        "checksum": "sha256:x",
        "error": None,
    }


async def test_list_backups_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    """Listing backups with no data returns an empty list."""
    response = await client.get("/api/v1/backups")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_and_get_backup(client: AsyncClient, db_session: AsyncSession) -> None:
    """A backup can be created and fetched by id."""
    await _seed(db_session)
    await db_session.commit()

    created = await client.post(
        "/api/v1/backups", json=_payload(), headers={"X-API-Key": "key-talenta"}
    )
    assert created.status_code == 201
    backup_id = created.json()["id"]

    fetched = await client.get(f"/api/v1/backups/{backup_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == backup_id


async def test_list_backups_filter_by_status(client: AsyncClient, db_session: AsyncSession) -> None:
    """Backups can be filtered by status."""
    await _seed(db_session)
    await db_session.commit()
    headers = {"X-API-Key": "key-talenta"}

    await client.post("/api/v1/backups", json=_payload("success"), headers=headers)
    await client.post("/api/v1/backups", json=_payload("failed"), headers=headers)

    response = await client.get("/api/v1/backups", params={"status": "FAILED"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "FAILED"


async def test_application_status_after_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """An application with a fresh success is not overdue."""
    application = await _seed(db_session)
    await db_session.commit()

    await client.post(
        "/api/v1/backups", json=_payload("success"), headers={"X-API-Key": "key-talenta"}
    )

    response = await client.get(f"/api/v1/applications/{application.id}/backup-status")
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"


async def test_application_overdue(client: AsyncClient, db_session: AsyncSession) -> None:
    """An application whose last success is older than its schedule is overdue."""
    application = await _seed(db_session)
    await db_session.commit()

    old = datetime.now(timezone.utc) - timedelta(hours=36)
    run = BackupRun(
        application_id=application.id,
        status="SUCCESS",
        started_at=old,
        finished_at=old,
        duration_seconds=100,
        size_bytes=1024,
        storage_provider="rustfs",
        storage_path="talenta/backup.sql.gz",
    )
    db_session.add(run)
    await db_session.commit()

    response = await client.get(f"/api/v1/applications/{application.id}/backup-status")
    assert response.status_code == 200
    assert response.json()["status"] == "OVERDUE"