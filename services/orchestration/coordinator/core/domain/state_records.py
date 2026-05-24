"""Domain records for Coordinator persisted runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, NewType

CoordinatorAgentId = NewType("CoordinatorAgentId", str)
CoordinatorDecisionId = NewType("CoordinatorDecisionId", str)
CoordinatorTaskId = NewType("CoordinatorTaskId", str)
CoordinatorWorkflowId = NewType("CoordinatorWorkflowId", str)


class CoordinatorAgentStatus(StrEnum):
    """Allowed Coordinator runtime view of an agent."""

    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    ERROR = "error"


def coordinator_agent_id(raw: object) -> CoordinatorAgentId:
    value = str(raw).strip()
    if not value:
        raise ValueError("coordinator agent id must not be empty")
    return CoordinatorAgentId(value)


def coordinator_decision_id(raw: object) -> CoordinatorDecisionId:
    value = str(raw).strip()
    if not value:
        raise ValueError("coordinator decision id must not be empty")
    return CoordinatorDecisionId(value)


def coordinator_task_id(raw: object | None) -> CoordinatorTaskId | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return CoordinatorTaskId(value)


def coordinator_workflow_id(raw: object | None) -> CoordinatorWorkflowId | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return CoordinatorWorkflowId(value)


@dataclass(frozen=True, slots=True)
class CoordinatorAgentStateRecord:
    """Coordinator-owned snapshot of one runtime agent state."""

    agent_id: CoordinatorAgentId
    status: CoordinatorAgentStatus
    current_task: CoordinatorTaskId | None = None
    last_output_at: datetime | None = None
    error: str | None = None

    @classmethod
    def create(
        cls,
        *,
        agent_id: object,
        status: object = CoordinatorAgentStatus.IDLE,
        current_task: object | None = None,
        last_output_at: datetime | None = None,
        error: str | None = None,
    ) -> "CoordinatorAgentStateRecord":
        return cls(
            agent_id=coordinator_agent_id(agent_id),
            status=CoordinatorAgentStatus(str(status)),
            current_task=coordinator_task_id(current_task),
            last_output_at=last_output_at,
            error=error,
        )

    @classmethod
    def from_record(cls, row: Any) -> "CoordinatorAgentStateRecord":
        """Hydrate a domain record from a persistence row or DTO."""
        return cls.create(
            agent_id=row.agent_id,
            status=row.status,
            current_task=getattr(row, "current_task", None),
            last_output_at=getattr(row, "last_output_at", None),
            error=getattr(row, "error", None),
        )

    def to_record_kwargs(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "status": self.status.value,
            "current_task": str(self.current_task) if self.current_task else None,
            "last_output_at": self.last_output_at,
            "error": self.error,
        }

    def model_dump(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Return a Pydantic-compatible primitive representation."""
        return self.to_record_kwargs()


@dataclass(frozen=True, slots=True)
class CoordinatorDecisionRecord:
    """Coordinator-owned snapshot of one pending decision."""

    decision_id: CoordinatorDecisionId
    reasoning: str
    action: str
    target_agent: CoordinatorAgentId
    workflow_id: CoordinatorWorkflowId | None = None
    created_at: datetime | None = None
    outcome: str | None = None
    task_id: CoordinatorTaskId | None = None

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("coordinator decision action must not be empty")

    @classmethod
    def create(
        cls,
        *,
        decision_id: object,
        reasoning: str,
        action: str,
        target_agent: object,
        workflow_id: object | None = None,
        created_at: datetime | None = None,
        outcome: str | None = None,
        task_id: object | None = None,
    ) -> "CoordinatorDecisionRecord":
        return cls(
            decision_id=coordinator_decision_id(decision_id),
            workflow_id=coordinator_workflow_id(workflow_id),
            reasoning=reasoning,
            action=action,
            target_agent=coordinator_agent_id(target_agent),
            created_at=created_at,
            outcome=outcome,
            task_id=coordinator_task_id(task_id),
        )

    @classmethod
    def from_record(cls, row: Any) -> "CoordinatorDecisionRecord":
        """Hydrate a domain record from a persistence row or DTO."""
        return cls.create(
            decision_id=row.decision_id,
            workflow_id=getattr(row, "workflow_id", None),
            reasoning=getattr(row, "reasoning", "") or "",
            action=row.action,
            target_agent=row.target_agent,
            created_at=getattr(row, "created_at", None),
            outcome=getattr(row, "outcome", None),
            task_id=getattr(row, "task_id", None),
        )

    def to_record_kwargs(self) -> dict[str, Any]:
        return {
            "decision_id": str(self.decision_id),
            "workflow_id": str(self.workflow_id) if self.workflow_id else None,
            "reasoning": self.reasoning,
            "action": self.action,
            "target_agent": str(self.target_agent),
            "created_at": self.created_at,
            "outcome": self.outcome,
        }

    def model_dump(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        """Return a Pydantic-compatible primitive representation."""
        payload = self.to_record_kwargs()
        payload["task_id"] = str(self.task_id) if self.task_id else None
        return payload


__all__ = [
    "CoordinatorAgentId",
    "CoordinatorAgentStateRecord",
    "CoordinatorAgentStatus",
    "CoordinatorDecisionId",
    "CoordinatorDecisionRecord",
    "CoordinatorTaskId",
    "CoordinatorWorkflowId",
    "coordinator_agent_id",
    "coordinator_decision_id",
    "coordinator_task_id",
    "coordinator_workflow_id",
]
