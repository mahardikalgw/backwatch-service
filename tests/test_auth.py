"""Tests for API-key authentication on backup ingestion."""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_api_key
from app.models import Application
from app.services.application_service import ApplicationService


async def _seed_application(db: AsyncSession, name: str = "talenta", api_key: str = "secret-key-1") -> Application:
    service = ApplicationService(db)
    return await service.create(
        name=name,
        environment="production",
        database_type="postgresql",
        schedule="daily",
        is_active=True,
        api_key=api_key,
    )


def _payload(application: str = "talenta") -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "application": application,
        "database_type": "postgresql",
        "database_name": application,
        "status": "success",
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
        "duration_seconds": 192,
        "size_bytes": 2483920128,
        "storage": "rustfs",
        "storage_path": "talenta/2026/08/12/backup.sql.gz",
        "checksum": "sha256:abc",
        "error": None,
    }


async def test_post_backup_requires_api_key(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/v1/backups without a key is rejected."""
    response = await client.post("/api/v1/backups", json=_payload())
    assert response.status_code == 401


async def test_post_backup_with_valid_key(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/v1/backups with a valid key creates a run."""
    await _seed_application(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/backups",
        json=_payload(),
        headers={"X-API-Key": "secret-key-1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["storage_provider"] == "rustfs"


async def test_post_backup_with_invalid_key(client: AsyncClient, db_session: AsyncSession) -> None:
    """POST /api/v1/backups with an unknown key is rejected."""
    await _seed_application(db_session)
    await db_session.commit()

    response = await client.post(
        "/api/v1/backups",
        json=_payload(),
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


async def test_hash_api_key_is_deterministic() -> None:
    """The API key digest is stable for the same input."""
    assert hash_api_key("abc123") == hash_api_key("abc123")
    assert hash_api_key("abc123") != hash_api_key("abc124")
