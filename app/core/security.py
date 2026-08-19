"""Per-application API key authentication.

Each application is issued a unique API key (PRD section 19). The raw key is
never stored; only a salted SHA-256 digest is persisted, so a leaked database
does not expose usable credentials.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.application import Application
from app.repositories.application_repository import ApplicationRepository

settings = get_settings()


def hash_api_key(api_key: str) -> str:
    """Return a salted digest of an API key for safe storage/comparison.

    Args:
        api_key: The raw API key supplied by a backup agent.

    Returns:
        Hex digest used both when persisting and when looking up the key.
    """
    digest = hmac.new(settings.secret_key.encode(), api_key.encode(), hashlib.sha256)
    return digest.hexdigest()


async def get_current_application(
    db: AsyncSession = Depends(get_db),
    api_key: str = Header(default="", alias=settings.api_key_header),
) -> Application:
    """Resolve the requesting application from its API key.

    Args:
        db: Active database session.
        api_key: Value of the API key header.

    Returns:
        The matching Application.

    Raises:
        HTTPException: 401 when the key is missing or unknown.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    repository = ApplicationRepository(db)
    digest = hash_api_key(api_key)
    application = await repository.find_by_api_key_hash(digest)

    if application is None or not application.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return application
