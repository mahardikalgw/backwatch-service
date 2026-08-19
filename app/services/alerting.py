"""Alert notification stub (PRD section 18).

The MVP supports Telegram, Discord and Email. This module provides a lightweight
notifier that logs a formatted alert and can be wired to real channels via
environment-configured webhook URLs.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.backup_run_service import utcnow


def _linearize(payload: dict[str, Any]) -> str:
    """Render an alert payload as a multi-line message.

    Args:
        payload: Alert fields (application, database_type, time, error, ...).

    Returns:
        A human-readable alert message.
    """
    lines = [payload.pop("title", "BACKUP ALERT")]
    lines.append("")
    for key, value in payload.items():
        lines.append(f"{key.title().replace('_', ' ')}: {value}")
    return "\n".join(lines)


def notify(payload: dict[str, Any]) -> bool:
    """Dispatch an alert to the configured channel(s).

    Args:
        payload: Alert fields describing the incident.

    Returns:
        True when the alert was accepted by at least one channel.
    """
    import logging

    webhook = os.getenv("ALERT_WEBHOOK_URL", "")
    message = _linearize(dict(payload))

    if webhook:
        try:
            response = httpx.post(webhook, json={"text": message}, timeout=10)
            return response.status_code < 300
        except httpx.HTTPError:
            logging.getLogger("backwatch.alert").exception("webhook delivery failed")
            return False

    logging.getLogger("backwatch.alert").warning("alert (no webhook configured):\n%s", message)
    return True


def failed_backup_alert(application: str, database_type: str, error: str | None) -> bool:
    """Send a 'backup failed' alert.

    Args:
        application: Application name.
        database_type: Database type.
        error: Failure detail, when known.

    Returns:
        True when delivered.
    """
    return notify(
        {
            "title": "BACKUP FAILED",
            "application": application,
            "database": database_type.title(),
            "time": utcnow().isoformat(),
            "error": error or "unknown",
        }
    )


def overdue_alert(application: str) -> bool:
    """Send a 'backup overdue' alert.

    Args:
        application: Application name.

    Returns:
        True when delivered.
    """
    return notify(
        {
            "title": "BACKUP OVERDUE",
            "application": application,
            "time": utcnow().isoformat(),
        }
    )
