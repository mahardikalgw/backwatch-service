"""Tests for the health endpoint."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    """The service health endpoint returns ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
