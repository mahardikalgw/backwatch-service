"""Periodic watcher for the Backup API (PRD sections 16 and 18).

Refreshes the ``backup_overdue`` metric and emits failure/overdue alerts once
per incident. Intended to run on the API host every 15 minutes via a systemd
timer so failures are detected within the "<= 15 minutes" target in PRD
section 20.

Run manually:
    PYTHONPATH=. .venv/bin/python scripts/overdue_watcher.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.repositories.application_repository import ApplicationRepository
from app.repositories.backup_run_repository import BackupRunRepository
from app.services.alerting import failed_backup_alert, overdue_alert
from app.services.backup_health_service import BackupHealthService
from app.services.backup_run_service import utcnow

STATEDIR_FALLBACK = "/var/lib/backwatch"


def _load_state(path: Path) -> dict[str, str]:
    """Load the previous per-application status map.

    Args:
        path: State file location.

    Returns:
        A dict mapping application name to the last alertable status.
    """
    try:
        return cast(dict[str, str], json.loads(path.read_text()))
    except (OSError, ValueError):
        return {}


def _save_state(path: Path, state: dict[str, str]) -> None:
    """Persist the current per-application status map.

    Args:
        path: State file location.
        state: Mapping of application name to alertable status.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, sort_keys=True, indent=2))


async def _alert_incident(app_name: str, status: str, session: AsyncSession) -> None:
    """Send a failure or overdue alert for a new incident.

    Args:
        app_name: The application name.
        status: The new alertable status (``FAILED`` or ``OVERDUE``).
        session: Active database session.
    """
    logger = logging.getLogger("backwatch.watcher")
    application_rows = ApplicationRepository(session)
    runs = BackupRunRepository(session)
    application = await application_rows.get_by_name(app_name)
    database_type = application.database_type if application else "unknown"

    error: str | None = None
    if status == "FAILED" and application is not None:
        failed = await runs.latest_failure(application.id)
        error = failed.error_message if failed else None

    delivered = failed_backup_alert(app_name, database_type, error) if status == "FAILED" else overdue_alert(app_name)
    logger.info("alert dispatched for %s (%s): %s", app_name, status, delivered)


async def run_once() -> int:
    """Run a single watcher pass.

    Returns:
        0 on success, 1 when the pass could not complete.
    """
    logger = logging.getLogger("backwatch.watcher")
    state_file = Path(os.getenv("BACKWATCH_STATE_FILE", f"{STATEDIR_FALLBACK}/watcher-state.json"))
    previous = _load_state(state_file)
    current: dict[str, str] = {}

    try:
        async with AsyncSessionLocal() as session:
            service = BackupHealthService(session)
            await service.refresh_overdue_metrics(utcnow())
            statuses = await service.all_statuses(utcnow())
            for item in statuses:
                app_name = str(item["application"])
                status = str(item["status"])
                current[app_name] = status
                if status in {"FAILED", "OVERDUE"} and previous.get(app_name) != status:
                    await _alert_incident(app_name, status, session)
    except Exception:  # noqa: BLE001 - the watcher must never crash silently
        logger.exception("watcher pass failed")
        return 1

    _save_state(state_file, current)
    return 0


def main() -> int:
    """Configure logging and run one watcher pass.

    Returns:
        The pass exit code.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return asyncio.run(run_once())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
