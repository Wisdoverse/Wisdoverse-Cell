"""Dev delivery workflow domain policy."""

from __future__ import annotations

from dataclasses import dataclass

from .task_values import RiskLevel


@dataclass(frozen=True, slots=True)
class WorkflowCapacityDecision:
    """Decision for whether a task can start workflow execution now."""

    can_start: bool
    active_count: int
    limit: int


@dataclass(frozen=True, slots=True)
class QaRetryDecision:
    """Decision for whether a failed QA result should trigger one retry."""

    should_retry: bool
    retry_count: int
    max_retries: int

    @property
    def next_retry_count(self) -> int:
        """Return the retry count to persist if a retry is allowed."""
        return self.retry_count + 1


class DevDeliveryWorkflowPolicy:
    """Domain policy for Dev task delivery decisions.

    Workflow validation and security scanning remain operational tools. This
    policy owns the business decisions around risk gating, concurrency, and
    retry semantics so application use cases do not duplicate raw constants.
    """

    def rejects_automatic_delivery(self, risk: RiskLevel) -> bool:
        """Return whether a task must be implemented by a human."""
        return risk == RiskLevel.CRITICAL

    def requires_workflow_approval(self, risk: RiskLevel) -> bool:
        """Return whether a planned workflow must wait for HITL approval."""
        return risk == RiskLevel.HIGH

    def capacity_decision(
        self,
        *,
        active_count: int,
        max_concurrent_workflows: int,
    ) -> WorkflowCapacityDecision:
        """Return whether the task can start under the workflow limit."""
        return WorkflowCapacityDecision(
            can_start=active_count < max_concurrent_workflows,
            active_count=active_count,
            limit=max_concurrent_workflows,
        )

    def qa_retry_decision(
        self,
        *,
        retry_count: int,
        max_retries: int = 1,
    ) -> QaRetryDecision:
        """Return whether QA failure should re-enter planning."""
        return QaRetryDecision(
            should_retry=retry_count < max_retries,
            retry_count=retry_count,
            max_retries=max_retries,
        )


__all__ = [
    "DevDeliveryWorkflowPolicy",
    "QaRetryDecision",
    "WorkflowCapacityDecision",
]
