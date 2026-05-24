"""Acceptance verdict value object.

Stage 2 (domain modeling) per docs/architecture/migration-plan.md.
The QA flow does not have a state machine in the same sense as PJM
decomposition or dev tasks; an acceptance run produces one verdict
that is logically immutable. This module models the verdict as a
value object instead of an aggregate, so the canonical "did the gate
pass" question lives in one place.

Mirrors the pattern landed for PJM Decomposition (#137), Dev Task
(#138), and Requirement (#139), filling the QA slot in Stage 2
domain coverage.

Adoption is gradual. The current run-store record (`QAAcceptanceRunRecord`)
stores ``l0_status``, ``l1_status``, ``l2_status`` as plain strings;
this value object validates and exposes the gate-level outcome for
use cases that need a one-call answer ("did this run block the merge?").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .acceptance_vocabulary import (
    GATE_ERROR,
    GATE_PASS,
    GATE_VALUES,
    L1_ERROR,
    L1_PASS,
    L1_STATUS_VALUES,
    L2_INFO,
    L2_STATUS_VALUES,
    is_failing_gate,
)


class InvalidAcceptanceVerdictError(ValueError):
    """Raised when a verdict is constructed from unknown status values."""


@dataclass(frozen=True, slots=True)
class AcceptanceVerdict:
    """Three-layer outcome of one QA acceptance run.

    Fields:

    - ``l0_gate`` — gate outcome. One of ``GATE_VALUES``.
    - ``l1_status`` — L1 verdict. One of ``L1_STATUS_VALUES``.
    - ``l2_status`` — L2 report status. The acceptance framework currently
      emits ``INFO`` for the L2 report bucket.
    - ``l0_failure_count`` and ``l1_warning_count`` — counters used by
      operators to prioritise notification fan-out.
    """

    l0_gate: str
    l1_status: str
    l2_status: str
    l0_failure_count: int = 0
    l1_warning_count: int = 0

    def __post_init__(self) -> None:
        if self.l0_gate not in GATE_VALUES:
            raise InvalidAcceptanceVerdictError(
                f"unknown l0_gate {self.l0_gate!r}; expected one of {GATE_VALUES}"
            )
        if self.l1_status not in L1_STATUS_VALUES:
            raise InvalidAcceptanceVerdictError(
                f"unknown l1_status {self.l1_status!r}; expected one of {L1_STATUS_VALUES}"
            )
        if self.l2_status not in L2_STATUS_VALUES:
            raise InvalidAcceptanceVerdictError(
                f"unknown l2_status {self.l2_status!r}; expected one of {L2_STATUS_VALUES}"
            )
        if self.l0_failure_count < 0:
            raise InvalidAcceptanceVerdictError(
                "l0_failure_count must be >= 0"
            )
        if self.l1_warning_count < 0:
            raise InvalidAcceptanceVerdictError(
                "l1_warning_count must be >= 0"
            )

    @property
    def is_blocking(self) -> bool:
        """Return whether the verdict blocks the merge gate."""
        return is_failing_gate(self.l0_gate)

    @property
    def is_clean(self) -> bool:
        """Return whether the verdict passed L0 and L1 without warnings."""
        return (
            self.l0_gate == GATE_PASS
            and self.l1_status == L1_PASS
            and self.l2_status == L2_INFO
            and self.l0_failure_count == 0
            and self.l1_warning_count == 0
        )

    @classmethod
    def from_summary(cls, summary: Mapping[str, Any]) -> AcceptanceVerdict:
        """Build a verdict from the acceptance runner summary shape."""
        return cls(
            l0_gate=str(summary.get("l0_gate", GATE_ERROR)),
            l1_status=str(summary.get("l1_check", L1_ERROR)),
            l2_status=str(summary.get("l2_report", L2_INFO)),
            l0_failure_count=int(summary.get("l0_failures", 0) or 0),
            l1_warning_count=int(summary.get("l1_warnings", 0) or 0),
        )


__all__ = [
    "AcceptanceVerdict",
    "InvalidAcceptanceVerdictError",
]
