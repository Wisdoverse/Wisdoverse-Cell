"""Structured logging helper for application use cases.

Defines `log_use_case(...)`, an async context manager that emits a
`use_case.started` event on entry, a `use_case.completed` event on success,
and a `use_case.failed` event on exception. Business identifiers
(`work_item_id`, `run_id`, `approval_id`, ...) are bound to the structlog
context for the duration of the block so every log line emitted inside the
use case carries the same correlation fields.

Usage:

    from shared.observability.use_case_logger import log_use_case

    async with log_use_case(
        "qa.acceptance_execute",
        agent_id="qa-agent",
        run_id=run.id,
        work_item_id=work_item.id,
    ):
        await execute(...)

This helper does not change behavior. Adoption is gradual.

Companion contract: docs/architecture/observability-guidelines.md §2 item 3.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, AsyncIterator

import structlog

from shared.utils.logger import get_logger

_BUSINESS_ID_FIELDS = (
    "agent_id",
    "company_id",
    "run_id",
    "work_item_id",
    "goal_id",
    "approval_id",
    "artifact_id",
    "request_id",
    "trace_id",
)


@contextlib.asynccontextmanager
async def log_use_case(
    name: str,
    **bindings: Any,
) -> AsyncIterator[structlog.BoundLogger]:
    """Bind business IDs and emit start / complete / fail events.

    Args:
        name: Stable use-case identifier in `<domain>.<verb>` form
            (e.g., ``qa.acceptance_execute``).
        **bindings: Business identifiers to bind to the structlog context.
            Keys that match the recognized business-ID set are bound
            verbatim; any other keys are bound under a ``ctx`` prefix to
            avoid accidental collisions with framework-reserved names.

    Yields:
        A structlog ``BoundLogger`` whose context already contains the use
        case name and the bound identifiers.
    """
    recognized = {k: v for k, v in bindings.items() if k in _BUSINESS_ID_FIELDS}
    extra = {
        f"ctx.{k}": v for k, v in bindings.items() if k not in _BUSINESS_ID_FIELDS
    }

    logger = get_logger("use_case").bind(use_case=name, **recognized, **extra)
    started_at = time.monotonic()
    structlog.contextvars.bind_contextvars(use_case=name, **recognized)
    try:
        logger.info("use_case.started")
        yield logger
    except BaseException as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.error(
            "use_case.failed",
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
        )
        raise
    else:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.info("use_case.completed", duration_ms=duration_ms)
    finally:
        structlog.contextvars.unbind_contextvars(
            "use_case",
            *recognized.keys(),
        )


__all__ = ["log_use_case"]
