"""
Repository data-access layer.
"""
from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..models.feedback import FeedbackRecord

from sqlalchemy import Integer, and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..core.requirement_lifecycle import mark_confirmed, mark_rejected
from ..models import LLMUsage, Meeting, OpenQuestion, Requirement, RequirementEventOutbox
from ..models.chat_message import ChatMessage

logger = get_logger("repository")


class MeetingRepository:
    """Meeting record data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, meeting: Meeting) -> Meeting:
        """Create a meeting record."""
        self.session.add(meeting)
        await self.session.flush()
        return meeting

    async def get_by_id(self, meeting_id: str) -> Optional[Meeting]:
        """Get a meeting by ID."""
        result = await self.session.execute(
            select(Meeting).where(Meeting.id == meeting_id)
        )
        return result.scalar_one_or_none()

    async def get_by_source_id(self, source: str, source_id: str) -> Optional[Meeting]:
        """Get a meeting by source-system ID for deduplication."""
        result = await self.session.execute(
            select(Meeting).where(
                Meeting.source == source,
                Meeting.source_id == source_id
            )
        )
        return result.scalar_one_or_none()

    async def list_unprocessed(self, limit: int = 100) -> list[Meeting]:
        """List unprocessed meetings."""
        result = await self.session.execute(
            select(Meeting)
            .where(Meeting.processed.is_(False))
            .order_by(Meeting.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        source: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[list[Meeting], int]:
        """List meetings."""
        query = select(Meeting)

        if source:
            query = query.where(Meeting.source == source)

        # Get total count.
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar()

        # Get paginated rows.
        result = await self.session.execute(
            query.order_by(Meeting.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def mark_processed(self, meeting_id: str):
        """Mark a meeting as processed."""
        await self.session.execute(
            update(Meeting)
            .where(Meeting.id == meeting_id)
            .values(processed=True, processed_at=datetime.now(UTC))
        )


class RequirementRepository:
    """Requirement data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, requirement: Requirement) -> Requirement:
        """Create a requirement."""
        self.session.add(requirement)
        await self.session.flush()
        return requirement

    async def create_batch(self, requirements: list[Requirement]) -> list[Requirement]:
        """Create requirements in a batch."""
        self.session.add_all(requirements)
        await self.session.flush()
        return requirements

    async def get_by_id(self, requirement_id: str) -> Optional[Requirement]:
        """Get a requirement by ID, including related questions."""
        result = await self.session.execute(
            select(Requirement)
            .options(selectinload(Requirement.open_questions))
            .where(Requirement.id == requirement_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[list[Requirement], int]:
        """List requirements."""
        query = select(Requirement).options(selectinload(Requirement.open_questions))

        if status:
            query = query.where(Requirement.status == status)
        if category:
            query = query.where(Requirement.category == category)
        if priority:
            query = query.where(Requirement.priority == priority)

        # Get total count.
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_query)).scalar()

        # Get paginated rows.
        result = await self.session.execute(
            query.order_by(Requirement.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update(
        self,
        requirement_id: str,
        **kwargs
    ) -> Optional[Requirement]:
        """Update a requirement."""
        await self.session.execute(
            update(Requirement)
            .where(Requirement.id == requirement_id)
            .values(**kwargs, updated_at=datetime.now(UTC))
        )
        return await self.get_by_id(requirement_id)

    async def confirm(
        self,
        requirement_id: str,
        confirmed_by: str
    ) -> Optional[Requirement]:
        """Confirm a requirement."""
        requirement = await self.get_by_id(requirement_id)
        if requirement:
            mark_confirmed(requirement, confirmed_by)
            await self.session.flush()
        return requirement

    async def reject(
        self,
        requirement_id: str,
        reason: str,
        rejected_by: str
    ) -> Optional[Requirement]:
        """Reject a requirement."""
        requirement = await self.get_by_id(requirement_id)
        if requirement:
            mark_rejected(requirement, reason, rejected_by)
            await self.session.flush()
        return requirement

    async def get_by_meeting_id(self, meeting_id: str) -> list[Requirement]:
        """Get requirements related to a meeting."""
        result = await self.session.execute(
            select(Requirement)
            .where(Requirement.source_meeting_ids.contains([meeting_id]))
        )
        return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        """Count requirements by status."""
        result = await self.session.execute(
            select(Requirement.status, func.count())
            .group_by(Requirement.status)
        )
        return {status: count for status, count in result.all()}

    async def count_by_priority(self) -> dict[str, int]:
        """Count requirements by priority."""
        result = await self.session.execute(
            select(Requirement.priority, func.count())
            .group_by(Requirement.priority)
        )
        return {priority: count for priority, count in result.all()}

    async def count_by_category(self) -> dict[str, int]:
        """Count requirements by category."""
        result = await self.session.execute(
            select(Requirement.category, func.count())
            .group_by(Requirement.category)
        )
        return {category: count for category, count in result.all()}

    async def get_daily_counts(self, days: int = 7) -> list[dict]:
        """Get daily new-requirement counts."""
        from datetime import timedelta

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=days - 1)

        result = await self.session.execute(
            select(
                func.date(Requirement.created_at).label('date'),
                func.count().label('count')
            )
            .where(func.date(Requirement.created_at) >= start_date)
            .group_by(func.date(Requirement.created_at))
            .order_by(func.date(Requirement.created_at))
        )

        # Build a date-to-count map.
        counts_map = {str(row.date): row.count for row in result.all()}

        # Fill all dates in the requested range.
        trend = []
        current = start_date
        while current <= end_date:
            trend.append({
                'date': current.strftime('%m/%d'),
                'count': counts_map.get(str(current), 0)
            })
            current += timedelta(days=1)

        return trend

    async def count_today(self) -> int:
        """Count requirements created today."""
        today = datetime.now(UTC).date()
        result = await self.session.execute(
            select(func.count())
            .where(func.date(Requirement.created_at) == today)
        )
        return result.scalar() or 0

    async def delete(self, requirement_id: str) -> Optional[Requirement]:
        """
        Delete a requirement and its related database records.

        Args:
            requirement_id: Requirement ID.

        Returns:
            Deleted requirement object, or None if it does not exist.
        """
        # 1. Load the requirement for return value and logging.
        requirement = await self.get_by_id(requirement_id)
        if not requirement:
            return None

        # 2. Delete related OpenQuestion records.
        await self.session.execute(
            delete(OpenQuestion).where(OpenQuestion.requirement_id == requirement_id)
        )

        # 3. Delete the Requirement record.
        await self.session.execute(
            delete(Requirement).where(Requirement.id == requirement_id)
        )

        logger.info(
            "requirement_deleted_from_db",
            requirement_id=requirement_id,
            title_hash=hash_identifier(requirement.title),
        )

        return requirement


class QuestionRepository:
    """Open question data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, question: OpenQuestion) -> OpenQuestion:
        """Create a question."""
        self.session.add(question)
        await self.session.flush()
        return question

    async def create_batch(self, questions: list[OpenQuestion]) -> list[OpenQuestion]:
        """Create questions in a batch."""
        self.session.add_all(questions)
        await self.session.flush()
        return questions

    async def get_by_id(self, question_id: str) -> Optional[OpenQuestion]:
        """Get a question by ID."""
        result = await self.session.execute(
            select(OpenQuestion).where(OpenQuestion.id == question_id)
        )
        return result.scalar_one_or_none()

    async def list_open(self, limit: int = 50) -> list[OpenQuestion]:
        """List unanswered questions."""
        result = await self.session.execute(
            select(OpenQuestion)
            .where(OpenQuestion.status == "open")
            .order_by(OpenQuestion.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_answered(self, limit: int = 50) -> list[OpenQuestion]:
        """List answered clarification questions."""
        result = await self.session.execute(
            select(OpenQuestion)
            .where(OpenQuestion.status == "answered")
            .order_by(OpenQuestion.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all(self, limit: int = 50) -> list[OpenQuestion]:
        """List all clarification questions."""
        result = await self.session.execute(
            select(OpenQuestion)
            .where(OpenQuestion.status.in_(["open", "answered"]))
            .order_by(OpenQuestion.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def answer(
        self,
        question_id: str,
        answer: str,
        answered_by: str
    ) -> Optional[OpenQuestion]:
        """Answer a question."""
        question = await self.get_by_id(question_id)
        if question:
            question.status = "answered"
            question.answer = answer
            question.answered_by = answered_by
            question.answered_at = datetime.now(UTC)
            await self.session.flush()
        return question


class RequirementEventOutboxRepository:
    """Requirement integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> RequirementEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = RequirementEventOutbox(
            event_id=event.event_id,
            event_type=event.event_type,
            source_agent=event.source_agent,
            payload=payload["payload"],
            schema_version=event.schema_version,
            trace_id=payload["metadata"].get("trace_id"),
            correlation_id=payload["metadata"].get("correlation_id"),
            retry_count=payload["metadata"].get("retry_count", 0),
            status="pending",
            attempts=0,
        )
        self.session.add(row)
        result = self.session.flush()
        if inspect.isawaitable(result):
            await result
        return row

    async def list_pending(self, limit: int = 100) -> list[RequirementEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(RequirementEventOutbox)
            .where(RequirementEventOutbox.status == "pending")
            .order_by(RequirementEventOutbox.created_at, RequirementEventOutbox.event_id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(RequirementEventOutbox)
            .where(RequirementEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=RequirementEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(RequirementEventOutbox)
            .where(RequirementEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=RequirementEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )


class LLMUsageRepository:
    """
    LLM usage record data access.

    Provides CRUD operations and statistical queries for LLM call records.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, usage: LLMUsage) -> LLMUsage:
        """Create a usage record."""
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def get_daily_summary(
        self,
        date: str,
        agent_id: Optional[str] = None
    ) -> dict:
        """
        Get usage summary for one day.

        Args:
            date: Date string (YYYY-MM-DD).
            agent_id: Optional Agent ID filter.

        Returns:
            Dictionary containing summary statistics.
        """
        # Parse date range.
        start_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        end_date = start_date.replace(hour=23, minute=59, second=59)

        # Base query conditions.
        base_condition = [
            LLMUsage.created_at >= start_date,
            LLMUsage.created_at <= end_date
        ]

        if agent_id:
            base_condition.append(LLMUsage.agent_id == agent_id)

        # Overall statistics.
        total_query = select(
            func.count().label("total_calls"),
            func.sum(func.cast(LLMUsage.success, Integer)).label("success_calls"),
            func.sum(LLMUsage.input_tokens).label("total_input_tokens"),
            func.sum(LLMUsage.output_tokens).label("total_output_tokens"),
            func.sum(LLMUsage.cost_usd).label("total_cost_usd"),
            func.avg(LLMUsage.latency_ms).label("avg_latency_ms")
        ).where(*base_condition)

        result = await self.session.execute(total_query)
        row = result.one()

        total_calls = row.total_calls or 0
        success_calls = int(row.success_calls or 0)

        summary = {
            "date": date,
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": total_calls - success_calls,
            "total_input_tokens": int(row.total_input_tokens or 0),
            "total_output_tokens": int(row.total_output_tokens or 0),
            "total_cost_usd": round(float(row.total_cost_usd or 0), 6),
            "avg_latency_ms": int(row.avg_latency_ms or 0),
            "by_agent": {},
            "by_task_type": {}
        }

        # Group statistics by Agent.
        agent_query = select(
            LLMUsage.agent_id,
            func.count().label("calls"),
            func.sum(LLMUsage.cost_usd).label("cost_usd"),
            func.sum(LLMUsage.input_tokens).label("input_tokens"),
            func.sum(LLMUsage.output_tokens).label("output_tokens")
        ).where(*base_condition).group_by(LLMUsage.agent_id)

        agent_result = await self.session.execute(agent_query)
        for row in agent_result.all():
            summary["by_agent"][row.agent_id] = {
                "calls": row.calls,
                "cost_usd": round(float(row.cost_usd or 0), 6),
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0)
            }

        # Group statistics by task type.
        task_query = select(
            LLMUsage.task_type,
            func.count().label("calls"),
            func.sum(LLMUsage.cost_usd).label("cost_usd")
        ).where(*base_condition).group_by(LLMUsage.task_type)

        task_result = await self.session.execute(task_query)
        for row in task_result.all():
            summary["by_task_type"][row.task_type] = {
                "calls": row.calls,
                "cost_usd": round(float(row.cost_usd or 0), 6)
            }

        return summary

    async def get_usage_by_agent(
        self,
        agent_id: str,
        start_date: str,
        end_date: str
    ) -> list[LLMUsage]:
        """
        Get call records for an Agent during a date range.

        Args:
            agent_id: Agent ID
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            List of LLMUsage records.
        """
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )

        result = await self.session.execute(
            select(LLMUsage)
            .where(
                LLMUsage.agent_id == agent_id,
                LLMUsage.created_at >= start,
                LLMUsage.created_at <= end
            )
            .order_by(LLMUsage.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_recent_failures(self, limit: int = 20) -> list[LLMUsage]:
        """Get recent failed usage records."""
        result = await self.session.execute(
            select(LLMUsage)
            .where(LLMUsage.success.is_(False))
            .order_by(LLMUsage.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class MessageRepository:
    """Message data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, message: ChatMessage) -> ChatMessage:
        """Insert new message"""
        self.session.add(message)
        await self.session.flush()
        await self.session.refresh(message)
        return message

    async def get_by_id(self, message_id: str) -> Optional[ChatMessage]:
        """Get by internal ID"""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_by_feishu_message_id(self, feishu_message_id: str) -> Optional[ChatMessage]:
        """Get by Feishu message_id (for dedup check)"""
        result = await self.session.execute(
            select(ChatMessage).where(ChatMessage.message_id == feishu_message_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self,
        keyword: Optional[str] = None,
        chat_id: Optional[str] = None,
        sender_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ChatMessage], int]:
        """Search messages with PostgreSQL full-text search"""
        query = select(ChatMessage)
        count_query = select(func.count()).select_from(ChatMessage)

        conditions = []

        if keyword:
            # PostgreSQL full-text search using 'simple' configuration for Chinese
            ts_query = func.plainto_tsquery('simple', keyword)
            ts_vector = func.to_tsvector('simple', ChatMessage.content)
            conditions.append(ts_vector.op('@@')(ts_query))

        if chat_id:
            conditions.append(ChatMessage.chat_id == chat_id)

        if sender_id:
            conditions.append(ChatMessage.sender_id == sender_id)

        if start_time:
            conditions.append(ChatMessage.sent_at >= start_time)

        if end_time:
            conditions.append(ChatMessage.sent_at <= end_time)

        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))

        # Get total count
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(ChatMessage.sent_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_by_session(self, session_id: str) -> list[ChatMessage]:
        """Get all messages in a session, ordered by sent_at ASC"""
        result = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.sent_at.asc())
        )
        return list(result.scalars().all())

    async def count_by_session(self, session_id: str) -> int:
        """Count messages in a session"""
        result = await self.session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session_id)
        )
        return result.scalar() or 0

    async def mark_extracted(self, session_id: str, requirement_ids: list[str]) -> int:
        """Mark session messages as extracted and link to requirements"""
        result = await self.session.execute(
            update(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .values(extracted=True, requirement_ids=requirement_ids)
        )
        return result.rowcount


class FeedbackRepository:
    """
    Feedback record data access layer.

    Manages user corrections/feedback for learning.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, feedback: "FeedbackRecord") -> "FeedbackRecord":
        """Create a feedback record."""
        self.session.add(feedback)
        await self.session.flush()
        return feedback

    async def get_by_id(self, feedback_id: str) -> Optional["FeedbackRecord"]:
        """Get feedback by ID."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel).where(FeedbackModel.id == feedback_id)
        )
        return result.scalar_one_or_none()

    async def list_by_requirement(self, requirement_id: str) -> list["FeedbackRecord"]:
        """Get all feedback for a requirement."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel)
            .where(FeedbackModel.requirement_id == requirement_id)
            .order_by(FeedbackModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_recent(
        self,
        limit: int = 20,
        feedback_type: Optional[str] = None,
        unused_only: bool = False,
    ) -> list["FeedbackRecord"]:
        """
        Get recent feedback records for prompt examples.

        Args:
            limit: Maximum number of records
            feedback_type: Filter by type (correction, rejection, merge)
            unused_only: Only get records not yet used in prompts

        Returns:
            List of FeedbackRecord
        """
        from ..models import FeedbackRecord as FeedbackModel
        query = select(FeedbackModel)

        if feedback_type:
            query = query.where(FeedbackModel.feedback_type == feedback_type)

        if unused_only:
            query = query.where(FeedbackModel.used_in_prompt.is_(False))

        query = query.order_by(FeedbackModel.created_at.desc()).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_examples_for_prompt(self, limit: int = 5) -> list[dict]:
        """
        Get feedback examples formatted for LLM prompt.

        Returns the most recent corrections as examples to include
        in the extraction prompt for few-shot learning.
        """
        records = await self.list_recent(limit=limit, feedback_type="correction")
        return [r.to_example() for r in records]

    async def mark_used(self, feedback_ids: list[str]) -> int:
        """Mark feedback records as used in prompt."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            update(FeedbackModel)
            .where(FeedbackModel.id.in_(feedback_ids))
            .values(used_in_prompt=True)
        )
        return result.rowcount

    async def count_by_type(self) -> dict[str, int]:
        """Count feedback records by type."""
        from ..models import FeedbackRecord as FeedbackModel
        result = await self.session.execute(
            select(FeedbackModel.feedback_type, func.count())
            .group_by(FeedbackModel.feedback_type)
        )
        return {ftype: count for ftype, count in result.all()}
