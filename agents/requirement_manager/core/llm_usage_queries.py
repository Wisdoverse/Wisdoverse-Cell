"""Application query use cases for LLM usage read models."""

from datetime import UTC, datetime
from typing import Protocol


class LLMUsageSummaryRepository(Protocol):
    async def get_daily_summary(self, date: str, agent_id: str | None = None) -> dict:
        """Return aggregated LLM usage for the requested date."""


class LLMUsageQueryService:
    """Application use case for querying LLM usage summaries."""

    def __init__(self, repository: LLMUsageSummaryRepository):
        self._repository = repository

    async def get_daily_summary(
        self,
        *,
        date: str | None = None,
        agent_id: str | None = None,
    ) -> dict:
        target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        return await self._repository.get_daily_summary(target_date, agent_id)
