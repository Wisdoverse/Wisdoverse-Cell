"""
RequirementManagerAgent core.

Inherits BaseAgent and implements the standard Agent interface. All business
logic is coordinated through this class; FastAPI is only the HTTP adapter.
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings as app_settings
from shared.control_plane.agent_prompt_config import resolve_agent_system_prompt
from shared.core import EventPublisher, FeishuMessengerPort
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.infra.notification import NotificationChannel, notification_service
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.card_ports import RequirementCardRendererPort
from ..core.event_use_cases import (
    SUBSCRIBED_EVENTS,
    RequirementManagerEventUseCase,
)
from ..core.extractor import RequirementExtractor
from ..core.health_ports import RequirementHealthStore
from ..core.health_use_cases import RequirementHealthUseCase
from ..core.ingest_side_effect_use_cases import (
    RequirementIngestSideEffectUseCase,
    RequirementSessionExtractionCardUseCase,
)
from ..core.meeting_ingest_workflow import (
    IngestResult,
    RequirementMeetingIngestWorkflow,
)
from ..core.mutation_side_effect_use_cases import RequirementMutationSideEffectUseCase
from ..core.outbox_delivery_use_cases import RequirementOutboxDeliveryUseCase
from ..core.outbox_ports import RequirementEventOutboxStore
from ..core.read_query_use_cases import RequirementReadQueryUseCase
from ..core.request_use_cases import RequirementManagerRequestUseCase
from ..core.requirement_command_use_cases import RequirementCommandUseCase
from ..core.requirement_mutation_workflow import (
    RequirementMutationResult,
    RequirementMutationWorkflow,
)
from ..core.session_extraction_use_cases import (
    RequirementSessionExtractionUseCase,
    format_messages_for_extraction,
)
from ..core.unit_of_work_ports import (
    RequirementUnitOfWork,
    RequirementUnitOfWorkFactory,
)
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyRequirementHealthStore
from ..db.outbox_store import SqlAlchemyRequirementEventOutboxStore
from ..db.unit_of_work import (
    SqlAlchemyRequirementSessionUnitOfWork,
    SqlAlchemyRequirementUnitOfWorkFactory,
)
from ..db.vector_store import VectorStore, vector_store
from ..models import Meeting, OpenQuestion, Requirement

logger = get_logger("requirement-manager.agent")


class RequirementManagerAgent(BaseAgent):
    """
    Requirement management agent.

    Responsibilities:
    - Extract requirements from meeting records.
    - Manage the requirement lifecycle from pending to confirmed or rejected.
    - Publish requirement events for other agents to consume.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        vectors: Optional[VectorStore] = None,
        requirement_extractor: Optional[RequirementExtractor] = None,
        messenger: Optional[FeishuMessengerPort] = None,
        card_renderer: Optional[RequirementCardRendererPort] = None,
        outbox_store: RequirementEventOutboxStore | None = None,
        health_store: RequirementHealthStore | None = None,
    ):
        super().__init__(
            agent_id="requirement-manager",
            agent_name="Requirement Manager",
            subscribed_events=SUBSCRIBED_EVENTS,
            published_events=[
                EventTypes.REQUIREMENT_EXTRACTED,
                EventTypes.REQUIREMENT_CONFIRMED,
                EventTypes.REQUIREMENT_REJECTED,
                EventTypes.REQUIREMENT_CHANGED,
                EventTypes.REQUIREMENT_DELETED,
            ]
        )
        # Dependency injection supports replacement during tests.
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store or SqlAlchemyRequirementEventOutboxStore(
            self._db_manager
        )
        self._uow_factory: RequirementUnitOfWorkFactory = (
            SqlAlchemyRequirementUnitOfWorkFactory(self._db_manager)
        )
        self._health_store = health_store or SqlAlchemyRequirementHealthStore(
            self._db_manager
        )
        self._vector_store = vectors or vector_store
        self._extractor = requirement_extractor or RequirementExtractor(
            llm=llm_gateway,
            system_prompt_resolver=resolve_agent_system_prompt,
        )
        self._ingest_workflow = RequirementMeetingIngestWorkflow(
            extractor=self._extractor,
            vector_index=self._vector_store,
        )
        self._mutation_workflow = RequirementMutationWorkflow()
        self._messenger = messenger
        self._card_renderer = card_renderer

    def configure_messenger(self, messenger: FeishuMessengerPort | None) -> None:
        """Wire the outbound messaging adapter at the service entry point."""
        self._messenger = messenger

    def configure_card_renderer(
        self,
        card_renderer: RequirementCardRendererPort | None,
    ) -> None:
        """Wire the outbound card renderer at the service entry point."""
        self._card_renderer = card_renderer

    @property
    def mutation_workflow(self) -> RequirementMutationWorkflow:
        """Expose the application workflow for HTTP use-case composition."""
        return self._mutation_workflow

    @property
    def mutation_side_effects(self) -> RequirementMutationSideEffectUseCase:
        """Expose committed-mutation side effects for HTTP use-case composition."""
        return self._mutation_side_effect_use_case()

    # ========== Lifecycle ==========

    async def startup(self):
        """Initialize resources when the agent starts."""
        logger.info("agent_starting", agent_id=self.agent_id)

        # Initialize database tables (production uses Alembic).
        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")
        else:
            logger.info("schema_managed_by_alembic")

        # Connect EventBus.
        await self._event_bus.connect()
        logger.info("event_bus_connected")

        # Vector store lifecycle is now managed by VectorStorePlugin.
        # The plugin starts during runtime.startup() and the facade is
        # bound via the on_startup callback in main.py.

        # Event loop is managed by AgentRuntime.start_event_loop()

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        """Clean up resources when the agent stops."""
        logger.info("agent_stopping", agent_id=self.agent_id)

        await self._event_bus.disconnect()

        # Vector store lifecycle is now managed by VectorStorePlugin.
        # Shutdown is handled via the on_shutdown callback in main.py.

        # Close database connections.
        await self._db_manager.close()

        logger.info("agent_stopped", agent_id=self.agent_id)

    # ========== Event Handling ==========

    async def handle_event(self, event: Event) -> list[Event]:
        """
        Handle a received event.

        Delegates handling to the application event use case.
        """
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> RequirementManagerEventUseCase:
        return RequirementManagerEventUseCase(
            agent=self,
            uow_factory=self.get_unit_of_work,
        )

    async def handle_request(self, request: dict) -> dict:
        """
        Handle an API request.

        This method is reserved for future extensions. Current FastAPI routes
        call business methods directly.
        """
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> RequirementManagerRequestUseCase:
        return RequirementManagerRequestUseCase(
            agent=self,
            uow_factory=self.get_unit_of_work,
        )

    def get_unit_of_work(self):
        """Open one transaction-scoped Requirement unit of work."""
        return self._uow_factory()

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the requirement manager runtime boundary."""
        return await self._health_use_case().check()

    def _health_use_case(self) -> RequirementHealthUseCase:
        return RequirementHealthUseCase(
            health_store=self._health_store,
            event_bus=self._event_bus,
            messenger=self._messenger,
            card_renderer=self._card_renderer,
        )

    # ========== Business Methods ==========

    async def ingest_meeting(
        self,
        content: str,
        source: str,
        session: AsyncSession | None = None,
        title: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        participants: Optional[list[str]] = None,
        context: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> IngestResult:
        """
        Ingest meeting content and extract requirements.

        Args:
            content: Raw meeting content.
            source: Source channel (upload/feishu/wechat).
            session: Optional existing database session for compatibility.
            title: Meeting title.
            meeting_date: Meeting date.
            participants: Participant list.
            context: Additional context.
            source_id: Source-system ID for deduplication.

        Returns:
            IngestResult with extracted requirement and question counts.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            result = await self.ingest_meeting_with_uow(
                content=content,
                source=source,
                uow=uow,
                title=title,
                meeting_date=meeting_date,
                participants=participants,
                context=context,
                source_id=source_id,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.ingest_meeting_with_uow(
                    content=content,
                    source=source,
                    uow=uow,
                    title=title,
                    meeting_date=meeting_date,
                    participants=participants,
                    context=context,
                    source_id=source_id,
                )
                await uow.commit()

        await self.publish_ingest_side_effects(result)
        return result

    async def ingest_meeting_with_uow(
        self,
        *,
        content: str,
        source: str,
        uow: RequirementUnitOfWork,
        title: Optional[str] = None,
        meeting_date: Optional[datetime] = None,
        participants: Optional[list[str]] = None,
        context: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> IngestResult:
        """Ingest meeting content inside an explicit Requirement unit of work."""
        return await self._ingest_workflow.ingest_meeting(
            content=content,
            source=source,
            uow=uow,
            title=title,
            meeting_date=meeting_date,
            participants=participants,
            context=context,
            source_id=source_id,
        )

    async def publish_ingest_side_effects(self, result: IngestResult) -> None:
        """Publish integration and notification side effects after ingest commit."""
        await self._ingest_side_effect_use_case().publish_ingest_side_effects(result)

    async def confirm_requirement(
        self,
        requirement_id: str,
        confirmed_by: str,
        session: AsyncSession | None = None,
    ) -> Optional[Requirement]:
        """
        Confirm a requirement.

        Args:
            requirement_id: Requirement ID.
            confirmed_by: Confirmer.
            session: Optional existing database session for compatibility.

        Returns:
            Confirmed requirement, or None if it does not exist.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._command_use_case().confirm_requirement(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=uow,
            )
        return await self._command_use_case().confirm_requirement(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
        )

    async def confirm_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Confirm one requirement through the application workflow."""
        return await self._command_use_case().confirm_requirement_with_uow(
            requirement_id=requirement_id,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def reject_requirement(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        session: AsyncSession | None = None,
    ) -> Optional[Requirement]:
        """
        Reject a requirement.

        Args:
            requirement_id: Requirement ID.
            reason: Rejection reason.
            rejected_by: Rejecting user.
            session: Optional existing database session for compatibility.

        Returns:
            Rejected requirement, or None if it does not exist.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._command_use_case().reject_requirement(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
        return await self._command_use_case().reject_requirement(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def reject_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Reject one requirement through the application workflow."""
        return await self._command_use_case().reject_requirement_with_uow(
            requirement_id=requirement_id,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def update_requirement(
        self,
        requirement_id: str,
        changes: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> Optional[Requirement]:
        """
        Update a requirement through the application boundary.

        HTTP/RPC adapters pass validated DTO data here. This use case owns
        history recording, feedback learning, and event publication.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._command_use_case().update_requirement(
                requirement_id=requirement_id,
                changes=changes,
                uow=uow,
            )
        return await self._command_use_case().update_requirement(
            requirement_id=requirement_id,
            changes=changes,
        )

    async def update_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Update one requirement through the application workflow."""
        return await self._command_use_case().update_requirement_with_uow(
            requirement_id=requirement_id,
            changes=changes,
            uow=uow,
        )

    async def delete_requirement(
        self,
        requirement_id: str,
        deleted_by: str,
        session: AsyncSession | None = None,
    ) -> Optional[Requirement]:
        """
        Delete a requirement.

        Also deletes the vector-store record and publishes an event.

        Args:
            requirement_id: Requirement ID.
            deleted_by: Deleting user.
            session: Optional existing database session for compatibility.

        Returns:
            Deleted requirement, or None if it does not exist.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._command_use_case().delete_requirement(
                requirement_id=requirement_id,
                deleted_by=deleted_by,
                uow=uow,
            )
        return await self._command_use_case().delete_requirement(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
        )

    async def delete_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Delete one requirement through the application workflow."""
        return await self._command_use_case().delete_requirement_with_uow(
            requirement_id=requirement_id,
            deleted_by=deleted_by,
            uow=uow,
        )

    async def answer_question(
        self,
        question_id: str,
        answer: str,
        answered_by: str,
        session: AsyncSession | None = None,
    ) -> Optional[OpenQuestion]:
        """
        Answer an open clarification question through the application boundary.

        HTTP/RPC adapters pass validated DTO data here. This use case owns the
        write transaction and keeps the route layer free of persistence rules.
        """
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._command_use_case().answer_question(
                question_id,
                answer=answer,
                answered_by=answered_by,
                uow=uow,
            )
        return await self._command_use_case().answer_question(
            question_id,
            answer=answer,
            answered_by=answered_by,
        )

    async def answer_question_with_uow(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Answer one open question through the application workflow."""
        return await self._command_use_case().answer_question_with_uow(
            question_id,
            answer=answer,
            answered_by=answered_by,
            uow=uow,
        )

    async def list_open_questions(
        self,
        session: AsyncSession | None = None,
        *,
        limit: int = 50,
    ) -> list[OpenQuestion]:
        """List unanswered clarification questions through the application facade."""
        if session is not None:
            uow = self._session_unit_of_work(session)
            return await self._read_query_use_case().list_open_questions_with_uow(
                uow,
                limit=limit,
            )

        return await self._read_query_use_case().list_open_questions(limit=limit)

    async def publish_requirement_mutation_side_effects(
        self,
        result: RequirementMutationResult,
    ) -> None:
        await self._mutation_side_effect_use_case().publish_requirement_mutation_side_effects(
            result,
        )

    def _command_use_case(self) -> RequirementCommandUseCase:
        return RequirementCommandUseCase(
            mutation_workflow=self._mutation_workflow,
            side_effects=self._mutation_side_effect_use_case(),
            uow_factory=self.get_unit_of_work,
        )

    def _mutation_side_effect_use_case(self) -> RequirementMutationSideEffectUseCase:
        return RequirementMutationSideEffectUseCase(
            vector_index=self._vector_store,
            event_publisher=self._outbox_delivery_use_case(),
        )

    def _ingest_side_effect_use_case(self) -> RequirementIngestSideEffectUseCase:
        return RequirementIngestSideEffectUseCase(
            event_publisher=self._outbox_delivery_use_case(),
            notifier=notification_service,
            notification_channel=NotificationChannel.FEISHU,
        )

    async def publish_pending_requirement_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> RequirementOutboxDeliveryUseCase:
        return RequirementOutboxDeliveryUseCase(
            outbox_store=self._outbox_store,
            event_publisher=self._event_publisher,
        )

    def _read_query_use_case(self) -> RequirementReadQueryUseCase:
        return RequirementReadQueryUseCase(
            uow_factory=self.get_unit_of_work,
        )

    def _session_unit_of_work(
        self,
        session: AsyncSession,
    ) -> RequirementUnitOfWork:
        """Adapt a caller-owned legacy SQLAlchemy session to the UOW boundary."""
        return SqlAlchemyRequirementSessionUnitOfWork(
            session,
            outbox_store=self._outbox_store,
        )

    # ========== Convenience Methods Without External Sessions ==========

    async def list_pending_requirements(
        self,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict], int, int]:
        return await self._read_query_use_case().list_pending_requirements(
            page=page,
            page_size=page_size,
        )

    async def get_confirmed_requirements(self) -> list[dict]:
        return await self._read_query_use_case().get_confirmed_requirements()

    async def batch_confirm_requirements(
        self,
        requirement_ids: list[str],
        confirmed_by: str,
    ) -> list[dict]:
        """
        Confirm requirements in a batch.

        Args:
            requirement_ids: Requirement ID list.
            confirmed_by: Confirmer.

        Returns:
            Operation results; each item contains requirement_id, success, and error.
        """
        return await self._command_use_case().batch_confirm_requirements(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
        )

    async def batch_confirm_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Confirm requirements through the application workflow."""
        return await self._command_use_case().batch_confirm_requirements_with_uow(
            requirement_ids=requirement_ids,
            confirmed_by=confirmed_by,
            uow=uow,
        )

    async def batch_reject_requirements(
        self,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
    ) -> list[dict]:
        """
        Reject requirements in a batch.

        Args:
            requirement_ids: Requirement ID list.
            reason: Shared rejection reason.
            rejected_by: Rejecting user.

        Returns:
            Operation results; each item contains requirement_id, success, and error.
        """
        return await self._command_use_case().batch_reject_requirements(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
        )

    async def batch_reject_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Reject requirements through the application workflow."""
        return await self._command_use_case().batch_reject_requirements_with_uow(
            requirement_ids=requirement_ids,
            reason=reason,
            rejected_by=rejected_by,
            uow=uow,
        )

    async def get_requirement(self, requirement_id: str) -> Optional[Requirement]:
        return await self._read_query_use_case().get_requirement(requirement_id)

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        return await self._read_query_use_case().get_meeting(meeting_id)

    # ========== Session Extraction Methods ==========

    async def extract_from_session(self, session_id: str) -> Optional[IngestResult]:
        """Extract requirements from a chat session's messages."""
        return await self._session_extraction_use_case().extract_from_session(
            session_id,
        )

    def _session_extraction_use_case(self) -> RequirementSessionExtractionUseCase:
        return RequirementSessionExtractionUseCase(
            agent=self,
            uow_factory=self.get_unit_of_work,
        )

    def _session_card_use_case(self) -> RequirementSessionExtractionCardUseCase:
        return RequirementSessionExtractionCardUseCase(
            messenger=self._messenger,
            card_renderer=self._card_renderer,
        )

    def _format_messages_for_extraction(self, messages: list) -> str:
        """Format messages as conversation text for LLM extraction."""
        return format_messages_for_extraction(messages)

    async def send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ) -> None:
        """Send extraction result card to the originating chat."""
        await self._send_session_extraction_card(chat_id, result, session_id)

    async def _send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ):
        """Send extraction result card to the chat."""
        await self._session_card_use_case().send_session_extraction_card(
            chat_id,
            result,
            session_id,
        )


# Global Agent singleton.
agent = RequirementManagerAgent()


def get_agent() -> RequirementManagerAgent:
    """Get the current Agent instance; tests can replace it."""
    return agent
