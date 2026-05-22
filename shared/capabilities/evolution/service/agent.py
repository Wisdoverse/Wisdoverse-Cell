"""
EvolutionModule — Analyzes global trace data and proposes architecture-level optimizations.

CRITICAL: This module must NOT be wrapped with EvolvedAgent (no self-evolution).
Phase 2 operates in suggestion mode only — proposals require human approval.
Phase 3 adds collaboration pattern proposal and approval handling.
"""
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.control_plane import (
    ApprovalGateService,
    EvolutionTier,
)
from shared.core import EventPublisher
from shared.evolution.config import evolution_settings
from shared.evolution.db.database import EvolutionDatabaseManager, db_manager
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import LLMGateway, llm_gateway
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.analysis_ports import EvolutionTraceAnalysisStore
from ..core.application_facade import EvolutionApplicationFacade
from ..core.control_plane_ports import EvolutionControlPlaneProposalStore
from ..core.health_ports import EvolutionHealthStore
from ..core.outbox_ports import EvolutionEventOutboxStore
from ..core.proposal_approval_use_cases import EvolutionProposalApprovalUseCase
from ..core.seed_ports import EvolutionSkillSeedStore
from ..db.control_plane_store import (
    SqlAlchemyEvolutionControlPlaneProposalStore,
    default_control_plane_session_provider,
)
from ..db.health_store import SqlAlchemyEvolutionHealthStore
from ..db.outbox_store import SqlAlchemyEvolutionEventOutboxStore
from ..db.skill_seed_store import SqlAlchemyEvolutionSkillSeedStore
from ..db.trace_analysis_store import SqlAlchemyEvolutionTraceAnalysisStore
from .global_analyzer import GlobalAnalyzer

logger = get_logger("evolution_module.service")

ControlPlaneSessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class EvolutionModule(BaseAgent):
    """Evolution module that analyzes all agents and proposes improvements."""

    def __init__(
        self,
        db: EvolutionDatabaseManager | None = None,
        bus: EventBus | None = None,
        event_publisher: EventPublisher | None = None,
        llm: LLMGateway | None = None,
        control_plane_session_provider: ControlPlaneSessionProvider | None = None,
        control_plane_enabled: bool | None = None,
        outbox_store: EvolutionEventOutboxStore | None = None,
        trace_analysis_store: EvolutionTraceAnalysisStore | None = None,
        seed_store: EvolutionSkillSeedStore | None = None,
        health_store: EvolutionHealthStore | None = None,
        control_plane_proposal_store: EvolutionControlPlaneProposalStore | None = None,
    ):
        super().__init__(
            agent_id="evolution-module",
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
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._llm = llm or llm_gateway
        self._outbox_store = outbox_store or SqlAlchemyEvolutionEventOutboxStore(
            self._db_manager
        )
        self._trace_analysis_store = (
            trace_analysis_store
            or SqlAlchemyEvolutionTraceAnalysisStore(self._db_manager)
        )
        self._seed_store = (
            seed_store
            or SqlAlchemyEvolutionSkillSeedStore(self._db_manager)
        )
        self._health_store = (
            health_store
            or SqlAlchemyEvolutionHealthStore(self._db_manager)
        )
        self._control_plane_session_provider = control_plane_session_provider
        self._control_plane_enabled = control_plane_enabled
        self._control_plane_proposal_store = control_plane_proposal_store
        self._analyzer = GlobalAnalyzer(
            self._llm,
            self._trace_analysis_store,
        )
        self._approval_gateway = None
        self._control_plane_approvals = ApprovalGateService(
            source_agent_id=self.agent_id,
            session_provider=control_plane_session_provider,
            enabled=control_plane_enabled,
        )
        self._application = EvolutionApplicationFacade(
            standard_request_handler=self.handle_standard_request,
            analyzer_provider=lambda: self._analyzer,
            attach_proposal_approval=self._attach_proposal_approval,
            event_factory=self,
            approval_service_provider=lambda: self._control_plane_approvals,
            approval_gateway_provider=lambda: self._approval_gateway,
            collaboration_enabled_provider=(
                lambda: evolution_settings.collaboration_enabled
            ),
            health_store_provider=lambda: self._health_store,
            event_bus=self._event_bus,
            llm_gateway_provider=lambda: self._llm,
            seed_store_provider=lambda: self._seed_store,
            outbox_store_provider=lambda: self._outbox_store,
            event_publisher=self._event_publisher,
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

    async def _bootstrap_seeds(self) -> int:
        """Load skill seed configs into DB if not already present."""
        return await self._application.bootstrap_seeds()

    def set_approval_gateway(self, gateway) -> None:
        """Inject ApprovalGateway for processing pattern approvals."""
        self._approval_gateway = gateway

    async def handle_event(self, event: Event) -> list[Event]:
        return await self._application.handle_event(event)

    async def handle_request(self, request: dict) -> dict:
        return await self._application.handle_request(request)

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the evolution capability boundary."""
        return await self._application.health_check()

    async def publish_pending_evolution_events(self, limit: int = 100) -> dict[str, int]:
        """Retry pending Evolution outbox events."""
        return await self._application.publish_pending_evolution_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Evolution event before EventBus delivery."""
        return await self._application.publish_event_via_outbox(event)

    async def _attach_proposal_approval(
        self,
        proposal: dict,
        *,
        trace_id: str | None = None,
        tier: EvolutionTier | None = None,
    ) -> dict:
        return await self._proposal_approval_use_case().attach_approval(
            proposal,
            trace_id=trace_id,
            tier=tier,
        )

    def _proposal_approval_use_case(self) -> EvolutionProposalApprovalUseCase:
        return EvolutionProposalApprovalUseCase(
            approval_service=self._control_plane_approvals,
            proposal_store=(
                self._get_control_plane_proposal_store()
                if self._control_plane_records_enabled
                else None
            ),
            source_agent_id=self.agent_id,
            company_id=settings.control_plane_company_id,
            records_enabled=self._control_plane_records_enabled,
        )

    def _get_control_plane_proposal_store(self) -> EvolutionControlPlaneProposalStore:
        if self._control_plane_proposal_store is None:
            self._control_plane_proposal_store = SqlAlchemyEvolutionControlPlaneProposalStore(
                self._resolve_control_plane_session_provider()
            )
        return self._control_plane_proposal_store

    @property
    def _control_plane_records_enabled(self) -> bool:
        if self._control_plane_enabled is not None:
            return self._control_plane_enabled
        return settings.control_plane_enabled or settings.control_plane_approval_enforced

    def _resolve_control_plane_session_provider(self) -> ControlPlaneSessionProvider:
        if self._control_plane_session_provider is not None:
            return self._control_plane_session_provider
        return default_control_plane_session_provider()


agent = EvolutionModule()


def get_agent() -> EvolutionModule:
    return agent
