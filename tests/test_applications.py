"""Tests for application endpoints."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.application_service import ApplicationService


async def test_create_and_list_applications(client: AsyncClient, db_session: AsyncSession) -> None:
    """Applications can be created and listed."""
    payload = {
        "name": "talenta",
        "environment": "production",
        "database_type": "postgresql",
        "schedule": "daily",
        "is_active": True,
        "api_key": "super-secret-key-1",
    }
    response = await client.post("/api/v1/applications", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "talenta"
    assert "api_key" not in created  # raw key never exposed

    listing = await client.get("/api/v1/applications")
    assert listing.status_code == 200
    assert any(app["name"] == "talenta" for app in listing.json())


async def test_create_duplicate_application(client: AsyncClient, db_session: AsyncSession) -> None:
    """Creating a duplicate application returns 409."""
    service = ApplicationService(db_session)
    await service.create(
        name="dupe",
        environment="production",
        database_type="postgresql",
        schedule="daily",
        is_active=True,
        api_key="some-api-key-1",
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/applications",
        json={
            "name": "dupe",
            "environment": "production",
            "database_type": "postgresql",
            "schedule": "daily",
            "is_active": True,
            "api_key": "another-key-1",
        },
    )
    assert response.status_code == 409