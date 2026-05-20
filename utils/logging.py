"""Structured logging for the paper collector.

Uses structlog for machine-parseable JSON logs and rich console output
when not running in CI/GitHub Actions.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import structlog


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
) -> structlog.stdlib.BoundLogger:
    """Set up structlog with sensible defaults for the paper collector.

    Call once at application startup.
    """
    _auto_detect_json = os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")
    use_json = json_format or bool(_auto_detect_json)

    structlog.reset_defaults()

    # Shared processors
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if use_json:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
    )

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "chardet"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = structlog.get_logger()
    logger.info("logging_configured", level=level, json=use_json)
    return logger


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger."""
    return structlog.get_logger(name or __name__)
