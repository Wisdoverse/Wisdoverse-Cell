"""
Logger - centralized logging configuration.

Uses structlog for structured logs that are easier to analyze.
"""
import logging
import sys
from typing import Optional

import structlog

from shared.observability.privacy import redact_for_observability


def redact_log_event(logger, method_name: str, event_dict: dict) -> dict:
    """Structlog processor that redacts secrets and direct PII before rendering."""
    return redact_for_observability(event_dict)


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    Return a configured logger instance.

    Args:
        name: Logger name, usually a module name or agent ID.

    Returns:
        Configured structlog logger.
    """
    return structlog.get_logger(name)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None
):
    """
    Configure global logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        json_format: Whether to output JSON-formatted logs.
        log_file: Optional log file path.
    """
    # Set standard-library logging level.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    # Minimal processor list.
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        redact_log_event,
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(
                exception_formatter=structlog.dev.plain_traceback,
            )
        )

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Default configuration
setup_logging()
