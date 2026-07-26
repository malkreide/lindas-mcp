"""Structured logging for lindas-mcp (OBS-003).

Logs are JSON, carry RFC 5424-style severity levels, and go to **stderr** only
— stdout is reserved for the JSON-RPC protocol stream on the stdio transport
(OBS-004). `configure_logging()` is idempotent and is also called at import so
that a stray log before `main()` can never land on stdout.
"""

from __future__ import annotations

import logging
import sys

import structlog

_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON to stderr at ``level``. Idempotent."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        # stderr, never stdout — the stdio transport owns stdout.
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(
            _LEVELS.get(level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


# Configure eagerly so importing `logger` is always safe (stderr-bound).
configure_logging()

logger = structlog.get_logger("lindas_mcp")
