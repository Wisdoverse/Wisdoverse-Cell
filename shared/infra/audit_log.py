"""Structured audit logging for agent operations.

Writes to a dedicated 'audit' logger with immutable structured fields.
Can be routed to a SIEM, file, or database via logging configuration.
"""

from enum import Enum
from typing import Any

from shared.utils.logger import get_logger

logger = get_logger("audit")


class AuditAction(str, Enum):
    """Audit action types for agent operations."""

    LLM_CALL = "llm_call"
    EVENT_HANDLED = "event_handled"
    EVENT_FAILED = "event_failed"
    REQUEST_HANDLED = "request_handled"
    REQUEST_FAILED = "request_failed"
    TOOL_EXECUTED = "tool_executed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    SKILL_PROMOTED = "skill_promoted"
    SKILL_ROLLED_BACK = "skill_rolled_back"
    RATE_LIMITED = "rate_limited"
    INJECTION_BLOCKED = "injection_blocked"
    COST_CAP_EXCEEDED = "cost_cap_exceeded"


def audit_log(
    *,
    action: AuditAction,
    agent_id: str,
    detail: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Emit a structured audit log entry."""
    logger.info(
        "audit",
        action=action.value,
        agent_id=agent_id,
        trace_id=trace_id or "",
        **(detail or {}),
    )
