"""Requirement ingest side-effect use case tests."""

from typing import Any

import pytest

from agents.requirement_manager.core.ingest_side_effect_use_cases import (
    RequirementIngestSideEffectUseCase,
    RequirementSessionExtractionCardUseCase,
)
from agents.requirement_manager.core.meeting_ingest_workflow import IngestResult
from shared.schemas.event import Event, EventTypes


class FakePublisher:
    def __init__(self):
        self.published: list[tuple[Event, str | None]] = []

    async def publish_staged_event(
        self,
        event: Event,
        *,
        requirement_id: str | None,
    ) -> bool:
        self.published.append((event, requirement_id))
        return True


class FakeNotifier:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    async def send(self, **kwargs):
        if self.fail:
            raise RuntimeError("notification unavailable")
        self.sent.append(kwargs)


class FakeMessenger:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.cards: list[dict[str, Any]] = []

    async def send_card(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card: dict[str, Any],
    ) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("messenger unavailable")
        payload = {
            "receive_id": receive_id,
            "receive_id_type": receive_id_type,
            "card": card,
        }
        self.cards.append(payload)
        return payload


class FakeCardRenderer:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def extraction_result_card(
        self,
        *,
        requirements: list[dict[str, Any]],
        meeting_title: str,
        questions_count: int,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "requirements": requirements,
                "meeting_title": meeting_title,
                "questions_count": questions_count,
            }
        )
        return {"type": "template", "title": meeting_title}


def _event() -> Event:
    return Event.create(
        event_type=EventTypes.REQUIREMENT_EXTRACTED,
        source_agent="requirement-manager",
        payload={"requirement_ids": ["req_1"]},
    )


def _ingest_result(**overrides) -> IngestResult:
    values = {
        "meeting_id": "mtg_1",
        "requirements_extracted": 1,
        "questions_generated": 2,
        "requirement_ids": ["req_1"],
        "requirements": [{"id": "req_1", "title": "Offline capture"}],
        "staged_events": [_event()],
    }
    values.update(overrides)
    return IngestResult(**values)


@pytest.mark.asyncio
async def test_publish_ingest_side_effects_publishes_events_and_notification():
    publisher = FakePublisher()
    notifier = FakeNotifier()

    await RequirementIngestSideEffectUseCase(
        event_publisher=publisher,
        notifier=notifier,
        notification_channel="feishu",
    ).publish_ingest_side_effects(_ingest_result())

    assert len(publisher.published) == 1
    event, requirement_id = publisher.published[0]
    assert event.event_type == EventTypes.REQUIREMENT_EXTRACTED
    assert requirement_id is None
    assert notifier.sent == [
        {
            "channel": "feishu",
            "title": "新需求待确认",
            "content": "从会议中提取了 1 个新需求，2 个待确认问题。",
        }
    ]


@pytest.mark.asyncio
async def test_publish_ingest_side_effects_skips_notification_without_requirements():
    publisher = FakePublisher()
    notifier = FakeNotifier()

    await RequirementIngestSideEffectUseCase(
        event_publisher=publisher,
        notifier=notifier,
        notification_channel="feishu",
    ).publish_ingest_side_effects(
        _ingest_result(
            requirements_extracted=0,
            questions_generated=0,
            requirement_ids=[],
            requirements=[],
        )
    )

    assert len(publisher.published) == 1
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_publish_ingest_side_effects_tolerates_notification_failure():
    publisher = FakePublisher()
    notifier = FakeNotifier(fail=True)

    await RequirementIngestSideEffectUseCase(
        event_publisher=publisher,
        notifier=notifier,
        notification_channel="feishu",
    ).publish_ingest_side_effects(_ingest_result())

    assert len(publisher.published) == 1
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_send_session_extraction_card_renders_and_sends_card():
    messenger = FakeMessenger()
    renderer = FakeCardRenderer()

    await RequirementSessionExtractionCardUseCase(
        messenger=messenger,
        card_renderer=renderer,
    ).send_session_extraction_card(
        "chat_1",
        _ingest_result(),
        "session_123456789",
    )

    assert renderer.calls == [
        {
            "requirements": [{"id": "req_1", "title": "Offline capture"}],
            "meeting_title": "群聊会话 session_...",
            "questions_count": 2,
        }
    ]
    assert messenger.cards == [
        {
            "receive_id": "chat_1",
            "receive_id_type": "chat_id",
            "card": {
                "type": "template",
                "title": "群聊会话 session_...",
            },
        }
    ]


@pytest.mark.asyncio
async def test_send_session_extraction_card_skips_when_adapter_missing():
    renderer = FakeCardRenderer()

    await RequirementSessionExtractionCardUseCase(
        messenger=None,
        card_renderer=renderer,
    ).send_session_extraction_card(
        "chat_1",
        _ingest_result(),
        "session_1",
    )

    assert renderer.calls == []


@pytest.mark.asyncio
async def test_send_session_extraction_card_tolerates_messenger_failure():
    messenger = FakeMessenger(fail=True)
    renderer = FakeCardRenderer()

    await RequirementSessionExtractionCardUseCase(
        messenger=messenger,
        card_renderer=renderer,
    ).send_session_extraction_card(
        "chat_1",
        _ingest_result(),
        "session_1",
    )

    assert renderer.calls
    assert messenger.cards == []
