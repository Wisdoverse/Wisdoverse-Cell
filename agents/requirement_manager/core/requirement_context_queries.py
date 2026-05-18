"""Application query use cases for requirement context read models."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RequirementContextRequirementView:
    """Requirement read model for context lookup responses."""

    id: str
    title: str
    description: str | None
    status: str
    priority: str | None
    category: str | None
    source_quote: str | None
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime | None
    context_message_ids: list[str]

    @classmethod
    def from_row(cls, row: object) -> "RequirementContextRequirementView":
        return cls(
            id=row.id,
            title=row.title,
            description=row.description,
            status=row.status,
            priority=row.priority,
            category=row.category,
            source_quote=row.source_quote,
            confirmed_by=row.confirmed_by,
            confirmed_at=row.confirmed_at,
            created_at=row.created_at,
            context_message_ids=list(row.context_message_ids or []),
        )


@dataclass(frozen=True, slots=True)
class RequirementContextMessageView:
    """Message read model for requirement context responses."""

    id: str
    sender_name: str
    content: str
    message_type: str
    sent_at: datetime | None
    session_id: str | None

    @classmethod
    def from_row(cls, row: object) -> "RequirementContextMessageView":
        return cls(
            id=row.id,
            sender_name=row.sender_name,
            content=row.content,
            message_type=row.message_type,
            sent_at=row.sent_at,
            session_id=row.session_id,
        )


@dataclass(frozen=True, slots=True)
class RequirementContextSessionView:
    """Session metadata derived from context messages."""

    session_id: str
    total_messages: int
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class RequirementContextResult:
    """Requirement context read model."""

    requirement: RequirementContextRequirementView
    context_messages: list[RequirementContextMessageView]
    session: RequirementContextSessionView | None


class RequirementContextRequirementRepository(Protocol):
    async def get_by_id(self, requirement_id: str) -> object | None:
        """Return one requirement by ID."""


class RequirementContextMessageRepository(Protocol):
    async def get_by_id(self, message_id: str) -> object | None:
        """Return one message by internal ID."""

    async def get_by_session(self, session_id: str) -> Sequence[object]:
        """Return all messages in one session."""


class RequirementContextQueryService:
    """Application use case for requirement context lookups."""

    def __init__(
        self,
        requirement_repository: RequirementContextRequirementRepository,
        message_repository: RequirementContextMessageRepository,
    ):
        self._requirements = requirement_repository
        self._messages = message_repository

    async def get_context(self, requirement_id: str) -> RequirementContextResult | None:
        row = await self._requirements.get_by_id(requirement_id)
        if row is None:
            return None

        requirement = RequirementContextRequirementView.from_row(row)
        context_messages: list[RequirementContextMessageView] = []
        for message_id in requirement.context_message_ids:
            message = await self._messages.get_by_id(message_id)
            if message is not None:
                context_messages.append(RequirementContextMessageView.from_row(message))

        return RequirementContextResult(
            requirement=requirement,
            context_messages=context_messages,
            session=await self._get_session_context(context_messages),
        )

    async def _get_session_context(
        self,
        context_messages: Sequence[RequirementContextMessageView],
    ) -> RequirementContextSessionView | None:
        if not context_messages:
            return None
        session_id = context_messages[0].session_id
        if not session_id:
            return None

        rows = await self._messages.get_by_session(session_id)
        return RequirementContextSessionView(
            session_id=session_id,
            total_messages=len(rows),
            started_at=rows[0].sent_at if rows else None,
            ended_at=rows[-1].sent_at if rows else None,
        )
