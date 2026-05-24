"""Domain policy for Coordinator dispatch decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from shared.schemas.coordinator import CoordinatorResponse
from shared.schemas.event import EventTypes


class CoordinatorDispatchTarget(StrEnum):
    """Known downstream runtime targets for Coordinator decisions."""

    REQUIREMENT_MANAGER = "requirement-manager"
    PJM_AGENT = "pjm-agent"
    DEV_AGENT = "dev-agent"
    QA_AGENT = "qa-agent"
    CHAT_AGENT = "chat-agent"


class CoordinatorTargetRelationship(StrEnum):
    """Context-map relationship for a dispatch target."""

    CUSTOMER_SUPPLIER = "customer_supplier"
    OPEN_HOST_SERVICE = "open_host_service"


@dataclass(frozen=True, slots=True)
class CoordinatorDispatchRoute:
    """Value object describing how a Coordinator target is routed."""

    target_agent: str
    relationship: CoordinatorTargetRelationship
    target: CoordinatorDispatchTarget | None = None

    @classmethod
    def from_target_agent(cls, target_agent: str) -> "CoordinatorDispatchRoute":
        """Classify a target agent without losing unknown-agent passthrough."""
        try:
            known_target = CoordinatorDispatchTarget(target_agent)
        except ValueError:
            return cls(
                target_agent=target_agent,
                relationship=CoordinatorTargetRelationship.OPEN_HOST_SERVICE,
                target=None,
            )
        return cls(
            target_agent=known_target.value,
            relationship=CoordinatorTargetRelationship.CUSTOMER_SUPPLIER,
            target=known_target,
        )

    @property
    def uses_specialized_contract(self) -> bool:
        """Return whether this route maps to a target-specific event contract."""
        return self.target in {
            CoordinatorDispatchTarget.DEV_AGENT,
            CoordinatorDispatchTarget.QA_AGENT,
            CoordinatorDispatchTarget.CHAT_AGENT,
        }


class CoordinatorDecisionLike(Protocol):
    """Decision fields consumed by the dispatch policy."""

    target_agent: str
    action: str
    task_id: str
    instruction: str
    workflow_id: str | None
    context: Mapping[str, Any]
    command_id: str | None
    status: str | None
    summary: str | None
    scratchpad_ref: str | None


@dataclass(frozen=True, slots=True)
class CoordinatorDispatchEnvelope:
    """Primitive EventBus envelope produced from a Coordinator decision."""

    event_type: str
    payload: Mapping[str, Any]
    route: CoordinatorDispatchRoute


class CoordinatorDispatchPolicy:
    """Domain service that maps Coordinator decisions to outbound contracts."""

    def envelope_for(
        self,
        decision: CoordinatorDecisionLike,
    ) -> CoordinatorDispatchEnvelope:
        """Create an EventBus envelope without publishing it."""
        route = CoordinatorDispatchRoute.from_target_agent(decision.target_agent)

        if route.target == CoordinatorDispatchTarget.DEV_AGENT:
            return CoordinatorDispatchEnvelope(
                event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
                payload={
                    "wp_id": decision.context.get("wp_id"),
                    "tasks": decision.context.get("tasks", []),
                    "instruction": decision.instruction,
                    "workflow_id": decision.workflow_id,
                },
                route=route,
            )

        if route.target == CoordinatorDispatchTarget.QA_AGENT:
            return CoordinatorDispatchEnvelope(
                event_type=EventTypes.QA_RUN_REQUESTED,
                payload={
                    "agent_name": decision.context.get("agent_name"),
                    "commit_sha": decision.context.get("commit_sha"),
                    "mr_iid": decision.context.get("mr_iid"),
                    "gitlab_project_id": decision.context.get("gitlab_project_id"),
                    "files_changed": decision.context.get("files_changed", []),
                    "requested_by": "coordinator",
                    "instruction": decision.instruction,
                    "workflow_id": decision.workflow_id,
                },
                route=route,
            )

        if route.target == CoordinatorDispatchTarget.CHAT_AGENT:
            return CoordinatorDispatchEnvelope(
                event_type=EventTypes.COORDINATOR_RESPONSE,
                payload=CoordinatorResponse(
                    command_id=decision.command_id or "",
                    status=decision.status or "completed",
                    summary=decision.summary or "",
                ).model_dump(),
                route=route,
            )

        return CoordinatorDispatchEnvelope(
            event_type=EventTypes.COORDINATOR_DISPATCH,
            payload={
                "target_agent": route.target_agent,
                "task_id": decision.task_id,
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
                "scratchpad_ref": decision.scratchpad_ref,
            },
            route=route,
        )


__all__ = [
    "CoordinatorDecisionLike",
    "CoordinatorDispatchEnvelope",
    "CoordinatorDispatchPolicy",
    "CoordinatorDispatchRoute",
    "CoordinatorDispatchTarget",
    "CoordinatorTargetRelationship",
]
