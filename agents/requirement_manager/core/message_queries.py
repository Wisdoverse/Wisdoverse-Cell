"""Application query use cases for message read models."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MessageView:
    """Read model exposed by the message query use case."""

    id: str
    chat_id: str
    message_id: str
    sender_id: str
    sender_name: str
    message_type: str
    content: str
    session_id: str | None
    extracted: bool
    requirement_ids: list[str] | None
    sent_at: datetime | None
    created_at: datetime | None

    @classmethod
    def from_row(cls, row: object) -> "MessageView":
        return cls(
            id=row.id,
            chat_id=row.chat_id,
            message_id=row.message_id,
            sender_id=row.sender_id,
            sender_name=row.sender_name,
            message_type=row.message_type,
            content=row.content,
            session_id=row.session_id,
            extracted=row.extracted,
            requirement_ids=list(row.requirement_ids or []),
            sent_at=row.sent_at,
            created_at=row.created_at,
        )


@dataclass(frozen=True, slots=True)
class MessageSearchResult:
    """Paginated message search read model."""

    messages: list[MessageView]
    total: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class SessionMessagesResult:
    """Session message read model with derived session metadata."""

    session_id: str
    chat_id: str
    messages: list[MessageView]
    message_count: int
    started_at: datetime | None
    ended_at: datetime | None
    extracted: bool
    requirement_ids: list[str]


class MessageQueryRepository(Protocol):
    async def search(
        self,
        keyword: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[object], int]:
        """Search persisted messages and return rows with total count."""

    async def get_by_session(self, session_id: str) -> Sequence[object]:
        """Return persisted messages for one session."""


class MessageQueryService:
    """Application use case for querying message read models."""

    def __init__(self, repository: MessageQueryRepository):
        self._repository = repository

    async def search_messages(
        self,
        *,
        chat_id: str | None = None,
        keyword: str | None = None,
        sender_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> MessageSearchResult:
        rows, total = await self._repository.search(
            keyword=keyword,
            chat_id=chat_id,
            sender_id=sender_id,
            start_time=start_time,
            end_time=end_time,
            page=page,
            page_size=page_size,
        )
        return MessageSearchResult(
            messages=[MessageView.from_row(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )

    async def get_session_messages(
        self,
        session_id: str,
    ) -> SessionMessagesResult | None:
        rows = await self._repository.get_by_session(session_id)
        if not rows:
            return None

        messages = [MessageView.from_row(row) for row in rows]
        first_message = messages[0]
        last_message = messages[-1]
        requirement_ids: set[str] = set()
        for message in messages:
            if message.requirement_ids:
                requirement_ids.update(message.requirement_ids)

        return SessionMessagesResult(
            session_id=session_id,
            chat_id=first_message.chat_id,
            messages=messages,
            message_count=len(messages),
            started_at=first_message.sent_at,
            ended_at=last_message.sent_at,
            extracted=any(message.extracted for message in messages),
            requirement_ids=list(requirement_ids),
        )
