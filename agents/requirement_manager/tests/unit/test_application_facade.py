"""Requirement application facade tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.core.application_facade import (
    RequirementApplicationFacade,
)
from agents.requirement_manager.core.meeting_ingest_workflow import IngestResult


def _facade(
    *,
    uow_factory: MagicMock | None = None,
    session_uow_factory: MagicMock | None = None,
    ingest_workflow: MagicMock | None = None,
    command_use_case: MagicMock | None = None,
    read_query_use_case: MagicMock | None = None,
    mutation_side_effects: MagicMock | None = None,
    ingest_side_effects: MagicMock | None = None,
    outbox_delivery: MagicMock | None = None,
    messenger: MagicMock | None = None,
    card_renderer: MagicMock | None = None,
) -> RequirementApplicationFacade:
    return RequirementApplicationFacade(
        uow_factory=uow_factory or MagicMock(),
        session_uow_factory=session_uow_factory or MagicMock(),
        ingest_workflow=ingest_workflow or MagicMock(),
        command_use_case=command_use_case or MagicMock(),
        read_query_use_case=read_query_use_case or MagicMock(),
        mutation_side_effects=mutation_side_effects or MagicMock(),
        ingest_side_effects=ingest_side_effects or MagicMock(),
        outbox_delivery=outbox_delivery or MagicMock(),
        messenger=messenger,
        card_renderer=card_renderer,
    )


@pytest.mark.asyncio
async def test_application_facade_ingest_uses_legacy_session_uow_and_side_effects():
    session = MagicMock()
    uow = MagicMock()
    uow.commit = AsyncMock()
    session_uow_factory = MagicMock(return_value=uow)
    result = IngestResult(
        meeting_id="mtg_1",
        requirements_extracted=1,
        questions_generated=0,
        requirement_ids=["req_1"],
    )
    ingest_workflow = MagicMock()
    ingest_workflow.ingest_meeting = AsyncMock(return_value=result)
    ingest_side_effects = MagicMock()
    ingest_side_effects.publish_ingest_side_effects = AsyncMock()
    facade = _facade(
        session_uow_factory=session_uow_factory,
        ingest_workflow=ingest_workflow,
        ingest_side_effects=ingest_side_effects,
    )

    actual = await facade.ingest_meeting(
        content="Need login",
        source="upload",
        session=session,
    )

    assert actual is result
    session_uow_factory.assert_called_once_with(session)
    ingest_workflow.ingest_meeting.assert_awaited_once()
    uow.commit.assert_awaited_once()
    ingest_side_effects.publish_ingest_side_effects.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_application_facade_command_uses_legacy_session_uow():
    session = MagicMock()
    uow = MagicMock()
    session_uow_factory = MagicMock(return_value=uow)
    command_use_case = MagicMock()
    requirement = MagicMock()
    command_use_case.confirm_requirement = AsyncMock(return_value=requirement)
    facade = _facade(
        session_uow_factory=session_uow_factory,
        command_use_case=command_use_case,
    )

    actual = await facade.confirm_requirement(
        "req_1",
        "pm",
        session=session,
    )

    assert actual is requirement
    session_uow_factory.assert_called_once_with(session)
    command_use_case.confirm_requirement.assert_awaited_once_with(
        requirement_id="req_1",
        confirmed_by="pm",
        uow=uow,
    )


@pytest.mark.asyncio
async def test_application_facade_read_uses_legacy_session_uow():
    session = MagicMock()
    uow = MagicMock()
    questions = [MagicMock()]
    session_uow_factory = MagicMock(return_value=uow)
    read_query_use_case = MagicMock()
    read_query_use_case.list_open_questions_with_uow = AsyncMock(
        return_value=questions,
    )
    facade = _facade(
        session_uow_factory=session_uow_factory,
        read_query_use_case=read_query_use_case,
    )

    actual = await facade.list_open_questions(session=session, limit=10)

    assert actual is questions
    session_uow_factory.assert_called_once_with(session)
    read_query_use_case.list_open_questions_with_uow.assert_awaited_once_with(
        uow,
        limit=10,
    )


@pytest.mark.asyncio
async def test_application_facade_uses_configured_session_card_ports():
    messenger = MagicMock()
    messenger.send_card = AsyncMock()
    card_renderer = MagicMock()
    card = {"type": "card"}
    card_renderer.extraction_result_card.return_value = card
    result = IngestResult(
        meeting_id="mtg_1",
        requirements_extracted=1,
        questions_generated=2,
        requirement_ids=["req_1"],
    )
    facade = _facade(card_renderer=card_renderer)
    facade.configure_messenger(messenger)

    await facade.send_session_extraction_card("chat_1", result, "session_123456")

    card_renderer.extraction_result_card.assert_called_once()
    messenger.send_card.assert_awaited_once_with(
        receive_id="chat_1",
        receive_id_type="chat_id",
        card=card,
    )
