"""ORM models package.

Importing the models here ensures they are registered on the declarative
base before Alembic autogeneration or ``Base.metadata.create_all`` runs.
"""

from __future__ import annotations

from app.models.application import Application
from app.models.backup_event import BackupEvent
from app.models.backup_run import BackupRun

__all__ = ["Application", "BackupRun", "BackupEvent"]
