"""Deprecated location for dev task lifecycle policy.

The lifecycle policy moved to
``agents.dev_agent.core.domain.lifecycle.task_lifecycle`` as part of
Migration Plan §Stage 1 item 2. New imports should use the new path.
This shim preserves backward compatibility until callers migrate.
"""

from agents.dev_agent.core.domain.lifecycle.task_lifecycle import (
    ACTIVE_STATUSES,
    IN_PROGRESS_STATUSES,
    VALID_TRANSITIONS,
    can_transition,
)

__all__ = [
    "ACTIVE_STATUSES",
    "IN_PROGRESS_STATUSES",
    "VALID_TRANSITIONS",
    "can_transition",
]
