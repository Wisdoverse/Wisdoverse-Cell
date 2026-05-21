"""
RequirementManagerAgent core.

Inherits BaseAgent and implements the standard Agent interface. All business
logic is coordinated through this class; FastAPI is only the HTTP adapter.
"""
import inspect
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings as app_settings
from shared.control_plane.agent_prompt_config import resolve_agent_system_prompt
from shared.core import EventPublisher, FeishuMessengerPort
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.infra.llm_gateway import llm_gateway
from shared.infra.notification import NotificationChannel, notification_service
from shared.observability.outbox import record_outbox_pending_age
from shared.observability.privacy import hash_identifier
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..core.card_ports import RequirementCardRendererPort
from ..core.event_use_cases import (
    SUBSCRIBED_EVENTS,
    RequirementManagerEventUseCase,
)
from ..core.extractor import RequirementExtractor
from ..core.health_ports import RequirementHealthStore
from ..core.health_use_cases import RequirementHealthUseCase
from ..core.meeting_ports import RequirementMeetingStore
from ..core.message_ports import RequirementMessageStore
from ..core.outbox_ports import RequirementEventOutboxStore
from ..core.question_ports import RequirementQuestionStore
from ..core.request_use_cases import RequirementManagerRequestUseCase
from ..core.requirement_lifecycle import record_updated
from ..core.requirement_ports import RequirementStore
from ..core.unit_of_work_ports import (
    RequirementOutboxWriter,
    RequirementUnitOfWork,
    RequirementUnitOfWorkFactory,
)
from ..db.database import DatabaseManager, db_manager
from ..db.feedback_store import SqlAlchemyRequirementFeedbackStore
from ..db.health_store import SqlAlchemyRequirementHealthStore
from ..db.meeting_store import SqlAlchemyRequirementMeetingStore
from ..db.message_store import SqlAlchemyRequirementMessageStore
from ..db.outbox_store import SqlAlchemyRequirementEventOutboxStore
from ..db.question_store import SqlAlchemyRequirementQuestionStore
from ..db.requirement_store import SqlAlchemyRequirementStore
from ..db.unit_of_work import SqlAlchemyRequirementUnitOfWorkFactory
from ..db.vector_store import VectorStore, vector_store
from ..models import Meeting, OpenQuestion, Requirement

logger = get_logger("requirement-manager.agent")


@dataclass
class IngestResult:
    """Meeting ingestion result."""
    meeting_id: str
    requirements_extracted: int
    questions_generated: int
    requirement_ids: list[str]
    requirements: list[Requirement] = field(default_factory=list, repr=False)
    open_questions: list[OpenQuestion] = field(default_factory=list, repr=False)
    staged_events: list[Event] = field(default_factory=list, repr=False)


@dataclass
class RequirementMutationResult:
    """Requirement mutation result with post-commit side effects."""

    entity: Requirement | OpenQuestion | None
    event: Event | None = None
    requirement_id: str | None = None
    delete_vector_requirement_id: str | None = None


class _RequirementSessionOutboxWriter(RequirementOutboxWriter):
    """Adapter for staging outbox rows in a caller-owned legacy session."""

    def __init__(self, agent: "RequirementManagerAgent", session: AsyncSession):
        self._agent = agent
        self._session = session

    async def stage(self, event: Event) -> None:
        await self._agent._stage_requirement_event(self._session, event)


class _RequirementSessionUnitOfWork(RequirementUnitOfWork):
    """Compatibility UOW for existing callers that still pass a session."""

    def __init__(self, agent: "RequirementManagerAgent", session: AsyncSession):
        self._agent = agent
        self._session = session
        self.meetings = agent._get_meeting_store(session)
        self.requirements = agent._get_requirement_store(session)
        self.questions = agent._get_question_store(session)
        self.messages = agent._get_message_store(session)
        self.feedback = SqlAlchemyRequirementFeedbackStore(session)
        self.outbox = _RequirementSessionOutboxWriter(agent, session)
        self.completed = False

    async def commit(self) -> None:
        await self._agent._commit_requirement_mutation(
            self._session,
            use_case="requirement_mutation",
        )
        self.completed = True

    async def rollback(self) -> None:
        result = self._session.rollback()
        if inspect.isawaitable(result):
            await result
        self.completed = True


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
            uow = _RequirementSessionUnitOfWork(self, session)
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
        meeting_store = uow.meetings
        requirement_store = uow.requirements
        question_store = uow.questions

        # Create meeting record.
        meeting = Meeting(
            source=source,
            source_id=source_id,
            title=title,
            raw_content=content,
            meeting_date=meeting_date,
            participants=participants or [],
            context=context
        )
        await meeting_store.create(meeting)

        logger.info(
            "meeting_created",
            meeting_id=meeting.id,
            source=source,
            content_length=len(content)
        )

        # Extract requirements.
        result = await self._extractor.extract(
            content=content,
            source=source,
            meeting_date=meeting_date.isoformat() if meeting_date else None,
            participants=participants,
            context=context
        )

        # Save requirements.
        requirements: list[Requirement] = []
        for req in result.requirements:
            requirement = Requirement(
                title=req.title,
                description=req.description,
                category=req.category,
                priority=req.priority,
                source_quote=req.source_quote,
                source_meeting_ids=[meeting.id]
            )
            requirements.append(requirement)

        if requirements:
            await requirement_store.create_batch(requirements)

            # Add to vector store synchronously; non-critical failure does not block the main flow.
            try:
                vector_docs = [
                    {
                        "id": req.id,
                        "title": req.title,
                        "description": req.description,
                        "category": req.category,
                        "metadata": {"meeting_id": meeting.id, "priority": req.priority}
                    }
                    for req in requirements
                ]
                await self._vector_store.add_requirements_batch(vector_docs)
            except Exception as e:
                logger.warning(
                    "vector_store_batch_add_failed",
                    meeting_id=meeting.id,
                    count=len(requirements),
                    error=str(e),
                )

        # Save questions.
        questions: list[OpenQuestion] = []
        for q in result.open_questions:
            req_id = requirements[0].id if requirements else None
            if req_id:
                question = OpenQuestion(
                    requirement_id=req_id,
                    question=q.question,
                    context=q.context
                )
                questions.append(question)

        if questions:
            await question_store.create_batch(questions)

        # Mark meeting as processed.
        await meeting_store.mark_processed(meeting.id)

        extracted_event = None
        if requirements:
            extracted_event = self._create_requirements_extracted_event(
                requirements=requirements,
                meeting_id=meeting.id,
            )
            await uow.outbox.stage(extracted_event)

        return IngestResult(
            meeting_id=meeting.id,
            requirements_extracted=len(requirements),
            questions_generated=len(questions),
            requirement_ids=[r.id for r in requirements],
            requirements=requirements,
            open_questions=questions,
            staged_events=[extracted_event] if extracted_event else [],
        )

    async def publish_ingest_side_effects(self, result: IngestResult) -> None:
        """Publish integration and notification side effects after ingest commit."""
        for event in result.staged_events:
            await self._publish_staged_requirement_event(event)

        if result.requirements_extracted <= 0:
            return

        try:
            await notification_service.send(
                channel=NotificationChannel.FEISHU,
                title="新需求待确认",
                content=(
                    f"从会议中提取了 {result.requirements_extracted} 个新需求，"
                    f"{result.questions_generated} 个待确认问题。"
                )
            )
        except Exception as e:
            logger.warning(
                "notification_send_failed",
                meeting_id=result.meeting_id,
                error=str(e),
            )

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
            uow = _RequirementSessionUnitOfWork(self, session)
            result = await self.confirm_requirement_with_uow(
                requirement_id=requirement_id,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.confirm_requirement_with_uow(
                    requirement_id=requirement_id,
                    confirmed_by=confirmed_by,
                    uow=uow,
                )
                await uow.commit()

        await self.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def confirm_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Confirm one requirement inside an explicit unit of work."""
        requirement = await uow.requirements.confirm(requirement_id, confirmed_by)
        if not requirement:
            return RequirementMutationResult(entity=None)

        logger.info(
            "requirement_confirmed",
            requirement_id=requirement_id,
            confirmed_by=confirmed_by
        )

        event = self._create_requirement_confirmed_event(requirement, confirmed_by)
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
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
            uow = _RequirementSessionUnitOfWork(self, session)
            result = await self.reject_requirement_with_uow(
                requirement_id=requirement_id,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.reject_requirement_with_uow(
                    requirement_id=requirement_id,
                    reason=reason,
                    rejected_by=rejected_by,
                    uow=uow,
                )
                await uow.commit()

        await self.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def reject_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Reject one requirement inside an explicit unit of work."""
        from .feedback_learning import FeedbackLearningService

        # Load the original requirement for feedback learning.
        original_req = await uow.requirements.get_by_id(requirement_id)
        if not original_req:
            return RequirementMutationResult(entity=None)

        original_values = {
            "title": original_req.title,
            "description": original_req.description,
            "priority": original_req.priority,
            "category": original_req.category,
        }

        requirement = await uow.requirements.reject(
            requirement_id,
            reason=reason,
            rejected_by=rejected_by,
        )

        if not requirement:
            return RequirementMutationResult(entity=None)

        logger.info(
            "requirement_rejected",
            requirement_id=requirement_id,
            reason_length=len(reason or ""),
            rejected_by_hash=hash_identifier(rejected_by),
        )

        # Record rejection feedback for learning; failure does not block the main flow.
        try:
            feedback_service = FeedbackLearningService(feedback_store=uow.feedback)
            await feedback_service.record_rejection(
                requirement_id=requirement_id,
                original=original_values,
                rejected_by=rejected_by,
                reason=reason,
            )
        except Exception as e:
            logger.warning(
                "feedback_recording_failed",
                requirement_id=requirement_id,
                error=str(e),
            )

        event = self._create_requirement_rejected_event(requirement, reason)
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
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
            uow = _RequirementSessionUnitOfWork(self, session)
            result = await self.update_requirement_with_uow(
                requirement_id=requirement_id,
                changes=changes,
                uow=uow,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.update_requirement_with_uow(
                    requirement_id=requirement_id,
                    changes=changes,
                    uow=uow,
                )
                await uow.commit()

        await self.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def update_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        changes: dict[str, Any],
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Update one requirement inside an explicit unit of work."""
        from .feedback_learning import FeedbackLearningService

        requirement = await uow.requirements.get_by_id(requirement_id)
        if not requirement:
            return RequirementMutationResult(entity=None)

        update_data = dict(changes)
        comment = update_data.pop("comment", None)
        if not update_data:
            return RequirementMutationResult(entity=requirement)

        original_values = {
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
            "category": requirement.category,
        }
        changed_fields = list(update_data.keys())
        changed_by = comment or "system"

        record_updated(requirement, changed_fields, changed_by)
        requirement = await uow.requirements.update(requirement_id, **update_data)
        if requirement is None:
            return RequirementMutationResult(entity=None)

        feedback_fields = {"title", "description", "priority", "category"}
        if update_data.keys() & feedback_fields:
            try:
                corrected_values = {
                    "title": requirement.title,
                    "description": requirement.description,
                    "priority": requirement.priority,
                    "category": requirement.category,
                }
                feedback_service = FeedbackLearningService(feedback_store=uow.feedback)
                await feedback_service.record_correction(
                    requirement_id=requirement_id,
                    original=original_values,
                    corrected=corrected_values,
                    corrected_by=comment or "user",
                    note=f"Updated fields: {changed_fields}",
                )
            except Exception as exc:
                logger.warning(
                    "feedback_recording_failed",
                    requirement_id=requirement_id,
                    error=str(exc),
                )

        event = self._create_requirement_changed_event(
            requirement,
            changed_fields,
            changed_by,
        )
        await uow.outbox.stage(event)
        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
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
            uow = _RequirementSessionUnitOfWork(self, session)
            result = await self.delete_requirement_with_uow(
                requirement_id=requirement_id,
                deleted_by=deleted_by,
                uow=uow,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.delete_requirement_with_uow(
                    requirement_id=requirement_id,
                    deleted_by=deleted_by,
                    uow=uow,
                )
                await uow.commit()

        await self.publish_requirement_mutation_side_effects(result)
        return result.entity

    async def delete_requirement_with_uow(
        self,
        *,
        requirement_id: str,
        deleted_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Delete one requirement inside an explicit unit of work."""
        requirement = await uow.requirements.delete(requirement_id)
        if not requirement:
            return RequirementMutationResult(entity=None)

        event = self._create_requirement_deleted_event(requirement, deleted_by)
        await uow.outbox.stage(event)

        logger.info(
            "requirement_deleted",
            requirement_id=requirement_id,
            title_hash=hash_identifier(requirement.title),
            deleted_by_hash=hash_identifier(deleted_by),
        )

        return RequirementMutationResult(
            entity=requirement,
            event=event,
            requirement_id=requirement.id,
            delete_vector_requirement_id=requirement_id,
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
            uow = _RequirementSessionUnitOfWork(self, session)
            result = await self.answer_question_with_uow(
                question_id,
                answer=answer,
                answered_by=answered_by,
                uow=uow,
            )
            await uow.commit()
        else:
            async with self.get_unit_of_work() as uow:
                result = await self.answer_question_with_uow(
                    question_id,
                    answer=answer,
                    answered_by=answered_by,
                    uow=uow,
                )
                await uow.commit()

        return result.entity

    async def answer_question_with_uow(
        self,
        question_id: str,
        *,
        answer: str,
        answered_by: str,
        uow: RequirementUnitOfWork,
    ) -> RequirementMutationResult:
        """Answer one open clarification question inside an explicit unit of work."""
        question = await uow.questions.answer(
            question_id,
            answer=answer,
            answered_by=answered_by,
        )
        if not question:
            return RequirementMutationResult(entity=None)

        logger.info(
            "question_answered",
            question_id=question_id,
            answered_by_hash=hash_identifier(answered_by),
        )

        return RequirementMutationResult(entity=question)

    async def list_open_questions(
        self,
        session: AsyncSession | None = None,
        *,
        limit: int = 50,
    ) -> list[OpenQuestion]:
        """List unanswered clarification questions through the application facade."""
        if session is not None:
            return await self._get_question_store(session).list_open(limit=limit)

        async with self.get_unit_of_work() as uow:
            return await uow.questions.list_open(limit=limit)

    async def publish_requirement_mutation_side_effects(
        self,
        result: RequirementMutationResult,
    ) -> None:
        """Run external side effects after a Requirement mutation commits."""
        if result.delete_vector_requirement_id:
            await self._delete_requirement_vector_record(result.delete_vector_requirement_id)
        if result.event:
            await self._publish_staged_requirement_event(
                result.event,
                requirement_id=result.requirement_id,
            )

    async def publish_pending_requirement_events(self, limit: int = 100) -> dict[str, int]:
        """
        Retry pending Requirement outbox events.

        This is intentionally a callable application use case, so a future
        scheduler, admin endpoint, or worker can reuse it without knowing
        persistence details.
        """
        rows = await self._outbox_store.list_pending(limit=limit)
        record_outbox_pending_age("requirement-manager", rows)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            try:
                ok = await self._event_publisher.publish(event)
                if not ok:
                    raise RuntimeError("event_bus_publish_returned_false")
                await self._mark_requirement_event_published(event)
                published += 1
            except Exception as exc:
                await self._mark_requirement_event_failed(event, exc)
                failed += 1

        logger.info(
            "requirement_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced Requirement event before EventBus delivery."""
        await self._outbox_store.add(event)
        await self._publish_staged_requirement_event(event)
        return True

    async def _stage_requirement_event(
        self,
        session: AsyncSession,
        event: Event,
    ) -> Event:
        """Persist an integration event in the local Requirement outbox."""
        await self._outbox_store.stage(session, event)
        return event

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a Requirement outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _commit_requirement_mutation(
        self,
        session: AsyncSession,
        *,
        use_case: str,
    ) -> None:
        """Commit the local requirement transaction before external side effects."""
        result = session.commit()
        if inspect.isawaitable(result):
            await result
        logger.debug("requirement_mutation_committed", use_case=use_case)

    def _get_requirement_store(
        self,
        session: AsyncSession,
    ) -> RequirementStore:
        """Build the persistence adapter for requirement use cases."""
        return SqlAlchemyRequirementStore(session)

    def _get_meeting_store(
        self,
        session: AsyncSession,
    ) -> RequirementMeetingStore:
        """Build the persistence adapter for meeting use cases."""
        return SqlAlchemyRequirementMeetingStore(session)

    def _get_message_store(
        self,
        session: AsyncSession,
    ) -> RequirementMessageStore:
        """Build the persistence adapter for chat-message use cases."""
        return SqlAlchemyRequirementMessageStore(session)

    def _get_question_store(
        self,
        session: AsyncSession,
    ) -> RequirementQuestionStore:
        """Build the persistence adapter for question use cases."""
        return SqlAlchemyRequirementQuestionStore(session)

    async def _mark_requirement_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published outbox event."""
        if not isinstance(self._db_manager, DatabaseManager):
            return
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "requirement_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_requirement_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an outbox event publish attempt."""
        if not isinstance(self._db_manager, DatabaseManager):
            return
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "requirement_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

    async def _delete_requirement_vector_record(self, requirement_id: str) -> None:
        """
        Best-effort cleanup for the requirement search index.

        The database is the source of truth. If vector cleanup fails, query-time
        filtering still prevents orphaned vector records from surfacing.
        """
        try:
            result = self._vector_store.delete_requirement(requirement_id)
            if inspect.isawaitable(result):
                await result
            logger.info(
                "vector_store_record_deleted",
                requirement_id=requirement_id,
            )
        except Exception as exc:
            logger.warning(
                "vector_store_delete_failed",
                requirement_id=requirement_id,
                error=str(exc),
                note="Orphaned vector record may exist, will be filtered on query",
            )

    # ========== Convenience Methods Without External Sessions ==========

    async def list_pending_requirements(
        self,
        page: int = 1,
        page_size: int = 5,
    ) -> tuple[list[dict], int, int]:
        """
        List pending requirements, creating a session internally.

        Used by the Feishu bot handler without requiring the caller to pass a session.

        Args:
            page: Page number starting from 1.
            page_size: Number of items per page.

        Returns:
            (requirements_list, total_count, total_pages)
        """
        async with self._db_manager.session() as session:
            repo = self._get_requirement_store(session)
            skip = (page - 1) * page_size
            requirements, total = await repo.list_all(
                status="PENDING",
                skip=skip,
                limit=page_size
            )

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            # Convert to dict for Feishu card
            req_list = [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority,
                    "category": r.category,
                }
                for r in requirements
            ]

            return req_list, total, total_pages

    async def get_confirmed_requirements(self) -> list[dict]:
        """
        Get all confirmed requirements for PRD export.

        Returns:
            Confirmed requirement list.
        """
        async with self._db_manager.session() as session:
            repo = self._get_requirement_store(session)
            requirements, _ = await repo.list_all(status="CONFIRMED", limit=1000)

            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "priority": r.priority,
                    "category": r.category,
                    "source_quote": r.source_quote,
                    "status": r.status,
                }
                for r in requirements
            ]

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
        async with self.get_unit_of_work() as uow:
            results, mutation_results = await self.batch_confirm_requirements_with_uow(
                requirement_ids=requirement_ids,
                confirmed_by=confirmed_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self.publish_requirement_mutation_side_effects(result)

        return results

    async def batch_confirm_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        confirmed_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Confirm requirements in one explicit unit of work."""
        results = []
        mutation_results: list[RequirementMutationResult] = []

        for req_id in requirement_ids:
            try:
                result = await self.confirm_requirement_with_uow(
                    requirement_id=req_id,
                    confirmed_by=confirmed_by,
                    uow=uow,
                )
                if result.entity:
                    mutation_results.append(result)
                    results.append({
                        "requirement_id": req_id,
                        "success": True,
                        "error": None
                    })
                    logger.info(
                        "batch_requirement_confirmed",
                        requirement_id=req_id,
                        confirmed_by=confirmed_by
                    )
                else:
                    results.append({
                        "requirement_id": req_id,
                        "success": False,
                        "error": "需求不存在或已处理"
                    })
            except Exception as e:
                results.append({
                    "requirement_id": req_id,
                    "success": False,
                    "error": str(e)
                })
                logger.error(
                    "batch_confirm_error",
                    requirement_id=req_id,
                    error=str(e)
                )

        return results, mutation_results

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
        async with self.get_unit_of_work() as uow:
            results, mutation_results = await self.batch_reject_requirements_with_uow(
                requirement_ids=requirement_ids,
                reason=reason,
                rejected_by=rejected_by,
                uow=uow,
            )
            await uow.commit()

        for result in mutation_results:
            await self.publish_requirement_mutation_side_effects(result)

        return results

    async def batch_reject_requirements_with_uow(
        self,
        *,
        requirement_ids: list[str],
        reason: str,
        rejected_by: str,
        uow: RequirementUnitOfWork,
    ) -> tuple[list[dict], list[RequirementMutationResult]]:
        """Reject requirements in one explicit unit of work."""
        results = []
        mutation_results: list[RequirementMutationResult] = []

        for req_id in requirement_ids:
            try:
                result = await self.reject_requirement_with_uow(
                    requirement_id=req_id,
                    reason=reason,
                    rejected_by=rejected_by,
                    uow=uow,
                )
                if result.entity:
                    mutation_results.append(result)
                    results.append({
                        "requirement_id": req_id,
                        "success": True,
                        "error": None
                    })
                    logger.info(
                        "batch_requirement_rejected",
                        requirement_id=req_id,
                        reason_length=len(reason or ""),
                        rejected_by_hash=hash_identifier(rejected_by),
                    )
                else:
                    results.append({
                        "requirement_id": req_id,
                        "success": False,
                        "error": "需求不存在或已处理"
                    })
            except Exception as e:
                results.append({
                    "requirement_id": req_id,
                    "success": False,
                    "error": str(e)
                })
                logger.error(
                    "batch_reject_error",
                    requirement_id=req_id,
                    error=str(e)
                )

        return results, mutation_results

    async def get_requirement(self, requirement_id: str) -> Optional[Requirement]:
        """
        Get a requirement by ID, managing the session internally.

        Args:
            requirement_id: Requirement ID.

        Returns:
            Requirement object, or None if it does not exist.
        """
        async with self._db_manager.session() as session:
            repo = self._get_requirement_store(session)
            return await repo.get_by_id(requirement_id)

    async def get_meeting(self, meeting_id: str) -> Optional[Meeting]:
        """
        Get a meeting by ID, managing the session internally.

        Args:
            meeting_id: Meeting ID.

        Returns:
            Meeting object, or None if it does not exist.
        """
        async with self._db_manager.session() as session:
            repo = self._get_meeting_store(session)
            return await repo.get_by_id(meeting_id)

    # ========== Session Extraction Methods ==========

    async def extract_from_session(self, session_id: str) -> Optional[IngestResult]:
        """
        Extract requirements from a chat session's messages.

        Called by SessionManager when session times out.

        Args:
            session_id: The session ID to extract from

        Returns:
            IngestResult if extraction succeeded, None if no messages or error
        """
        async with self.get_unit_of_work() as uow:
            # Get all messages in session
            messages = await uow.messages.get_by_session(session_id)
            if not messages:
                logger.warning("extract_from_session_no_messages", session_id=session_id)
                return None

            # Get chat_id from first message (for notifications)
            chat_id = messages[0].chat_id

            # Format messages for LLM extraction
            content = self._format_messages_for_extraction(messages)

            logger.info(
                "extract_from_session_starting",
                session_id=session_id,
                message_count=len(messages),
                content_length=len(content),
            )

            result = await self.ingest_meeting_with_uow(
                content=content,
                source="feishu_session",
                uow=uow,
                context=f"Session {session_id} from chat {chat_id} with {len(messages)} messages",
            )

            if result and result.requirements_extracted > 0:
                # Mark messages as extracted and link to requirements
                await uow.messages.mark_extracted(session_id, result.requirement_ids)

                # Get message IDs for context linking
                message_ids = [m.id for m in messages]

                # Update requirements with context_message_ids
                for req_id in result.requirement_ids:
                    req = await uow.requirements.get_by_id(req_id)
                    if req and hasattr(req, 'context_message_ids'):
                        req.context_message_ids = message_ids

            await uow.commit()
            await self.publish_ingest_side_effects(result)

            if result and result.requirements_extracted > 0:
                # Send notification card to chat
                await self._send_session_extraction_card(chat_id, result, session_id)

                logger.info(
                    "extract_from_session_complete",
                    session_id=session_id,
                    requirements_extracted=result.requirements_extracted,
                )

            return result

    def _format_messages_for_extraction(self, messages: list) -> str:
        """
        Format messages as conversation text for LLM extraction.

        Args:
            messages: List of ChatMessage objects ordered by sent_at

        Returns:
            Formatted conversation text
        """
        lines = []

        for msg in messages:
            sender = msg.sender_name or "Unknown"
            time_str = msg.sent_at.strftime("%H:%M") if msg.sent_at else "??:??"
            content = msg.content or ""

            # Skip empty content
            if not content.strip():
                continue

            lines.append(f"[{time_str}] {sender}: {content}")

        return "\n".join(lines)

    async def _send_session_extraction_card(
        self,
        chat_id: str,
        result: IngestResult,
        session_id: str,
    ):
        """
        Send extraction result card to the chat.

        Similar to existing notification but includes session context.
        """
        try:
            if self._messenger is None:
                logger.warning(
                    "session_extraction_card_skipped",
                    reason="messenger_port_not_configured",
                    chat_hash=hash_identifier(chat_id),
                    session_id=session_id,
                )
                return
            if self._card_renderer is None:
                logger.warning(
                    "session_extraction_card_skipped",
                    reason="card_renderer_not_configured",
                    chat_hash=hash_identifier(chat_id),
                    session_id=session_id,
                )
                return

            card = self._card_renderer.extraction_result_card(
                requirements=(
                    result.requirements if hasattr(result, "requirements") else []
                ),
                meeting_title=f"群聊会话 {session_id[:8]}...",
                questions_count=(
                    result.questions_generated
                    if hasattr(result, "questions_generated")
                    else 0
                ),
            )

            await self._messenger.send_card(
                receive_id=chat_id,
                receive_id_type="chat_id",
                card=card,
            )

            logger.info(
                "session_extraction_card_sent",
                chat_hash=hash_identifier(chat_id),
                session_id=session_id,
            )

        except Exception as e:
            logger.error(
                "session_extraction_card_failed",
                chat_hash=hash_identifier(chat_id),
                session_id=session_id,
                error=str(e),
            )

    # ========== Event Creation and Publishing Helpers ==========

    def _create_requirements_extracted_event(
        self,
        requirements: list[Requirement],
        meeting_id: str,
    ) -> Event:
        """Create a requirements-extracted integration event."""
        return self.create_event(
            event_type=EventTypes.REQUIREMENT_EXTRACTED,
            payload={
                "meeting_id": meeting_id,
                "requirement_ids": [r.id for r in requirements],
                "count": len(requirements),
                "requirements": [
                    {
                        "id": r.id,
                        "title": r.title,
                        "priority": r.priority,
                        "category": r.category,
                    }
                    for r in requirements
                ],
            },
        )

    def _create_requirement_confirmed_event(
        self,
        requirement: Requirement,
        confirmed_by: str,
    ) -> Event:
        """Create a requirement-confirmed integration event."""
        return self.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "priority": requirement.priority,
                "category": requirement.category,
                "confirmed_by": confirmed_by,
                "confirmed_at": datetime.now(UTC).isoformat(),
            },
        )

    def _create_requirement_rejected_event(
        self,
        requirement: Requirement,
        reason: str,
    ) -> Event:
        """Create a requirement-rejected integration event."""
        return self.create_event(
            event_type=EventTypes.REQUIREMENT_REJECTED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "reason": reason,
                "rejected_at": datetime.now(UTC).isoformat(),
            },
        )

    def _create_requirement_changed_event(
        self,
        requirement: Requirement,
        changed_fields: list[str],
        changed_by: str,
    ) -> Event:
        """Create a requirement-changed integration event."""
        return self.create_event(
            event_type=EventTypes.REQUIREMENT_CHANGED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "changed_fields": changed_fields,
                "changed_by": changed_by,
                "changed_at": datetime.now(UTC).isoformat(),
            },
        )

    def _create_requirement_deleted_event(
        self,
        requirement: Requirement,
        deleted_by: str,
    ) -> Event:
        """Create a requirement-deleted integration event."""
        return self.create_event(
            event_type=EventTypes.REQUIREMENT_DELETED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "deleted_by": deleted_by,
                "deleted_at": datetime.now(UTC).isoformat(),
            },
        )

    async def _publish_staged_requirement_event(
        self,
        event: Event,
        *,
        requirement_id: str | None = None,
    ) -> None:
        """Publish an event already persisted in the Requirement outbox."""
        try:
            ok = await self._event_publisher.publish(event)
            if not ok:
                raise RuntimeError("event_bus_publish_returned_false")
            await self._mark_requirement_event_published(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement_id,
            )
        except Exception as exc:
            await self._mark_requirement_event_failed(event, exc)
            logger.error(
                "event_publish_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement_id,
                error=str(exc),
            )


# Global Agent singleton.
agent = RequirementManagerAgent()


def get_agent() -> RequirementManagerAgent:
    """Get the current Agent instance; tests can replace it."""
    return agent
