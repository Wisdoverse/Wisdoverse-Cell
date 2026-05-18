from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.feedback_use_cases import RequirementFeedbackUseCase


@pytest.mark.asyncio
async def test_confirm_requirement_delegates_to_agent_with_session():
    agent = AsyncMock()
    agent.confirm_requirement = AsyncMock(return_value=object())
    session = MagicMock()

    await RequirementFeedbackUseCase(
        agent=agent,
        session=session,
    ).confirm_requirement(
        requirement_id="req_1",
        confirmed_by="pm",
    )

    agent.confirm_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        confirmed_by="pm",
        session=session,
    )


@pytest.mark.asyncio
async def test_answer_question_delegates_to_agent_with_session():
    agent = AsyncMock()
    agent.answer_question = AsyncMock(return_value=object())
    session = MagicMock()

    await RequirementFeedbackUseCase(
        agent=agent,
        session=session,
    ).answer_question(
        "q_1",
        answer="US first",
        answered_by="pm",
    )

    agent.answer_question.assert_awaited_once_with(
        "q_1",
        answer="US first",
        answered_by="pm",
        session=session,
    )


@pytest.mark.asyncio
async def test_batch_confirm_returns_summary():
    agent = AsyncMock()
    agent.batch_confirm_requirements = AsyncMock(
        return_value=[
            {"requirement_id": "req_1", "success": True},
            {"requirement_id": "req_2", "success": False, "error": "missing"},
        ]
    )

    result = await RequirementFeedbackUseCase(
        agent=agent,
        session=MagicMock(),
    ).batch_confirm_requirements(
        requirement_ids=["req_1", "req_2"],
        confirmed_by="pm",
    )

    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.results[1]["error"] == "missing"
