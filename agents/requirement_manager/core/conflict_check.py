"""Application use case for requirement conflict checks."""

from typing import Optional, Protocol

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .comparator import ComparisonResult

logger = get_logger("requirement_manager.conflict_check")


class RequirementComparatorPort(Protocol):
    async def compare(
        self,
        new_title: str,
        new_description: str,
        new_category: Optional[str] = None,
        exclude_ids: Optional[list[str]] = None,
    ) -> ComparisonResult:
        """Compare a requirement draft with existing requirements."""


class RequirementConflictCheckUseCase:
    """Application use case for conflict-check orchestration."""

    def __init__(self, *, comparator: RequirementComparatorPort):
        self._comparator = comparator

    async def check_conflict(
        self,
        *,
        title: str,
        description: str,
        category: Optional[str] = None,
        exclude_ids: Optional[list[str]] = None,
    ) -> ComparisonResult:
        result = await self._comparator.compare(
            new_title=title,
            new_description=description,
            new_category=category,
            exclude_ids=exclude_ids,
        )
        logger.info(
            "conflict_check",
            title_hash=hash_identifier(title),
            relation=result.relation.value,
            confidence=result.confidence,
        )
        return result
