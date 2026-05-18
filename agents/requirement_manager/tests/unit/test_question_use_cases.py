"""Requirement Manager question use-case tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.core.extractor import (
    ExtractedQuestion,
    ExtractedRequirement,
    ExtractionResult,
)
from agents.requirement_manager.models import OpenQuestion
from agents.requirement_manager.service.agent import RequirementManagerAgent


@pytest.mark.asyncio
async def test_answer_question_commits_in_application_service():
    """Question-answer writes are committed by the agent application boundary."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())

    question = MagicMock(spec=OpenQuestion)
    question.id = "qst_123"
    question.status = "answered"
    question.answer = "Use the web onboarding flow"
    question.answered_by = "pm"

    session = MagicMock()
    session.commit = AsyncMock()

    question_store = MagicMock()
    question_store.answer = AsyncMock(return_value=question)

    agent._get_question_store = MagicMock(return_value=question_store)
    result = await agent.answer_question(
        question_id="qst_123",
        answer="Use the web onboarding flow",
        answered_by="pm",
        session=session,
    )

    assert result is question
    question_store.answer.assert_awaited_once_with(
        "qst_123",
        answer="Use the web onboarding flow",
        answered_by="pm",
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_answer_question_does_not_commit_missing_question():
    """Missing questions do not produce a write commit."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())
    session = MagicMock()
    session.commit = AsyncMock()

    question_store = MagicMock()
    question_store.answer = AsyncMock(return_value=None)

    agent._get_question_store = MagicMock(return_value=question_store)
    result = await agent.answer_question(
        question_id="qst_missing",
        answer="No answer",
        answered_by="pm",
        session=session,
    )

    assert result is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_open_questions_uses_question_store_without_commit():
    """Open-question reads are delegated to the persistence port."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())
    session = MagicMock()
    session.commit = AsyncMock()

    questions = [MagicMock(spec=OpenQuestion)]
    question_store = MagicMock()
    question_store.list_open = AsyncMock(return_value=questions)

    agent._get_question_store = MagicMock(return_value=question_store)
    result = await agent.list_open_questions(session=session, limit=10)

    assert result is questions
    question_store.list_open.assert_awaited_once_with(limit=10)
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingest_meeting_persists_open_questions_through_question_store():
    """Meeting ingestion writes generated questions through the persistence port."""
    extractor = MagicMock()
    extractor.extract = AsyncMock(
        return_value=ExtractionResult(
            requirements=[
                ExtractedRequirement(
                    title="Login flow",
                    description="Users need an onboarding login flow",
                    category="功能",
                    priority="high",
                    source_quote="Need login",
                )
            ],
            open_questions=[
                ExtractedQuestion(question="Which identity provider?", context="Auth"),
                ExtractedQuestion(question="Should SSO be required?", context="Auth"),
            ],
        )
    )
    vectors = MagicMock()
    vectors.add_requirements_batch = AsyncMock()
    agent = RequirementManagerAgent(
        db=MagicMock(),
        bus=MagicMock(),
        vectors=vectors,
        requirement_extractor=extractor,
    )
    session = MagicMock()
    session.commit = AsyncMock()

    question_store = MagicMock()
    question_store.create_batch = AsyncMock(side_effect=lambda questions: questions)
    agent._get_question_store = MagicMock(return_value=question_store)
    agent._stage_requirement_event = AsyncMock()
    agent._publish_staged_requirement_event = AsyncMock()
    agent._commit_requirement_mutation = AsyncMock()

    async def create_meeting(meeting):
        meeting.id = "mtg_ingest"
        return meeting

    async def create_requirements(requirements):
        for index, requirement in enumerate(requirements, start=1):
            requirement.id = f"req_{index}"
        return requirements

    meeting_repo = MagicMock()
    meeting_repo.create = AsyncMock(side_effect=create_meeting)
    meeting_repo.mark_processed = AsyncMock()

    requirement_repo = MagicMock()
    requirement_repo.create_batch = AsyncMock(side_effect=create_requirements)

    with (
        patch.object(agent, "_get_meeting_store", return_value=meeting_repo),
        patch.object(agent, "_get_requirement_store", return_value=requirement_repo),
        patch(
            "agents.requirement_manager.service.agent.notification_service.send",
            new_callable=AsyncMock,
        ),
    ):
        result = await agent.ingest_meeting(
            content="Need login",
            source="upload",
            session=session,
        )

    assert result.questions_generated == 2
    question_store.create_batch.assert_awaited_once()
    questions = question_store.create_batch.await_args.args[0]
    assert [question.question for question in questions] == [
        "Which identity provider?",
        "Should SSO be required?",
    ]
    assert {question.requirement_id for question in questions} == {"req_1"}
