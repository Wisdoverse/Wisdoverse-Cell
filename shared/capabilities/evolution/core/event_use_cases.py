"""Application use cases for Evolution event dispatch."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from shared.control_plane import ApprovalRequiredError, EvolutionTier
from shared.evolution.collaboration.seeds import COLLABORATION_SEEDS
from shared.evolution.config import evolution_settings
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .request_use_cases import EvolutionAnalyzerPort

logger = get_logger("evolution_module.events")


class EvolutionApprovalServicePort(Protocol):
    """Control-plane approval operations needed by Evolution events."""

    async def approve_for_sensitive_action(
        self,
        approval_id: str | None,
        *,
        resolved_by: str,
    ) -> Any:
        """Approve one sensitive action."""

    async def reject_for_sensitive_action(
        self,
        approval_id: str | None,
        *,
        resolved_by: str,
    ) -> Any:
        """Reject one sensitive action."""


class EvolutionPatternApprovalGatewayPort(Protocol):
    """Collaboration-pattern approval side effect boundary."""

    async def process_approval(
        self,
        *,
        pattern_id: str,
        user_id: str,
        approved: bool,
    ) -> bool:
        """Apply one collaboration-pattern approval decision."""


class EvolutionEventFactoryPort(Protocol):
    """Event factory owned by the service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> Event:
        """Create an integration event with the module identity."""


class EvolutionProposalApprovalPort(Protocol):
    """Approval enrichment for proposed evolution payloads."""

    async def __call__(
        self,
        proposal: dict[str, Any],
        *,
        trace_id: str | None = None,
        tier: EvolutionTier | None = None,
    ) -> dict[str, Any]:
        """Attach approval metadata to a proposal payload."""


class EvolutionEventUseCase:
    """Dispatch and execute Evolution event workflows outside the service shell."""

    def __init__(
        self,
        *,
        analyzer: EvolutionAnalyzerPort,
        attach_proposal_approval: EvolutionProposalApprovalPort,
        event_factory: EvolutionEventFactoryPort,
        approval_service: EvolutionApprovalServicePort,
        approval_gateway: EvolutionPatternApprovalGatewayPort | None,
        collaboration_enabled: bool | None = None,
        collaboration_seeds: Sequence[Any] | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._attach_proposal_approval = attach_proposal_approval
        self._event_factory = event_factory
        self._approval_service = approval_service
        self._approval_gateway = approval_gateway
        self._collaboration_enabled = (
            evolution_settings.collaboration_enabled
            if collaboration_enabled is None
            else collaboration_enabled
        )
        self._collaboration_seeds = (
            COLLABORATION_SEEDS if collaboration_seeds is None else collaboration_seeds
        )

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.EVOLUTION_CYCLE_TRIGGERED:
            return await self._analyze_and_propose(event)
        if event.event_type == EventTypes.EVOLUTION_HUMAN_FEEDBACK:
            return await self._process_feedback(event)
        if event.event_type == EventTypes.EVOLUTION_PATTERN_APPROVED:
            return await self._process_pattern_approval(event)
        return []

    async def _analyze_and_propose(self, event: Event) -> list[Event]:
        trace_id = _trace_id(event)
        days = event.payload.get("days", 7)
        proposals = await self._analyzer.analyze(days)

        result_events: list[Event] = []
        for proposal in proposals:
            proposal = await self._attach_proposal_approval(
                proposal,
                trace_id=trace_id,
            )
            result_events.append(
                self._event_factory.create_event(
                    EventTypes.EVOLUTION_SKILL_PROPOSED,
                    payload=proposal,
                    trace_id=trace_id,
                )
            )

        if self._collaboration_enabled:
            pattern_events = await self._propose_collaboration_patterns(trace_id)
            result_events.extend(pattern_events)

        return result_events

    async def _propose_collaboration_patterns(self, trace_id: str | None) -> list[Event]:
        events: list[Event] = []
        for seed in self._collaboration_seeds:
            payload = {
                "pattern_id": seed.pattern_id,
                "name": seed.name,
                "trigger_event": seed.trigger_event,
                "steps": [step.model_dump() for step in seed.steps],
            }
            payload = await self._attach_proposal_approval(
                payload,
                trace_id=trace_id,
            )
            events.append(
                self._event_factory.create_event(
                    EventTypes.EVOLUTION_PATTERN_PROPOSED,
                    payload=payload,
                    trace_id=trace_id,
                )
            )
        return events

    async def _process_feedback(self, event: Event) -> list[Event]:
        logger.info(
            "human_feedback_received",
            event_id=event.event_id,
            trace_id=_trace_id(event),
            approved=bool(event.payload.get("approved", False)),
            payload_keys=sorted(event.payload.keys()),
        )
        approval_id = event.payload.get("control_plane_approval_id") or event.payload.get(
            "approval_id"
        )
        approved = bool(event.payload.get("approved", False))
        resolved_by = event.payload.get("user_id") or event.payload.get("resolved_by")
        if approval_id and not resolved_by:
            logger.warning(
                "evolution_feedback_resolver_required",
                approval_id=approval_id,
                event_id=event.event_id,
            )
            return []
        try:
            if approved:
                await self._approval_service.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
            else:
                await self._approval_service.reject_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
        except ApprovalRequiredError as exc:
            logger.warning(
                "evolution_feedback_control_plane_approval_required",
                approval_id=approval_id,
                error=str(exc),
            )
        return []

    async def _process_pattern_approval(self, event: Event) -> list[Event]:
        pattern_id = event.payload.get("pattern_id", "")
        user_id = event.payload.get("user_id", "")
        approved = event.payload.get("approved", False)
        approval_id = event.payload.get("control_plane_approval_id") or event.payload.get(
            "approval_id"
        )
        resolved_by = user_id

        if approval_id and not resolved_by:
            logger.warning(
                "pattern_control_plane_resolver_required",
                pattern_id=pattern_id,
                approval_id=approval_id,
                event_id=event.event_id,
            )
            return []

        try:
            if approved:
                await self._approval_service.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
            else:
                await self._approval_service.reject_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
        except ApprovalRequiredError as exc:
            logger.warning(
                "pattern_control_plane_approval_required",
                pattern_id=pattern_id,
                approval_id=approval_id,
                error=str(exc),
            )
            return []

        if not self._approval_gateway:
            logger.warning("no_approval_gateway", pattern_id=pattern_id)
            return []

        success = await self._approval_gateway.process_approval(
            pattern_id=pattern_id,
            user_id=resolved_by or "",
            approved=approved,
        )

        if success:
            logger.info(
                "pattern_approval_processed",
                pattern_id=pattern_id,
                approved=approved,
            )

        return []


def _trace_id(event: Event) -> str | None:
    return event.metadata.trace_id if event.metadata else None
