"""Application side effects for committed Requirement mutations."""
from __future__ import annotations

import inspect
from typing import Protocol

from shared.schemas.event import Event
from shared.utils.logger import get_logger

from .requirement_mutation_workflow import RequirementMutationResult

logger = get_logger("requirement_manager.mutation_side_effects")


class RequirementVectorDeletePort(Protocol):
    """Search-index boundary for Requirement deletion side effects."""

    def delete_requirement(self, requirement_id: str):
        """Delete one requirement from the search index."""


class RequirementStagedEventPublisherPort(Protocol):
    """Outbox delivery boundary for already-staged Requirement events."""

    async def publish_staged_event(
        self,
        event: Event,
        *,
        requirement_id: str | None,
    ) -> bool:
        """Publish one event that was staged in the local transaction."""


class RequirementMutationSideEffectUseCase:
    """Run post-commit external side effects for Requirement mutations."""

    def __init__(
        self,
        *,
        vector_index: RequirementVectorDeletePort,
        event_publisher: RequirementStagedEventPublisherPort,
    ) -> None:
        self._vector_index = vector_index
        self._event_publisher = event_publisher

    async def publish_requirement_mutation_side_effects(
        self,
        result: RequirementMutationResult,
    ) -> None:
        if result.delete_vector_requirement_id:
            await self.delete_requirement_vector_record(
                result.delete_vector_requirement_id,
            )
        if result.event:
            await self._event_publisher.publish_staged_event(
                result.event,
                requirement_id=result.requirement_id,
            )

    async def delete_requirement_vector_record(self, requirement_id: str) -> None:
        """Best-effort cleanup for a deleted Requirement search-index record."""
        try:
            result = self._vector_index.delete_requirement(requirement_id)
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
