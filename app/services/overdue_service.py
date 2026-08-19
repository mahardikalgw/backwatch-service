"""Overdue detection logic (PRD section 8).

An application is considered overdue when there is no successful backup within
its expected schedule interval. ``daily`` maps to 24 hours; other frequencies
fall back to a per-application interval when the schedule encodes hours.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.application import Application

#: Default interval in seconds when the schedule string is "daily".
DEFAULT_DAILY_SECONDS = 24 * 60 * 60

#: Recognized schedule frequencies mapped to interval seconds.
_SCHEDULE_INTERVALS: dict[str, int] = {
    "daily": 24 * 60 * 60,
    "hourly": 60 * 60,
    "weekly": 7 * 24 * 60 * 60,
}


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Return a timezone-aware copy of ``value``.

    SQLite-backed sessions return naive datetimes; this normalizes them to UTC
    so arithmetic with aware ``now`` timestamps is valid.

    Args:
        value: A datetime which may be naive or aware.

    Returns:
        An aware datetime, or None when the input is None.
    """
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def schedule_interval_seconds(schedule: str) -> int:
    """Return the expected interval for a schedule string.

    Args:
        schedule: A schedule frequency (e.g. ``daily``) or an encoded interval.

    Returns:
        The interval in seconds.
    """
    normalized = schedule.strip().lower()
    if normalized in _SCHEDULE_INTERVALS:
        return _SCHEDULE_INTERVALS[normalized]
    # Allow notation like "24h" or "12h30m" for custom schedules.
    seconds = 0
    number = ""
    for char in normalized:
        if char.isdigit():
            number += char
        elif char == "h" and number:
            seconds += int(number) * 3600
            number = ""
        elif char == "m" and number:
            seconds += int(number) * 60
            number = ""
        else:
            number = ""
    return seconds if seconds > 0 else DEFAULT_DAILY_SECONDS


def is_overdue(application: Application, last_success_at: datetime | None, now: datetime) -> bool:
    """Determine whether an application's backup is overdue.

    Args:
        application: The application under evaluation.
        last_success_at: Timestamp of the last successful backup (None if never).
        now: Current reference time.

    Returns:
        True when there is no success within the schedule interval.
    """
    interval = schedule_interval_seconds(application.schedule)
    reference_now = _ensure_aware(now) or datetime.now(timezone.utc)
    success = _ensure_aware(last_success_at)
    if success is None:
        # Never succeeded: overdue once the initial schedule window has passed.
        created = _ensure_aware(application.created_at) or reference_now
        return reference_now - created >= timedelta(seconds=interval)
    return reference_now - success > timedelta(seconds=interval)
