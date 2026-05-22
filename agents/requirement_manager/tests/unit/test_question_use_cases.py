"""Requirement Manager question use-case tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.extractor import (
    ExtractedQuestion,
    ExtractedRequirement,
    ExtractionResult,
)
from agents.requirement_manager.models import OpenQuestion
from agents.requirement_manager.service.agent import RequirementManagerAgent


@pytest.mark.asyncio
async def test_answer_question_with_uow_uses_question_store():
    """Question-answer writes use the transaction-scoped question store."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())

    question = MagicMock(spec=OpenQuestion)
    question.id = "qst_123"
    question.status = "answered"
    question.answer = "Use the web onboarding flow"
    question.answered_by = "pm"

    question_store = MagicMock()
    question_store.answer = AsyncMock(return_value=question)

    uow = MagicMock()
    uow.questions = question_store
    result = await agent.answer_question_with_uow(
        question_id="qst_123",
        answer="Use the web onboarding flow",
        answered_by="pm",
        uow=uow,
    )

    assert result.entity is question
    question_store.answer.assert_awaited_once_with(
        "qst_123",
        answer="Use the web onboarding flow",
        answered_by="pm",
    )


@pytest.mark.asyncio
async def test_answer_question_with_uow_returns_empty_result_for_missing_question():
    """Missing questions do not produce a mutation result entity."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())

    question_store = MagicMock()
    question_store.answer = AsyncMock(return_value=None)

    uow = MagicMock()
    uow.questions = question_store
    result = await agent.answer_question_with_uow(
        question_id="qst_missing",
        answer="No answer",
        answered_by="pm",
        uow=uow,
    )

    assert result.entity is None


@pytest.mark.asyncio
async def test_list_open_questions_uses_question_store_without_commit():
    """Open-question reads are delegated to the persistence port."""
    agent = RequirementManagerAgent(db=MagicMock(), bus=MagicMock(), vectors=MagicMock())
    session = MagicMock()
    session.commit = AsyncMock()

    questions = [MagicMock(spec=OpenQuestion)]
    question_store = MagicMock()
    question_store.list_open = AsyncMock(return_value=questions)

    uow = MagicMock()
    uow.questions = question_store
    agent._session_unit_of_work = MagicMock(return_value=uow)
    result = await agent.list_open_questions(session=session, limit=10)

    assert result is questions
    question_store.list_open.assert_awaited_once_with(limit=10)
    agent._session_unit_of_work.assert_called_once_with(session)
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

    question_store = MagicMock()
    question_store.create_batch = AsyncMock(side_effect=lambda questions: questions)
    outbox = MagicMock()
    outbox.stage = AsyncMock()

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

    uow = MagicMock()
    uow.meetings = meeting_repo
    uow.requirements = requirement_repo
    uow.questions = question_store
    uow.outbox = outbox

    result = await agent.ingest_meeting_with_uow(
        content="Need login",
        source="upload",
        uow=uow,
    )

    assert result.questions_generated == 2
    outbox.stage.assert_awaited_once()
    question_store.create_batch.assert_awaited_once()
    questions = question_store.create_batch.await_args.args[0]
    assert [question.question for question in questions] == [
        "Which identity provider?",
        "Should SSO be required?",
    ]
    assert {question.requirement_id for question in questions} == {"req_1"}
