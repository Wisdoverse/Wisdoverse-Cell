"""Application use cases for Evolution proposal approval records."""
from __future__ import annotations

from typing import Any, Protocol

from shared.control_plane import ApprovalCategory, ApprovalStatus, EvolutionTier
from shared.utils.logger import get_logger

from .control_plane_ports import EvolutionControlPlaneProposalStore

logger = get_logger("evolution_module.proposal_approval")


class EvolutionApprovalRequestPort(Protocol):
    """Control-plane approval boundary for Evolution proposals."""

    enforced: bool

    async def request_approval(
        self,
        *,
        category: ApprovalCategory,
        proposed_action: str,
        reason: str,
        risk: str,
        rollback_note: str,
        affected_resources: list[str],
        trace_id: str | None,
    ) -> Any:
        """Request approval for one proposed Evolution change."""


class EvolutionProposalApprovalUseCase:
    """Attach approval metadata and durable control-plane records to proposals."""

    def __init__(
        self,
        *,
        approval_service: EvolutionApprovalRequestPort,
        proposal_store: EvolutionControlPlaneProposalStore | None,
        source_agent_id: str,
        company_id: str,
        records_enabled: bool,
    ) -> None:
        self._approval_service = approval_service
        self._proposal_store = proposal_store
        self._source_agent_id = source_agent_id
        self._company_id = company_id
        self._records_enabled = records_enabled

    async def attach_approval(
        self,
        proposal: dict[str, Any],
        *,
        trace_id: str | None = None,
        tier: EvolutionTier | None = None,
    ) -> dict[str, Any]:
        payload = dict(proposal)
        await self.ensure_company()
        try:
            approval = await self._approval_service.request_approval(
                category=ApprovalCategory.TECHNICAL,
                proposed_action=(
                    "Approve evolution proposal "
                    f"{payload.get('operation') or payload.get('pattern_id') or 'unknown'}"
                ),
                reason=(
                    payload.get("rationale")
                    or payload.get("description")
                    or "Evolution proposal"
                ),
                risk=(
                    "Changes agent skill, architecture, or collaboration behavior."
                ),
                rollback_note=(
                    "Reject the proposal or roll back the rollout state before promotion."
                ),
                affected_resources=[
                    str(
                        payload.get("target_agent")
                        or payload.get("pattern_id")
                        or self._source_agent_id
                    )
                ],
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error(
                "evolution_approval_request_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._approval_service.enforced:
                raise
            return payload

        if approval is not None:
            payload["control_plane_approval_id"] = approval.approval_id
        return await self.record_control_plane_proposal(
            payload,
            approval=approval,
            trace_id=trace_id,
            tier=tier or self.infer_proposal_tier(payload),
        )

    async def ensure_company(self) -> None:
        if not self._records_enabled:
            return
        try:
            await self._require_proposal_store().ensure_company(self._company_id)
        except Exception as exc:
            logger.error(
                "control_plane_company_ensure_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._approval_service.enforced:
                raise

    async def record_control_plane_proposal(
        self,
        payload: dict[str, Any],
        *,
        approval: Any,
        trace_id: str | None,
        tier: EvolutionTier,
    ) -> dict[str, Any]:
        if not self._records_enabled:
            return payload

        approval_id = getattr(approval, "approval_id", None) or payload.get(
            "control_plane_approval_id"
        )
        approval_state = getattr(approval, "status", None) or ApprovalStatus.PENDING.value
        evidence = {
            "source_agent": self._source_agent_id,
            "trace_id": trace_id,
            "proposal": payload,
        }
        expected_benefit = (
            payload.get("expected_benefit")
            or payload.get("description")
            or payload.get("rationale")
            or "Improve agent behavior."
        )
        risk = (
            payload.get("risk")
            or "Changes agent skill, architecture, or collaboration behavior."
        )
        metadata = {
            "proposed_by": self._source_agent_id,
            "operation": payload.get("operation"),
            "target_agent": payload.get("target_agent"),
            "target_skill": payload.get("target_skill"),
            "pattern_id": payload.get("pattern_id"),
        }

        try:
            proposal_id = await self._require_proposal_store().record_proposal(
                company_id=self._company_id,
                tier=tier,
                scope=self.proposal_scope(payload, tier),
                evidence=evidence,
                expected_benefit=expected_benefit,
                risk=risk,
                approval_state=approval_state,
                approval_id=approval_id,
                metadata=metadata,
                actor_id=self._source_agent_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error(
                "control_plane_evolution_proposal_record_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._approval_service.enforced:
                raise
            return payload

        payload["control_plane_proposal_id"] = proposal_id
        return payload

    def _require_proposal_store(self) -> EvolutionControlPlaneProposalStore:
        if self._proposal_store is None:
            raise RuntimeError("evolution_proposal_store_required")
        return self._proposal_store

    @staticmethod
    def infer_proposal_tier(payload: dict[str, Any]) -> EvolutionTier:
        if "pattern_id" in payload:
            return EvolutionTier.L3
        operation = payload.get("operation")
        if operation in {"modify_event_subscription", "add_loop_logic"}:
            return EvolutionTier.L2
        return EvolutionTier.L1

    @staticmethod
    def proposal_scope(payload: dict[str, Any], tier: EvolutionTier) -> str:
        if tier == EvolutionTier.L3:
            return (
                "pattern:"
                f"{payload.get('pattern_id') or payload.get('name') or 'unknown'}"
            )
        target_agent = payload.get("target_agent") or "unknown-agent"
        target_skill = payload.get("target_skill")
        if target_skill:
            return f"agent:{target_agent}/skill:{target_skill}"
        return f"agent:{target_agent}"
