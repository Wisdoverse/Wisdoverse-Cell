"""
EvolutionAgent — Analyzes global trace data and proposes architecture-level optimizations.

CRITICAL: This agent must NOT be wrapped with EvolvedAgent (no self-evolution).
Phase 2 operates in suggestion mode only — proposals require human approval.
Phase 3 adds collaboration pattern proposal and approval handling.
"""

from shared.config import settings
from shared.control_plane import (
    ApprovalCategory,
    ApprovalGateService,
    ApprovalRequiredError,
)
from shared.evolution.collaboration.seeds import COLLABORATION_SEEDS
from shared.evolution.config import evolution_settings
from shared.evolution.db.database import EvolutionDatabaseManager
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.llm_gateway import LLMGateway, llm_gateway
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from .global_analyzer import GlobalAnalyzer

logger = get_logger("evolution_agent.service")


class EvolutionAgent(BaseAgent):
    """Evolution engine that analyzes all agents and proposes improvements."""

    def __init__(
        self,
        db: EvolutionDatabaseManager | None = None,
        bus: EventBus | None = None,
        llm: LLMGateway | None = None,
    ):
        super().__init__(
            agent_id="evolution-agent",
            agent_name="Evolution Capability",
            subscribed_events=[
                EventTypes.EVOLUTION_CYCLE_TRIGGERED,
                EventTypes.EVOLUTION_HUMAN_FEEDBACK,
                EventTypes.EVOLUTION_PATTERN_APPROVED,
            ],
            published_events=[
                EventTypes.EVOLUTION_SKILL_PROPOSED,
                EventTypes.EVOLUTION_PATTERN_PROPOSED,
            ],
        )
        self._db_manager = db or EvolutionDatabaseManager()
        self._event_bus = bus or event_bus
        self._llm = llm or llm_gateway
        self._analyzer = GlobalAnalyzer(self._llm)
        self._approval_gateway = None
        self._control_plane_approvals = ApprovalGateService(source_agent_id=self.agent_id)

    async def startup(self) -> None:
        logger.info("agent_starting", agent_id=self.agent_id)

        if settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("evolution_tables_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        # Bootstrap skill seeds (idempotent)
        await self._bootstrap_seeds()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self) -> None:
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def _bootstrap_seeds(self) -> None:
        """Load skill seed configs into DB if not already present."""
        try:
            from shared.evolution.db.repository import EvolutionRepository
            from shared.evolution.seeds.chat_agent import CHAT_AGENT_SEEDS
            from shared.evolution.seeds.pjm_agent import PM_AGENT_SEEDS
            from shared.evolution.seeds.requirement_manager import (
                REQUIREMENT_MANAGER_SEEDS,
            )

            all_seeds = [
                *PM_AGENT_SEEDS,
                *CHAT_AGENT_SEEDS,
                *REQUIREMENT_MANAGER_SEEDS,
            ]
            if not all_seeds:
                return

            async with self._db_manager.session() as session:
                repo = EvolutionRepository(session)
                seeded = 0
                for seed in all_seeds:
                    existing = await repo.get_active_skill(seed.skill_id)
                    if existing is None:
                        await repo.save_skill_config(
                            skill_id=seed.skill_id,
                            version=seed.version,
                            status=seed.status,
                            system_prompt=seed.system_prompt,
                            parameters=seed.parameters,
                            few_shot_examples=seed.few_shot_examples,
                            output_format=seed.output_format or "",
                            target_model=seed.target_model or "",
                        )
                        seeded += 1
            if seeded:
                logger.info("skill_seeds_bootstrapped", count=seeded)
        except Exception as e:
            logger.warning(
                "skill_seed_bootstrap_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

    def set_approval_gateway(self, gateway) -> None:
        """Inject ApprovalGateway for processing pattern approvals."""
        self._approval_gateway = gateway

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.EVOLUTION_CYCLE_TRIGGERED:
            return await self._analyze_and_propose(event)
        elif event.event_type == EventTypes.EVOLUTION_HUMAN_FEEDBACK:
            return await self._process_feedback(event)
        elif event.event_type == EventTypes.EVOLUTION_PATTERN_APPROVED:
            return await self._process_pattern_approval(event)
        return []

    async def _analyze_and_propose(self, event: Event) -> list[Event]:
        """Analyze global traces and propose optimizations."""
        days = event.payload.get("days", 7)
        proposals = await self._analyzer.analyze(self._db_manager, days)

        result_events = []
        for proposal in proposals:
            proposal = await self._attach_proposal_approval(
                proposal,
                trace_id=event.metadata.trace_id,
            )
            result_events.append(
                self.create_event(
                    EventTypes.EVOLUTION_SKILL_PROPOSED,
                    payload=proposal,
                    trace_id=event.metadata.trace_id,
                )
            )

        # Phase 3: propose collaboration patterns when collaboration is enabled
        if evolution_settings.collaboration_enabled:
            pattern_events = await self._propose_collaboration_patterns(event)
            result_events.extend(pattern_events)

        return result_events

    async def _propose_collaboration_patterns(self, event: Event) -> list[Event]:
        """Emit pattern-proposed events for seed patterns."""
        events = []
        for seed in COLLABORATION_SEEDS:
            payload = {
                "pattern_id": seed.pattern_id,
                "name": seed.name,
                "trigger_event": seed.trigger_event,
                "steps": [s.model_dump() for s in seed.steps],
            }
            payload = await self._attach_proposal_approval(
                payload,
                trace_id=event.metadata.trace_id,
            )
            events.append(
                self.create_event(
                    EventTypes.EVOLUTION_PATTERN_PROPOSED,
                    payload=payload,
                    trace_id=event.metadata.trace_id,
                )
            )
        return events

    async def _process_feedback(self, event: Event) -> list[Event]:
        """Process human approval/rejection of proposals."""
        logger.info(
            "human_feedback_received",
            event_id=event.event_id,
            trace_id=event.metadata.trace_id,
            approved=bool(event.payload.get("approved", False)),
            payload_keys=sorted(event.payload.keys()),
        )
        approval_id = event.payload.get("control_plane_approval_id") or event.payload.get(
            "approval_id"
        )
        approved = bool(event.payload.get("approved", False))
        resolved_by = event.payload.get("user_id") or event.payload.get("resolved_by") or "api"
        try:
            if approved:
                await self._control_plane_approvals.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by,
                )
            else:
                await self._control_plane_approvals.reject_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by,
                )
        except ApprovalRequiredError as exc:
            logger.warning(
                "evolution_feedback_control_plane_approval_required",
                approval_id=approval_id,
                error=str(exc),
            )
        return []

    async def _process_pattern_approval(self, event: Event) -> list[Event]:
        """Process approval of a collaboration pattern via ApprovalGateway."""
        pattern_id = event.payload.get("pattern_id", "")
        user_id = event.payload.get("user_id", "")
        approved = event.payload.get("approved", False)
        approval_id = event.payload.get("control_plane_approval_id") or event.payload.get(
            "approval_id"
        )

        try:
            if approved:
                await self._control_plane_approvals.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=user_id or "api",
                )
            else:
                await self._control_plane_approvals.reject_for_sensitive_action(
                    approval_id,
                    resolved_by=user_id or "api",
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
            user_id=user_id,
            approved=approved,
        )

        if success:
            logger.info(
                "pattern_approval_processed",
                pattern_id=pattern_id,
                approved=approved,
            )

        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        if request.get("action") == "trigger_analysis":
            days = request.get("days", 7)
            proposals = await self._analyzer.analyze(
                self._db_manager, days,
            )
            proposals = [
                await self._attach_proposal_approval(proposal)
                for proposal in proposals
            ]
            return {"proposals": proposals}
        return {"status": "ok"}

    async def _attach_proposal_approval(
        self,
        proposal: dict,
        *,
        trace_id: str | None = None,
    ) -> dict:
        payload = dict(proposal)
        try:
            approval = await self._control_plane_approvals.request_approval(
                category=ApprovalCategory.TECHNICAL,
                proposed_action=(
                    "Approve evolution proposal "
                    f"{payload.get('operation') or payload.get('pattern_id') or 'unknown'}"
                ),
                reason=payload.get("rationale") or payload.get("description") or "Evolution proposal",
                risk="Changes agent skill, architecture, or collaboration behavior.",
                rollback_note="Reject the proposal or roll back the rollout state before promotion.",
                affected_resources=[
                    str(payload.get("target_agent") or payload.get("pattern_id") or self.agent_id)
                ],
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.error(
                "evolution_approval_request_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._control_plane_approvals.enforced:
                raise
            return payload

        if approval is not None:
            payload["control_plane_approval_id"] = approval.approval_id
        return payload


agent = EvolutionAgent()


def get_agent() -> EvolutionAgent:
    return agent
