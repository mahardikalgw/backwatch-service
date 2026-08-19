"""Prometheus instrumentation for the Backup API.

Exposes the metric families described in PRD section 16. Metrics are
instantiated at import time (module scope) as recommended by
prometheus-client and updated by the metric service.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

_SUCCESS_COUNTER = Counter(
    "backup_success_total",
    "Total number of successful backups",
    labelnames=("application", "database_type"),
)
_FAILURE_COUNTER = Counter(
    "backup_failure_total",
    "Total number of failed backups",
    labelnames=("application", "database_type"),
)

LAST_SUCCESS_TS = Gauge(
    "backup_last_success_timestamp",
    "Unix timestamp of the last successful backup",
    labelnames=("application",),
)
LAST_FAILURE_TS = Gauge(
    "backup_last_failure_timestamp",
    "Unix timestamp of the last failed backup",
    labelnames=("application",),
)
DURATION_SECONDS = Gauge(
    "backup_duration_seconds",
    "Duration of the last backup in seconds",
    labelnames=("application",),
)
SIZE_BYTES = Gauge(
    "backup_size_bytes",
    "Size in bytes of the last backup",
    labelnames=("application",),
)
OVERDUE = Gauge(
    "backup_overdue",
    "1 if the application is currently overdue, else 0",
    labelnames=("application",),
)


def reset_metrics() -> None:
    """Clear all metric values (used by tests)."""
    for counter in (_SUCCESS_COUNTER, _FAILURE_COUNTER):
        counter._metrics.clear()
    for gauge in (LAST_SUCCESS_TS, LAST_FAILURE_TS, DURATION_SECONDS, SIZE_BYTES, OVERDUE):
        gauge._metrics.clear()

