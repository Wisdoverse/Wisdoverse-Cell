"""Tests for Evolution API application use cases."""

from unittest.mock import AsyncMock

import pytest

from shared.capabilities.evolution.core.api_use_cases import EvolutionApiUseCase


@pytest.mark.asyncio
async def test_trigger_analysis_forwards_days() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {
        "proposals": [{"operation": "add_skill", "target_agent": "pjm-agent"}]
    }

    result = await EvolutionApiUseCase(agent).trigger_analysis(days=14)

    assert result["proposals"][0]["operation"] == "add_skill"
    agent.handle_request.assert_awaited_once_with(
        {"action": "trigger_analysis", "days": 14}
    )
