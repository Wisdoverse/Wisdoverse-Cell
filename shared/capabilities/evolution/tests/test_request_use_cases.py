from unittest.mock import AsyncMock

import pytest

from shared.capabilities.evolution.core.request_use_cases import (
    EvolutionRequestUseCase,
)


@pytest.mark.asyncio
async def test_trigger_analysis_analyzes_days_and_attaches_approvals() -> None:
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(
        return_value=[
            {"operation": "add_skill", "target_agent": "pjm-agent"},
            {"operation": "modify_prompt", "target_agent": "qa-agent"},
        ]
    )
    attach_approval = AsyncMock(
        side_effect=lambda proposal: {**proposal, "control_plane_approval_id": "appr_1"}
    )

    result = await EvolutionRequestUseCase(
        analyzer=analyzer,
        attach_proposal_approval=attach_approval,
    ).handle({"action": "trigger_analysis", "days": 14})

    assert result == {
        "proposals": [
            {
                "operation": "add_skill",
                "target_agent": "pjm-agent",
                "control_plane_approval_id": "appr_1",
            },
            {
                "operation": "modify_prompt",
                "target_agent": "qa-agent",
                "control_plane_approval_id": "appr_1",
            },
        ]
    }
    analyzer.analyze.assert_awaited_once_with(14)
    assert attach_approval.await_count == 2


@pytest.mark.asyncio
async def test_trigger_analysis_defaults_to_seven_days() -> None:
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(return_value=[])

    result = await EvolutionRequestUseCase(
        analyzer=analyzer,
        attach_proposal_approval=AsyncMock(),
    ).handle({"action": "trigger_analysis"})

    assert result == {"proposals": []}
    analyzer.analyze.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_unknown_action_preserves_status_ok_contract() -> None:
    analyzer = AsyncMock()

    result = await EvolutionRequestUseCase(
        analyzer=analyzer,
        attach_proposal_approval=AsyncMock(),
    ).handle({"action": "unknown"})

    assert result == {"status": "ok"}
    analyzer.analyze.assert_not_called()
