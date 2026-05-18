"""Deprecated location for requirement lifecycle policy.

The lifecycle policy moved to
``agents.requirement_manager.core.domain.lifecycle.requirement_lifecycle``
as part of Migration Plan §Stage 1 item 2. New imports should use the new
path. This shim preserves backward compatibility until callers migrate.
"""

from agents.requirement_manager.core.domain.lifecycle.requirement_lifecycle import (
    CHANGED,
    CONFIRMED,
    PENDING,
    REJECTED,
    MutableRequirement,
    mark_confirmed,
    mark_rejected,
    record_updated,
)

__all__ = [
    "CHANGED",
    "CONFIRMED",
    "MutableRequirement",
    "PENDING",
    "REJECTED",
    "mark_confirmed",
    "mark_rejected",
    "record_updated",
]
