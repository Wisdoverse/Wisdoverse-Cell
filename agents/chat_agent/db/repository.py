"""Repository - chat_agent"""
import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..core.domain.card_operation import CardOperationLogEntry
from ..core.domain.conversation import ConversationTranscript
from ..core.domain.daily_progress import DailyProgressEntry
from ..models.card_operation import CardOperation
from ..models.conversation import ConversationHistory
from ..models.daily_progress import DailyProgress
from ..models.event_outbox import ChatAgentEventOutbox

logger = get_logger("chat_agent.repository")

# Max serialized conversation size (512 KB)
MAX_CONVERSATION_BYTES = 512 * 1024


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(self, user_id: str) -> Optional[list[dict]]:
        result = await self.session.execute(
            select(ConversationHistory).where(ConversationHistory.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv and conv.messages:
            return json.loads(conv.messages)
        return None

    async def save(self, user_id: str, messages: list[dict]) -> None:
        transcript = ConversationTranscript(
            user_id=user_id,
            messages=messages,
        ).trim_to_serialized_size(MAX_CONVERSATION_BYTES)
        messages = transcript.messages
        serialized = json.dumps(messages, ensure_ascii=False)
        for event in transcript.pull_events():
            logger.warning(
                "conversation_trimmed",
                user_hash=hash_identifier(user_id),
                reason=event.reason,
                removed=event.removed_count,
                remaining=event.remaining_count,
            )

        stmt = pg_insert(ConversationHistory).values(
            user_id=user_id,
            messages=serialized,
            updated_at=datetime.now(UTC),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "messages": stmt.excluded.messages,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def clear(self, user_id: str) -> None:
        result = await self.session.execute(
            select(ConversationHistory).where(ConversationHistory.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            await self.session.delete(conv)
            await self.session.flush()

    async def delete_inactive(self, days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self.session.execute(
            delete(ConversationHistory).where(
                ConversationHistory.updated_at < cutoff
            )
        )
        await self.session.flush()
        return result.rowcount


class CardOperationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        entry: CardOperationLogEntry,
    ) -> CardOperation:
        op = CardOperation(
            user_id=entry.user_id,
            user_name=entry.user_name,
            action=entry.action,
            table_id=entry.table_id,
            record_id=entry.record_id,
            assignee_name=entry.assignee_name,
            fields_snapshot=entry.fields_snapshot,
            result=entry.result.value,
            error_message=entry.error_message,
        )
        self.session.add(op)
        await self.session.flush()
        return op

    async def query(
        self,
        user_id: str = "",
        action: str = "",
        limit: int = 20,
    ) -> list[CardOperation]:
        stmt = select(CardOperation).order_by(CardOperation.created_at.desc())
        if user_id:
            stmt = stmt.where(CardOperation.user_id == user_id)
        if action:
            stmt = stmt.where(CardOperation.action == action)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DailyProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_batch(self, items: list[dict]) -> list[DailyProgress]:
        records = []
        for item in items:
            aggregate = DailyProgressEntry(
                progress_id=item.get("id"),
                user_id=item.get("user_id", ""),
                task_record_id=item.get("task_record_id", ""),
                task_title=item.get("task_title", ""),
                status=item.get("status", "pending"),
                raw_reply=item.get("raw_reply", ""),
                note=item.get("note", ""),
            )
            dp = DailyProgress(
                **{
                    **item,
                    "status": aggregate.status.value,
                    "raw_reply": aggregate.raw_reply,
                    "note": aggregate.note,
                }
            )
            self.session.add(dp)
            records.append(dp)
        await self.session.flush()
        return records

    async def get_pending(self, user_id: str, target_date) -> list[DailyProgress]:
        stmt = (
            select(DailyProgress)
            .where(DailyProgress.user_id == user_id, DailyProgress.date == target_date)
            .order_by(DailyProgress.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_progress(
        self, progress_id: int, status: str, raw_reply: str = "", note: str = "",
    ) -> DailyProgress | None:
        stmt = select(DailyProgress).where(DailyProgress.id == progress_id)
        result = await self.session.execute(stmt)
        dp = result.scalar_one_or_none()
        if dp:
            aggregate = DailyProgressEntry(
                progress_id=dp.id,
                user_id=dp.user_id,
                task_record_id=dp.task_record_id,
                task_title=dp.task_title,
                status=dp.status,
                raw_reply=dp.raw_reply or "",
                note=dp.note or "",
            )
            aggregate.record_update(status, raw_reply=raw_reply, note=note)
            dp.status = aggregate.status.value
            dp.raw_reply = aggregate.raw_reply
            dp.note = aggregate.note
            for event in aggregate.pull_events():
                logger.info(
                    "daily_progress_status_changed",
                    progress_id=event.progress_id,
                    user_hash=hash_identifier(event.user_id),
                    task_record_hash=hash_identifier(event.task_record_id),
                    from_status=event.from_status.value,
                    to_status=event.to_status.value,
                )
            await self.session.flush()
        return dp

    async def get_by_date_range(
        self, start_date, end_date, user_id: str = "",
    ) -> list[DailyProgress]:
        stmt = (
            select(DailyProgress)
            .where(DailyProgress.date >= start_date, DailyProgress.date <= end_date)
            .order_by(DailyProgress.date.desc(), DailyProgress.user_name)
        )
        if user_id:
            stmt = stmt.where(DailyProgress.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ChatAgentEventOutboxRepository:
    """Chat-agent integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> ChatAgentEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = ChatAgentEventOutbox(
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
        add_result = self.session.add(row)
        if inspect.isawaitable(add_result):
            await add_result
        flush_result = self.session.flush()
        if inspect.isawaitable(flush_result):
            await flush_result
        return row

    async def list_pending(self, limit: int = 100) -> list[ChatAgentEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(ChatAgentEventOutbox)
            .where(ChatAgentEventOutbox.status == "pending")
            .order_by(
                ChatAgentEventOutbox.created_at,
                ChatAgentEventOutbox.event_id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(ChatAgentEventOutbox)
            .where(ChatAgentEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=ChatAgentEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(ChatAgentEventOutbox)
            .where(ChatAgentEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=ChatAgentEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
