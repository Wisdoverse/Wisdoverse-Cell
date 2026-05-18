from unittest.mock import AsyncMock

import pytest

from agents.requirement_manager.core.llm_usage_queries import LLMUsageQueryService


@pytest.mark.asyncio
async def test_get_daily_summary_delegates_to_repository():
    repository = AsyncMock()
    repository.get_daily_summary = AsyncMock(
        return_value={
            "date": "2026-05-17",
            "total_calls": 1,
            "success_calls": 1,
            "failed_calls": 0,
            "total_input_tokens": 10,
            "total_output_tokens": 5,
            "total_cost_usd": 0.001,
            "avg_latency_ms": 100,
            "by_agent": {},
            "by_task_type": {},
        }
    )

    result = await LLMUsageQueryService(repository).get_daily_summary(
        date="2026-05-17",
        agent_id="requirement-manager",
    )

    assert result["date"] == "2026-05-17"
    repository.get_daily_summary.assert_awaited_once_with(
        "2026-05-17",
        "requirement-manager",
    )
