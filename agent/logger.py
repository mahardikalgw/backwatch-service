"""Structured logging for the backup agent (PRD section 15)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            A JSON string with a timestamp, level, message and extra context.
        """
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in logging.LogRecord.__dict__:
                continue
            if key not in ("message", "timestamp", "level"):
                payload[key] = value
        return json.dumps(payload, default=str)


class StructuredLogger:
    """A thin wrapper that forwards extra context as logging ``extra`` kwargs.

    Args:
        logger: The underlying standard logger.
    """

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def _log(self, level: int, msg: str, kwargs: dict[str, Any]) -> None:
        """Emit a record with the given level and context.

        Args:
            level: Numeric logging level.
            msg: The log message.
            kwargs: Extra structured context.
        """
        if not self._logger.isEnabledFor(level):
            return
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            __file__,
            0,
            msg,
            (),
            None,
            None,
            extra=dict(kwargs),
        )
        self._logger.handle(record)

    def info(self, msg: str, **kwargs: Any) -> None:
        """Log at INFO level with structured context.

        Args:
            msg: The log message.
            kwargs: Extra structured context.
        """
        self._log(logging.INFO, msg, kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        """Log at ERROR level with structured context.

        Args:
            msg: The log message.
            kwargs: Extra structured context.
        """
        self._log(logging.ERROR, msg, kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        """Log at WARNING level with structured context.

        Args:
            msg: The log message.
            kwargs: Extra structured context.
        """
        self._log(logging.WARNING, msg, kwargs)

    def debug(self, msg: str, **kwargs: Any) -> None:
        """Log at DEBUG level with structured context.

        Args:
            msg: The log message.
            kwargs: Extra structured context.
        """
        self._log(logging.DEBUG, msg, kwargs)


def get_logger(name: str = "backup-agent") -> StructuredLogger:
    """Return a configured structured logger.

    Args:
        name: Logger name.

    Returns:
        A StructuredLogger that writes JSON lines to stdout.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return StructuredLogger(logger)
