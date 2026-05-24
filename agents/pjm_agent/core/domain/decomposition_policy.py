"""Domain policies for decomposition workflow coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .lifecycle.decomposition_lifecycle import (
    APPROVED,
    FAILED,
    PENDING,
    REJECTED,
    WRITE_FAILED,
    WRITING,
    DecompositionStatus,
)

DecompositionIntakeAction = Literal["start", "skip", "replace"]

_EXISTING_BLOCKING_STATUSES: frozenset[str] = frozenset({PENDING, WRITING, APPROVED, WRITE_FAILED})
_RECOVERABLE_STATUSES: frozenset[str] = frozenset({FAILED, REJECTED, WRITE_FAILED})
_RECOVERABLE_STATUS_LABEL = "failed/rejected/write_failed"


@dataclass(frozen=True, slots=True)
class DecompositionIntakeDecision:
    """Decision for a new decomposition request against an existing record."""

    action: DecompositionIntakeAction
    existing_status: DecompositionStatus | str | None = None

    @property
    def should_skip(self) -> bool:
        return self.action == "skip"

    @property
    def should_replace_existing(self) -> bool:
        return self.action == "replace"


@dataclass(frozen=True, slots=True)
class DecompositionRetryDecision:
    """Decision for retrying a previously persisted decomposition."""

    allowed: bool
    error_message: str | None = None
    error_code: str | None = None
    status: DecompositionStatus | str | None = None


class DecompositionWorkflowPolicy:
    """Owns cross-record decomposition workflow rules.

    PJM keeps one meaningful decomposition per OpenProject work package. New
    intake skips active/write-in-progress records, replaces failed or rejected
    records, and retry is allowed only from terminal failure states.
    """

    def intake_decision(
        self,
        existing_status: DecompositionStatus | str | None,
    ) -> DecompositionIntakeDecision:
        if existing_status is None:
            return DecompositionIntakeDecision("start")
        if existing_status in _EXISTING_BLOCKING_STATUSES:
            return DecompositionIntakeDecision("skip", existing_status=existing_status)
        return DecompositionIntakeDecision("replace", existing_status=existing_status)

    def retry_decision(
        self,
        existing_status: DecompositionStatus | str | None,
    ) -> DecompositionRetryDecision:
        if existing_status is None:
            return DecompositionRetryDecision(
                allowed=False,
                error_message="record not found",
                error_code="pm.decomposition_not_found",
            )
        if existing_status not in _RECOVERABLE_STATUSES:
            return DecompositionRetryDecision(
                allowed=False,
                error_message=(
                    f"cannot retry status '{existing_status}', only {_RECOVERABLE_STATUS_LABEL}"
                ),
                error_code="pm.decomposition_retry_not_allowed",
                status=existing_status,
            )
        return DecompositionRetryDecision(allowed=True, status=existing_status)


__all__ = [
    "DecompositionIntakeDecision",
    "DecompositionRetryDecision",
    "DecompositionWorkflowPolicy",
]
