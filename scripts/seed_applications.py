"""Seed the five applications and print their API keys.

Run against a prepared database:
    PYTHONPATH=. .venv/bin/python scripts/seed_applications.py
"""

from __future__ import annotations

import asyncio
import secrets
import sys

from app.core.database import Base, engine
from app.core.security import hash_api_key
from app.models import Application  # noqa: F401  register model

APPLICATIONS = [
    {"name": "talenta", "environment": "production", "database_type": "postgresql"},
    {"name": "simaira", "environment": "production", "database_type": "postgresql"},
    {"name": "cakra", "environment": "production", "database_type": "postgresql"},
    {"name": "liyatra", "environment": "production", "database_type": "mysql"},
    {"name": "app-e", "environment": "production", "database_type": "mysql"},
]


async def seed() -> None:
    """Create the applications table and the five default applications."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.repositories.application_repository import ApplicationRepository

    async with AsyncSession(engine) as session:
        repository = ApplicationRepository(session)
        print("Registering applications...")
        for item in APPLICATIONS:
            existing = await repository.get_by_name(item["name"])
            if existing is not None:
                print(f"  - {item['name']}: already exists, skipping")
                continue
            api_key = secrets.token_urlsafe(24)
            application = Application(
                name=item["name"],
                environment=item["environment"],
                database_type=item["database_type"],
                schedule="daily",
                is_active=True,
                api_key_hash=hash_api_key(api_key),
            )
            await repository.add(application)
            await session.commit()
            print(f"  + {item['name']}: {api_key}")
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(seed())
    except Exception as exc:  # pragma: no cover - operational errror
        print(f"Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
