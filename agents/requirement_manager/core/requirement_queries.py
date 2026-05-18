"""Application query use cases for requirement read models."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("requirement_manager.requirement_queries")


@dataclass(frozen=True, slots=True)
class OpenQuestionView:
    """Open-question read model nested under requirements."""

    id: str
    question: str
    context: str | None
    status: str
    answer: str | None
    answered_by: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: object) -> "OpenQuestionView":
        return cls(
            id=row.id,
            question=row.question,
            context=row.context,
            status=row.status,
            answer=row.answer,
            answered_by=row.answered_by,
            created_at=row.created_at,
        )


@dataclass(frozen=True, slots=True)
class RequirementView:
    """Requirement read model exposed by query use cases."""

    id: str
    title: str
    description: str
    source_quote: str | None
    status: str
    priority: str
    category: str
    source_meeting_ids: list[str]
    confirmed_by: str | None
    confirmed_at: datetime | None
    open_questions: list[OpenQuestionView]
    history: list[dict]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: object) -> "RequirementView":
        return cls(
            id=row.id,
            title=row.title,
            description=row.description,
            source_quote=row.source_quote,
            status=row.status,
            priority=row.priority,
            category=row.category,
            source_meeting_ids=list(row.source_meeting_ids or []),
            confirmed_by=row.confirmed_by,
            confirmed_at=row.confirmed_at,
            open_questions=[
                OpenQuestionView.from_row(question)
                for question in (row.open_questions or [])
            ],
            history=list(row.history or []),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@dataclass(frozen=True, slots=True)
class RequirementListResult:
    """Paginated requirement list read model."""

    total: int
    page: int
    page_size: int
    items: list[RequirementView]


@dataclass(frozen=True, slots=True)
class MeetingView:
    """Meeting read model exposed by query use cases."""

    id: str
    source: str
    title: str | None
    meeting_date: datetime | None
    participants: list[str]
    processed: bool
    created_at: datetime

    @classmethod
    def from_row(cls, row: object) -> "MeetingView":
        return cls(
            id=row.id,
            source=row.source,
            title=row.title,
            meeting_date=row.meeting_date,
            participants=list(row.participants or []),
            processed=row.processed,
            created_at=row.created_at,
        )


@dataclass(frozen=True, slots=True)
class MeetingListResult:
    """Paginated meeting list read model."""

    total: int
    page: int
    page_size: int
    items: list[MeetingView]


@dataclass(frozen=True, slots=True)
class StatsResult:
    """Basic requirement-manager statistics read model."""

    requirements_by_status: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: int | None


@dataclass(frozen=True, slots=True)
class EnhancedStatsResult:
    """Enhanced requirement-manager statistics read model."""

    requirements_by_status: dict[str, int]
    requirements_by_priority: dict[str, int]
    requirements_by_category: dict[str, int]
    total_meetings: int
    unprocessed_meetings: int
    vector_store_count: int | None
    weekly_trend: list[dict]
    today_count: int


@dataclass(frozen=True, slots=True)
class SimilarRequirementView:
    """Similar requirement read model returned by the vector index."""

    id: str
    title: str
    category: str
    similarity: float

    @classmethod
    def from_result(cls, result: dict) -> "SimilarRequirementView":
        return cls(
            id=result["id"],
            title=result["title"],
            category=result["category"],
            similarity=result["similarity"],
        )


@dataclass(frozen=True, slots=True)
class SimilarRequirementsResult:
    """Similar-requirements query result."""

    requirement_id: str
    similar: list[SimilarRequirementView]


@dataclass(frozen=True, slots=True)
class SearchRequirementView:
    """Semantic search item returned by the vector index."""

    id: str
    title: str
    category: str
    similarity: float

    @classmethod
    def from_result(cls, result: dict) -> "SearchRequirementView":
        return cls(
            id=result["id"],
            title=result["title"],
            category=result["category"],
            similarity=result["similarity"],
        )


@dataclass(frozen=True, slots=True)
class SemanticSearchResult:
    """Semantic search query result."""

    query: str
    items: list[SearchRequirementView]


@dataclass(frozen=True, slots=True)
class RequirementHistoryResult:
    """Requirement history query result."""

    requirement_id: str
    title: str
    current_status: str
    history: list[dict]
    total_changes: int


@dataclass(frozen=True, slots=True)
class RequirementDiffResult:
    """Requirement history diff query result."""

    requirement_id: str
    message: str | None = None
    diff: list[dict] | None = None
    from_index: int | None = None
    to_index: int | None = None
    changes: list[dict] | None = None
    total_in_range: int | None = None


class RequirementQueryRepository(Protocol):
    async def list_all(
        self,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[object], int]:
        """Return filtered requirements and total count."""

    async def get_by_id(self, requirement_id: str) -> object | None:
        """Return one requirement by ID."""

    async def count_by_status(self) -> dict[str, int]:
        """Return requirement counts grouped by status."""

    async def count_by_priority(self) -> dict[str, int]:
        """Return requirement counts grouped by priority."""

    async def count_by_category(self) -> dict[str, int]:
        """Return requirement counts grouped by category."""

    async def get_daily_counts(self, days: int = 7) -> list[dict]:
        """Return daily requirement counts."""

    async def count_today(self) -> int:
        """Return today's requirement count."""


class MeetingQueryRepository(Protocol):
    async def list_all(
        self,
        source: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[object], int]:
        """Return filtered meetings and total count."""

    async def list_unprocessed(self, limit: int = 100) -> Sequence[object]:
        """Return unprocessed meetings."""


class VectorStatsProvider(Protocol):
    async def get_stats(self) -> dict:
        """Return vector-store statistics."""

    async def search(
        self,
        query: str,
        n_results: int = 20,
        category_filter: str | None = None,
        min_similarity: float = 0.5,
    ) -> list[dict]:
        """Return semantic search matches."""

    async def find_similar(
        self,
        requirement_id: str,
        n_results: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict]:
        """Return semantically similar requirements."""


class RequirementQueryService:
    """Application use case for requirement-manager read models."""

    def __init__(
        self,
        requirement_repository: RequirementQueryRepository,
        meeting_repository: MeetingQueryRepository,
        vector_stats: VectorStatsProvider,
    ):
        self._requirements = requirement_repository
        self._meetings = meeting_repository
        self._vector_stats = vector_stats

    async def list_requirements(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> RequirementListResult:
        rows, total = await self._requirements.list_all(
            status=status,
            category=category,
            priority=priority,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return RequirementListResult(
            total=total,
            page=page,
            page_size=page_size,
            items=[RequirementView.from_row(row) for row in rows],
        )

    async def get_requirement(self, requirement_id: str) -> RequirementView | None:
        row = await self._requirements.get_by_id(requirement_id)
        if row is None:
            return None
        return RequirementView.from_row(row)

    async def search_requirements(
        self,
        *,
        query: str,
        category: str | None = None,
        limit: int = 20,
        min_similarity: float = 0.5,
    ) -> SemanticSearchResult:
        rows = await self._vector_stats.search(
            query=query,
            n_results=limit,
            category_filter=category,
            min_similarity=min_similarity,
        )
        items = [SearchRequirementView.from_result(row) for row in rows]
        logger.info(
            "semantic_search",
            query_hash=hash_identifier(query),
            query_length=len(query),
            results_count=len(items),
        )
        return SemanticSearchResult(query=query, items=items)

    async def list_meetings(
        self,
        *,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> MeetingListResult:
        rows, total = await self._meetings.list_all(
            source=source,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return MeetingListResult(
            total=total,
            page=page,
            page_size=page_size,
            items=[MeetingView.from_row(row) for row in rows],
        )

    async def get_stats(self) -> StatsResult:
        status_counts = await self._requirements.count_by_status()
        _meetings, total_meetings = await self._meetings.list_all(limit=1)
        unprocessed = await self._meetings.list_unprocessed(limit=1000)
        vector_stats = await self._vector_stats.get_stats()

        return StatsResult(
            requirements_by_status=status_counts,
            total_meetings=total_meetings,
            unprocessed_meetings=len(unprocessed),
            vector_store_count=vector_stats.get("total_documents"),
        )

    async def get_enhanced_stats(self) -> EnhancedStatsResult:
        status_counts = await self._requirements.count_by_status()
        priority_counts = await self._requirements.count_by_priority()
        category_counts = await self._requirements.count_by_category()
        _meetings, total_meetings = await self._meetings.list_all(limit=1)
        unprocessed = await self._meetings.list_unprocessed(limit=1000)
        vector_stats = await self._vector_stats.get_stats()
        weekly_trend = await self._requirements.get_daily_counts(days=7)
        today_count = await self._requirements.count_today()

        return EnhancedStatsResult(
            requirements_by_status=status_counts,
            requirements_by_priority=priority_counts,
            requirements_by_category=category_counts,
            total_meetings=total_meetings,
            unprocessed_meetings=len(unprocessed),
            vector_store_count=vector_stats.get("total_documents"),
            weekly_trend=weekly_trend,
            today_count=today_count,
        )

    async def find_similar_requirements(
        self,
        requirement_id: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.7,
    ) -> SimilarRequirementsResult | None:
        requirement = await self._requirements.get_by_id(requirement_id)
        if requirement is None:
            return None

        similar = await self._vector_stats.find_similar(
            requirement_id=requirement_id,
            n_results=limit,
            min_similarity=min_similarity,
        )
        return SimilarRequirementsResult(
            requirement_id=requirement_id,
            similar=[SimilarRequirementView.from_result(item) for item in similar],
        )

    async def get_requirement_history(
        self,
        requirement_id: str,
    ) -> RequirementHistoryResult | None:
        requirement = await self._requirements.get_by_id(requirement_id)
        if requirement is None:
            return None

        history = list(requirement.history or [])
        return RequirementHistoryResult(
            requirement_id=requirement_id,
            title=requirement.title,
            current_status=requirement.status,
            history=history,
            total_changes=len(history),
        )

    async def get_requirement_diff(
        self,
        requirement_id: str,
        *,
        from_index: int = 0,
        to_index: int = -1,
    ) -> RequirementDiffResult | None:
        requirement = await self._requirements.get_by_id(requirement_id)
        if requirement is None:
            return None

        history = list(requirement.history or [])
        if not history:
            return RequirementDiffResult(
                requirement_id=requirement_id,
                message="No change history",
                diff=[],
            )

        normalized_to_index = to_index
        if normalized_to_index == -1 or normalized_to_index >= len(history):
            normalized_to_index = len(history) - 1

        normalized_from_index = from_index
        if normalized_from_index >= len(history):
            normalized_from_index = 0

        changes = history[normalized_from_index : normalized_to_index + 1]
        return RequirementDiffResult(
            requirement_id=requirement_id,
            from_index=normalized_from_index,
            to_index=normalized_to_index,
            changes=changes,
            total_in_range=len(changes),
        )
