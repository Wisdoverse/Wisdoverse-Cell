"""
EvolutionAgent — Analyzes global trace data and proposes architecture-level optimizations.

CRITICAL: This agent must NOT be wrapped with EvolvedAgent (no self-evolution).
Phase 2 operates in suggestion mode only — proposals require human approval.
Phase 3 adds collaboration pattern proposal and approval handling.
"""
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.control_plane import (
    ApprovalCategory,
    ApprovalGateService,
    ApprovalRequiredError,
    ApprovalStatus,
    AuditEvent,
    CompanyContext,
    EvolutionProposal,
    EvolutionTier,
)
from shared.control_plane.repository import ControlPlaneRepository
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

ControlPlaneSessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class EvolutionAgent(BaseAgent):
    """Evolution engine that analyzes all agents and proposes improvements."""

    def __init__(
        self,
        db: EvolutionDatabaseManager | None = None,
        bus: EventBus | None = None,
        llm: LLMGateway | None = None,
        control_plane_session_provider: ControlPlaneSessionProvider | None = None,
        control_plane_enabled: bool | None = None,
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
        self._control_plane_session_provider = control_plane_session_provider
        self._control_plane_enabled = control_plane_enabled
        self._analyzer = GlobalAnalyzer(self._llm)
        self._approval_gateway = None
        self._control_plane_approvals = ApprovalGateService(
            source_agent_id=self.agent_id,
            session_provider=control_plane_session_provider,
            enabled=control_plane_enabled,
        )

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
                await self._control_plane_approvals.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
            else:
                await self._control_plane_approvals.reject_for_sensitive_action(
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
        """Process approval of a collaboration pattern via ApprovalGateway."""
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
                await self._control_plane_approvals.approve_for_sensitive_action(
                    approval_id,
                    resolved_by=resolved_by or "api",
                )
            else:
                await self._control_plane_approvals.reject_for_sensitive_action(
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

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the evolution capability boundary."""
        checks = {
            "database": False,
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "llm_gateway": self._llm is not None,
            "control_plane_approval_service": self._control_plane_approvals is not None,
        }
        if evolution_settings.collaboration_enabled:
            checks["collaboration_approval_gateway"] = self._approval_gateway is not None
        try:
            async with self._db_manager.session() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as exc:
            logger.error(
                "health_check_db_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return checks

    async def _attach_proposal_approval(
        self,
        proposal: dict,
        *,
        trace_id: str | None = None,
        tier: EvolutionTier | None = None,
    ) -> dict:
        payload = dict(proposal)
        await self._ensure_control_plane_company()
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
        payload = await self._record_control_plane_proposal(
            payload,
            approval=approval,
            trace_id=trace_id,
            tier=tier or self._infer_proposal_tier(payload),
        )
        return payload

    async def _record_control_plane_proposal(
        self,
        payload: dict,
        *,
        approval,
        trace_id: str | None,
        tier: EvolutionTier,
    ) -> dict:
        if not self._control_plane_records_enabled:
            return payload

        company_id = settings.control_plane_company_id
        approval_id = getattr(approval, "approval_id", None) or payload.get(
            "control_plane_approval_id"
        )
        approval_state = (
            getattr(approval, "status", None)
            or ApprovalStatus.PENDING.value
        )
        scope = self._proposal_scope(payload, tier)
        evidence = {
            "source_agent": self.agent_id,
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
            "proposed_by": self.agent_id,
            "operation": payload.get("operation"),
            "target_agent": payload.get("target_agent"),
            "target_skill": payload.get("target_skill"),
            "pattern_id": payload.get("pattern_id"),
        }

        try:
            async with self._resolve_control_plane_session_provider()() as session:
                repo = ControlPlaneRepository(session)
                if await repo.get_company(company_id) is None:
                    await repo.create_company(
                        CompanyContext(
                            company_id=company_id,
                            name="Wisdoverse Cell",
                            mission="AI-native company operations",
                        )
                    )
                row = await repo.create_evolution_proposal(
                    EvolutionProposal(
                        company_id=company_id,
                        tier=tier,
                        scope=scope,
                        evidence=evidence,
                        expected_benefit=expected_benefit,
                        risk=risk,
                        approval_state=approval_state,
                        approval_id=approval_id,
                        metadata=metadata,
                    )
                )
                await repo.append_audit_event(
                    AuditEvent(
                        company_id=company_id,
                        action=EventTypes.EVOLUTION_PROPOSAL_CREATED,
                        target_type="evolution_proposal",
                        target_id=row.proposal_id,
                        actor_type="agent",
                        actor_id=self.agent_id,
                        trace_id=trace_id,
                        detail={
                            "proposal_id": row.proposal_id,
                            "tier": row.tier,
                            "scope": row.scope,
                            "approval_state": row.approval_state,
                            "rollout_state": row.rollout_state,
                            "approval_id": row.approval_id,
                        },
                    )
                )
        except Exception as exc:
            logger.error(
                "control_plane_evolution_proposal_record_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._control_plane_approvals.enforced:
                raise
            return payload

        payload["control_plane_proposal_id"] = row.proposal_id
        return payload

    async def _ensure_control_plane_company(self) -> None:
        if not self._control_plane_records_enabled:
            return
        company_id = settings.control_plane_company_id
        try:
            async with self._resolve_control_plane_session_provider()() as session:
                repo = ControlPlaneRepository(session)
                if await repo.get_company(company_id) is None:
                    await repo.create_company(
                        CompanyContext(
                            company_id=company_id,
                            name="Wisdoverse Cell",
                            mission="AI-native company operations",
                        )
                    )
        except Exception as exc:
            logger.error(
                "control_plane_company_ensure_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if self._control_plane_approvals.enforced:
                raise

    @property
    def _control_plane_records_enabled(self) -> bool:
        if self._control_plane_enabled is not None:
            return self._control_plane_enabled
        return settings.control_plane_enabled or settings.control_plane_approval_enforced

    def _resolve_control_plane_session_provider(self) -> ControlPlaneSessionProvider:
        if self._control_plane_session_provider is not None:
            return self._control_plane_session_provider
        from shared.control_plane.database import control_plane_db_manager

        return control_plane_db_manager.session

    @staticmethod
    def _infer_proposal_tier(payload: dict) -> EvolutionTier:
        if "pattern_id" in payload:
            return EvolutionTier.L3
        operation = payload.get("operation")
        if operation in {"modify_event_subscription", "add_loop_logic"}:
            return EvolutionTier.L2
        return EvolutionTier.L1

    @staticmethod
    def _proposal_scope(payload: dict, tier: EvolutionTier) -> str:
        if tier == EvolutionTier.L3:
            return f"pattern:{payload.get('pattern_id') or payload.get('name') or 'unknown'}"
        target_agent = payload.get("target_agent") or "unknown-agent"
        target_skill = payload.get("target_skill")
        if target_skill:
            return f"agent:{target_agent}/skill:{target_skill}"
        return f"agent:{target_agent}"


agent = EvolutionAgent()


def get_agent() -> EvolutionAgent:
    return agent
