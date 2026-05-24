"""Proposal value objects for the Evolution capability."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from shared.control_plane import EvolutionTier

EVOLUTION_PROPOSAL_RISK = (
    "Changes agent skill, architecture, or collaboration behavior."
)
EVOLUTION_ROLLOUT_NOTE = (
    "Reject the proposal or roll back the rollout state before promotion."
)


class EvolutionProposalOperation(StrEnum):
    """Whitelisted operations the Evolution capability may propose."""

    ADD_SKILL = "add_skill"
    ADJUST_SKILL_ORDERING = "adjust_skill_ordering"
    MODIFY_EVENT_SUBSCRIPTION = "modify_event_subscription"
    ADJUST_SAMPLING_PARAMETERS = "adjust_sampling_parameters"
    ADD_LOOP_LOGIC = "add_loop_logic"


ALLOWED_EVOLUTION_OPERATIONS = tuple(
    operation.value for operation in EvolutionProposalOperation
)


@dataclass(frozen=True, slots=True)
class EvolutionProposalScope:
    """Stable scope string used by the Control Plane proposal ledger."""

    tier: EvolutionTier
    value: str
    target_agent: str | None = None
    target_skill: str | None = None
    pattern_id: str | None = None

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        tier: EvolutionTier,
    ) -> "EvolutionProposalScope":
        if tier == EvolutionTier.L3:
            pattern_id = _required_text(
                payload.get("pattern_id") or payload.get("name"),
                fallback="unknown",
            )
            return cls(
                tier=tier,
                value=f"pattern:{pattern_id}",
                pattern_id=pattern_id,
            )

        target_agent = _required_text(
            payload.get("target_agent"),
            fallback="unknown-agent",
        )
        target_skill = _optional_text(payload.get("target_skill"))
        if target_skill:
            value = f"agent:{target_agent}/skill:{target_skill}"
        else:
            value = f"agent:{target_agent}"
        return cls(
            tier=tier,
            value=value,
            target_agent=target_agent,
            target_skill=target_skill,
        )


@dataclass(frozen=True, slots=True)
class EvolutionProposalApprovalContext:
    """Immutable approval and ledger context derived from a proposal payload."""

    payload: Mapping[str, Any]
    source_agent_id: str
    trace_id: str | None
    tier: EvolutionTier
    scope: EvolutionProposalScope

    @classmethod
    def from_payload(
        cls,
        proposal: Mapping[str, Any],
        *,
        source_agent_id: str,
        trace_id: str | None,
        tier: EvolutionTier | None = None,
    ) -> "EvolutionProposalApprovalContext":
        payload = MappingProxyType(dict(proposal))
        resolved_tier = tier or infer_evolution_proposal_tier(payload)
        return cls(
            payload=payload,
            source_agent_id=source_agent_id,
            trace_id=trace_id,
            tier=resolved_tier,
            scope=EvolutionProposalScope.from_payload(
                payload,
                tier=resolved_tier,
            ),
        )

    def mutable_payload(self) -> dict[str, Any]:
        """Return a primitive copy for event/API compatibility."""
        return dict(self.payload)

    @property
    def operation_or_pattern(self) -> str:
        return _required_text(
            self.payload.get("operation") or self.payload.get("pattern_id"),
            fallback="unknown",
        )

    @property
    def approval_action(self) -> str:
        return f"Approve evolution proposal {self.operation_or_pattern}"

    @property
    def approval_reason(self) -> str:
        return _required_text(
            self.payload.get("rationale") or self.payload.get("description"),
            fallback="Evolution proposal",
        )

    @property
    def affected_resources(self) -> list[str]:
        resource = (
            self.payload.get("target_agent")
            or self.payload.get("pattern_id")
            or self.source_agent_id
        )
        return [_required_text(resource, fallback=self.source_agent_id)]

    @property
    def expected_benefit(self) -> str:
        return _required_text(
            self.payload.get("expected_benefit")
            or self.payload.get("description")
            or self.payload.get("rationale"),
            fallback="Improve agent behavior.",
        )

    @property
    def risk(self) -> str:
        return _required_text(
            self.payload.get("risk"),
            fallback=EVOLUTION_PROPOSAL_RISK,
        )

    @property
    def evidence(self) -> dict[str, Any]:
        return {
            "source_agent": self.source_agent_id,
            "trace_id": self.trace_id,
            "proposal": self.mutable_payload(),
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "proposed_by": self.source_agent_id,
            "operation": self.payload.get("operation"),
            "target_agent": self.payload.get("target_agent"),
            "target_skill": self.payload.get("target_skill"),
            "pattern_id": self.payload.get("pattern_id"),
        }


def infer_evolution_proposal_tier(payload: Mapping[str, Any]) -> EvolutionTier:
    """Infer the Control Plane tier from the Evolution proposal vocabulary."""
    if "pattern_id" in payload:
        return EvolutionTier.L3
    operation = payload.get("operation")
    if operation in {
        EvolutionProposalOperation.MODIFY_EVENT_SUBSCRIPTION.value,
        EvolutionProposalOperation.ADD_LOOP_LOGIC.value,
    }:
        return EvolutionTier.L2
    return EvolutionTier.L1


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, *, fallback: str) -> str:
    return _optional_text(value) or fallback
