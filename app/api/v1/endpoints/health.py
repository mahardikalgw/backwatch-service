"""Health endpoint for the service itself."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple liveness response.

    Returns:
        A dict indicating the service is operational.
    """
    return {"status": "ok"}