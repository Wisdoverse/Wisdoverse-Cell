"""Domain service for approval resolution side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ApprovalStatus, EvolutionRolloutState
from .services import ControlPlaneDomainService


@dataclass(frozen=True, slots=True)
class ApprovalResolutionEffect:
    """Domain effect produced when an approval is resolved."""

    approval_status: ApprovalStatus
    proposal_approval_state: ApprovalStatus
    proposal_rollout_state: EvolutionRolloutState | None = None

    @property
    def approved(self) -> bool:
        """True when the resolution grants permission."""
        return self.approval_status == ApprovalStatus.APPROVED

    def proposal_update_kwargs(self) -> dict[str, str | None]:
        """Return persistence-ready proposal approval synchronization fields."""
        return {
            "approval_state": self.proposal_approval_state.value,
            "rollout_state": (
                self.proposal_rollout_state.value
                if self.proposal_rollout_state is not None
                else None
            ),
        }

    def proposal_audit_detail(
        self,
        *,
        proposal_id: str,
        approval_id: str,
    ) -> dict[str, Any]:
        """Return audit detail for a proposal updated by this approval effect."""
        detail: dict[str, Any] = {
            "proposal_id": proposal_id,
            "approval_state": self.proposal_approval_state.value,
            "approval_id": approval_id,
        }
        if self.proposal_rollout_state is not None:
            detail["rollout_state"] = self.proposal_rollout_state.value
        return detail


class ApprovalResolutionPolicy(ControlPlaneDomainService):
    """Domain service for approval resolution effects across aggregates."""

    __slots__ = ()

    def resolve(self, *, approved: bool) -> ApprovalResolutionEffect:
        """Return the approval/proposal effect for a human decision."""
        if approved:
            return ApprovalResolutionEffect(
                approval_status=ApprovalStatus.APPROVED,
                proposal_approval_state=ApprovalStatus.APPROVED,
            )
        return ApprovalResolutionEffect(
            approval_status=ApprovalStatus.REJECTED,
            proposal_approval_state=ApprovalStatus.REJECTED,
            proposal_rollout_state=EvolutionRolloutState.REJECTED,
        )


__all__ = [
    "ApprovalResolutionEffect",
    "ApprovalResolutionPolicy",
]
