"""
RequirementManagerAgent core.

Inherits BaseAgent and implements the standard Agent interface. All business
logic is coordinated through this class; FastAPI is only the HTTP adapter.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings as app_settings
from shared.core import FeishuMessengerPort
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.notification import NotificationChannel, notification_service
from shared.observability.privacy import hash_identifier
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.card_ports import RequirementCardRendererPort
from ..core.extractor import extractor
from ..db.database import DatabaseManager, db_manager
from ..db.repository import (
    MeetingRepository,
    MessageRepository,
    QuestionRepository,
    RequirementRepository,
)
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
        vectors: Optional[VectorStore] = None,
        messenger: Optional[FeishuMessengerPort] = None,
        card_renderer: Optional[RequirementCardRendererPort] = None,
    ):
        # Import subscribed event list.
        from .event_handlers import SUBSCRIBED_EVENTS

        super().__init__(
            agent_id="requirement-manager",
            agent_name="Requirement Manager",
            subscribed_events=SUBSCRIBED_EVENTS,
            published_events=[
                EventTypes.REQUIREMENT_EXTRACTED,
                EventTypes.REQUIREMENT_CONFIRMED,
                EventTypes.REQUIREMENT_REJECTED,
                EventTypes.REQUIREMENT_DELETED,
            ]
        )
        # Dependency injection supports replacement during tests.
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._vector_store = vectors or vector_store
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

        Delegates handling to the event_handlers module.
        """
        from .event_handlers import dispatch_event
        return await dispatch_event(self, event)

    async def handle_request(self, request: dict) -> dict:
        """
        Handle an API request.

        This method is reserved for future extensions. Current FastAPI routes
        call business methods directly.
        """
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "ingest":
            content = request.get("content")
            if not isinstance(content, str) or not content.strip():
                return {"status": "error", "error": "content_required"}

            try:
                meeting_date = self._parse_meeting_date(request.get("meeting_date"))
            except ValueError as exc:
                return {"status": "error", "error": str(exc)}

            async with self._db_manager.session() as session:
                result = await self.ingest_meeting(
                    content=content,
                    source=str(request.get("source") or "agent_request"),
                    session=session,
                    title=self._optional_str(request.get("title")),
                    meeting_date=meeting_date,
                    participants=self._string_list(request.get("participants")),
                    context=self._optional_str(request.get("context")),
                    source_id=self._optional_str(request.get("source_id")),
                )

            return {
                "status": "ok",
                "meeting_id": result.meeting_id,
                "requirements_extracted": result.requirements_extracted,
                "questions_generated": result.questions_generated,
                "requirement_ids": result.requirement_ids,
            }
        return {"status": "ok"}

    async def health_check(self) -> dict[str, bool]:
        """Return readiness checks for the requirement manager runtime boundary."""
        checks = {
            "database": False,
            "event_bus": bool(getattr(self._event_bus, "is_connected", False)),
            "messenger": self._messenger is not None,
            "card_renderer": self._card_renderer is not None,
        }
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

    def _parse_meeting_date(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise ValueError("meeting_date_must_be_iso_datetime")
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("meeting_date_must_be_iso_datetime") from exc
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _optional_str(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        return [str(value)]

    # ========== Business Methods ==========

    async def ingest_meeting(
        self,
        content: str,
        source: str,
        session: AsyncSession,
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
            session: Database session.
            title: Meeting title.
            meeting_date: Meeting date.
            participants: Participant list.
            context: Additional context.
            source_id: Source-system ID for deduplication.

        Returns:
            IngestResult with extracted requirement and question counts.
        """
        meeting_repo = MeetingRepository(session)
        requirement_repo = RequirementRepository(session)
        question_repo = QuestionRepository(session)

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
        await meeting_repo.create(meeting)

        logger.info(
            "meeting_created",
            meeting_id=meeting.id,
            source=source,
            content_length=len(content)
        )

        # Extract requirements.
        result = await extractor.extract(
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
            await requirement_repo.create_batch(requirements)

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
            await question_repo.create_batch(questions)

        # Mark meeting as processed.
        await meeting_repo.mark_processed(meeting.id)

        # Publish event.
        await self._publish_requirements_extracted(
            requirements=requirements,
            meeting_id=meeting.id
        )

        # Send notification; non-critical failure does not block the main flow.
        if requirements:
            try:
                await notification_service.send(
                    channel=NotificationChannel.FEISHU,
                    title="新需求待确认",
                    content=(
                        f"从会议中提取了 {len(requirements)} 个新需求，"
                        f"{len(questions)} 个待确认问题。"
                    )
                )
            except Exception as e:
                logger.warning(
                    "notification_send_failed",
                    meeting_id=meeting.id,
                    error=str(e),
                )

        return IngestResult(
            meeting_id=meeting.id,
            requirements_extracted=len(requirements),
            questions_generated=len(questions),
            requirement_ids=[r.id for r in requirements]
        )

    async def confirm_requirement(
        self,
        requirement_id: str,
        confirmed_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        Confirm a requirement.

        Args:
            requirement_id: Requirement ID.
            confirmed_by: Confirmer.
            session: Database session.

        Returns:
            Confirmed requirement, or None if it does not exist.
        """
        repo = RequirementRepository(session)
        requirement = await repo.confirm(requirement_id, confirmed_by)

        if not requirement:
            return None

        logger.info(
            "requirement_confirmed",
            requirement_id=requirement_id,
            confirmed_by=confirmed_by
        )

        # Publish event.
        await self._publish_requirement_confirmed(requirement, confirmed_by)

        return requirement

    async def reject_requirement(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        Reject a requirement.

        Args:
            requirement_id: Requirement ID.
            reason: Rejection reason.
            rejected_by: Rejecting user.
            session: Database session.

        Returns:
            Rejected requirement, or None if it does not exist.
        """
        from .feedback_learning import FeedbackLearningService

        repo = RequirementRepository(session)

        # Load the original requirement for feedback learning.
        original_req = await repo.get_by_id(requirement_id)
        if not original_req:
            return None

        original_values = {
            "title": original_req.title,
            "description": original_req.description,
            "priority": original_req.priority,
            "category": original_req.category,
        }

        requirement = await repo.reject(requirement_id, reason=reason, rejected_by=rejected_by)

        if not requirement:
            return None

        logger.info(
            "requirement_rejected",
            requirement_id=requirement_id,
            reason_length=len(reason or ""),
            rejected_by_hash=hash_identifier(rejected_by),
        )

        # Record rejection feedback for learning; failure does not block the main flow.
        try:
            feedback_service = FeedbackLearningService(session)
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

        # Publish event.
        await self._publish_requirement_rejected(requirement, reason)

        return requirement

    async def delete_requirement(
        self,
        requirement_id: str,
        deleted_by: str,
        session: AsyncSession,
    ) -> Optional[Requirement]:
        """
        Delete a requirement.

        Also deletes the vector-store record and publishes an event.

        Args:
            requirement_id: Requirement ID.
            deleted_by: Deleting user.
            session: Database session.

        Returns:
            Deleted requirement, or None if it does not exist.
        """
        repo = RequirementRepository(session)
        requirement = await repo.delete(requirement_id)

        if not requirement:
            return None

        logger.info(
            "requirement_deleted",
            requirement_id=requirement_id,
            title_hash=hash_identifier(requirement.title),
            deleted_by_hash=hash_identifier(deleted_by),
        )

        # Publish event.
        await self._publish_requirement_deleted(requirement, deleted_by)

        return requirement

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
            repo = RequirementRepository(session)
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
            repo = RequirementRepository(session)
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
        results = []
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)

            for req_id in requirement_ids:
                try:
                    requirement = await repo.confirm(req_id, confirmed_by)
                    if requirement:
                        # Publish event.
                        await self._publish_requirement_confirmed(requirement, confirmed_by)
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

        return results

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
        results = []
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)

            for req_id in requirement_ids:
                try:
                    requirement = await repo.reject(req_id, reason=reason, rejected_by=rejected_by)
                    if requirement:
                        # Publish event.
                        await self._publish_requirement_rejected(requirement, reason)
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

        return results

    async def get_requirement(self, requirement_id: str) -> Optional[Requirement]:
        """
        Get a requirement by ID, managing the session internally.

        Args:
            requirement_id: Requirement ID.

        Returns:
            Requirement object, or None if it does not exist.
        """
        async with self._db_manager.session() as session:
            repo = RequirementRepository(session)
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
            repo = MeetingRepository(session)
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
        async with self._db_manager.session() as db_session:
            msg_repo = MessageRepository(db_session)
            req_repo = RequirementRepository(db_session)

            # Get all messages in session
            messages = await msg_repo.get_by_session(session_id)
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

            # Call existing extraction logic via ingest_meeting
            result = await self.ingest_meeting(
                content=content,
                source="feishu_session",
                session=db_session,
                context=f"Session {session_id} from chat {chat_id} with {len(messages)} messages",
            )

            if result and result.requirements_extracted > 0:
                # Mark messages as extracted and link to requirements
                await msg_repo.mark_extracted(session_id, result.requirement_ids)

                # Get message IDs for context linking
                message_ids = [m.id for m in messages]

                # Update requirements with context_message_ids
                for req_id in result.requirement_ids:
                    req = await req_repo.get_by_id(req_id)
                    if req and hasattr(req, 'context_message_ids'):
                        req.context_message_ids = message_ids

                await db_session.commit()

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

    # ========== Event Publishing Helpers ==========

    async def _publish_requirements_extracted(
        self,
        requirements: list[Requirement],
        meeting_id: str
    ):
        """Publish a requirements-extracted event."""
        if not requirements:
            return

        # Publish aggregate event for all requirements extracted from one meeting.
        event = self.create_event(
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
                ]
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_count=len(requirements)
            )
        except Exception as e:
            # Event publishing failure does not block the main flow.
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_EXTRACTED,
                error=str(e)
            )

    async def _publish_requirement_confirmed(
        self,
        requirement: Requirement,
        confirmed_by: str
    ):
        """Publish a requirement-confirmed event."""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "priority": requirement.priority,
                "category": requirement.category,
                "confirmed_by": confirmed_by,
                "confirmed_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_CONFIRMED,
                error=str(e)
            )

    async def _publish_requirement_rejected(
        self,
        requirement: Requirement,
        reason: str
    ):
        """Publish a requirement-rejected event."""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_REJECTED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "reason": reason,
                "rejected_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_REJECTED,
                error=str(e)
            )

    async def _publish_requirement_deleted(
        self,
        requirement: Requirement,
        deleted_by: str
    ):
        """Publish a requirement-deleted event."""
        event = self.create_event(
            event_type=EventTypes.REQUIREMENT_DELETED,
            payload={
                "requirement_id": requirement.id,
                "title": requirement.title,
                "deleted_by": deleted_by,
                "deleted_at": datetime.now(UTC).isoformat()
            }
        )

        try:
            await self._event_bus.publish(event)
            logger.info(
                "event_published",
                event_id=event.event_id,
                event_type=event.event_type,
                requirement_id=requirement.id
            )
        except Exception as e:
            logger.error(
                "event_publish_failed",
                event_type=EventTypes.REQUIREMENT_DELETED,
                error=str(e)
            )


# Global Agent singleton.
agent = RequirementManagerAgent()


def get_agent() -> RequirementManagerAgent:
    """Get the current Agent instance; tests can replace it."""
    return agent
