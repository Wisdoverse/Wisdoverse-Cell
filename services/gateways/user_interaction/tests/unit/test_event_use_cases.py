from unittest.mock import patch

import pytest

from services.gateways.user_interaction.core.event_use_cases import (
    UserInteractionEventUseCase,
)
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_pm_response_logs_hashed_user_id() -> None:
    event = Event.create(
        event_type=EventTypes.CHAT_PM_RESPONSE,
        source_agent="pjm-agent",
        payload={"user_id": "test_user", "reply": "pm response"},
    )

    with patch(
        "services.gateways.user_interaction.core.event_use_cases.logger"
    ) as logger:
        result = await UserInteractionEventUseCase().handle(event)

    assert result == []
    log_call = logger.info.call_args
    assert log_call.args == ("project_management_response_received",)
    assert log_call.kwargs["user_hash"] == hash_identifier("test_user")
    assert "user_id" not in log_call.kwargs


@pytest.mark.asyncio
async def test_pm_response_without_user_id_logs_empty_hash() -> None:
    event = Event.create(
        event_type=EventTypes.CHAT_PM_RESPONSE,
        source_agent="pjm-agent",
        payload={},
    )

    with patch(
        "services.gateways.user_interaction.core.event_use_cases.logger"
    ) as logger:
        result = await UserInteractionEventUseCase().handle(event)

    assert result == []
    assert logger.info.call_args.kwargs["user_hash"] == ""


@pytest.mark.asyncio
async def test_coordinator_response_logs_task_context() -> None:
    event = Event.create(
        event_type=EventTypes.COORDINATOR_RESPONSE,
        source_agent="coordinator",
        payload={"task_id": "task-1", "workflow_id": "wf-1"},
    )

    with patch(
        "services.gateways.user_interaction.core.event_use_cases.logger"
    ) as logger:
        result = await UserInteractionEventUseCase().handle(event)

    assert result == []
    log_call = logger.info.call_args
    assert log_call.args == ("coordinator_response_received",)
    assert log_call.kwargs == {"task_id": "task-1", "workflow_id": "wf-1"}


@pytest.mark.asyncio
async def test_unknown_event_returns_empty_list() -> None:
    event = Event.create(
        event_type="unknown.event",
        source_agent="test",
        payload={},
    )

    result = await UserInteractionEventUseCase().handle(event)

    assert result == []
