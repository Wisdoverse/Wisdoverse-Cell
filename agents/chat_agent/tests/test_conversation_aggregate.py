"""Unit tests for the chat-agent ConversationTranscript aggregate."""

from __future__ import annotations

import json

import pytest

from agents.chat_agent.core.domain.conversation import (
    ConversationHistoryTrimmed,
    ConversationTranscript,
)


def _message(role: str, content):
    return {"role": role, "content": content}


def test_construct_requires_user_id() -> None:
    with pytest.raises(ValueError):
        ConversationTranscript(user_id="", messages=[])


def test_trim_to_message_limit_keeps_newest_messages() -> None:
    transcript = ConversationTranscript(
        user_id="u_1",
        messages=[
            _message("user", "one"),
            _message("assistant", "two"),
            _message("user", "three"),
        ],
    )

    transcript.trim_to_message_limit(2)

    assert transcript.messages == [_message("user", "three")]
    events = transcript.pull_events()
    assert [event.reason for event in events] == [
        "message_limit",
        "orphaned_tool_message",
    ]


def test_trim_to_message_limit_removes_leading_orphaned_tool_result() -> None:
    transcript = ConversationTranscript(
        user_id="u_1",
        messages=[
            _message(
                "user",
                [{"type": "tool_result", "tool_use_id": "tu_1", "content": "ok"}],
            ),
            _message("user", "hello"),
            _message("assistant", "reply"),
        ],
    )

    transcript.trim_to_message_limit(10)

    assert transcript.messages[0] == _message("user", "hello")
    events = transcript.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], ConversationHistoryTrimmed)
    assert events[0].reason == "orphaned_tool_message"
    assert events[0].removed_count == 1


def test_valid_user_start_is_preserved() -> None:
    messages = [
        _message("user", "hello"),
        _message("assistant", "reply"),
    ]
    transcript = ConversationTranscript(user_id="u_1", messages=messages)

    transcript.trim_to_message_limit(10)

    assert transcript.messages == messages
    assert transcript.pull_events() == []


def test_trim_to_serialized_size_removes_oldest_until_under_limit() -> None:
    transcript = ConversationTranscript(
        user_id="u_1",
        messages=[
            _message("user", "x" * 120),
            _message("assistant", "ok"),
            _message("user", "short"),
        ],
    )

    transcript.trim_to_serialized_size(90)

    serialized = json.dumps(transcript.messages, ensure_ascii=False).encode("utf-8")
    assert len(serialized) <= 90
    assert transcript.messages == [_message("user", "short")]
    assert [event.reason for event in transcript.pull_events()] == [
        "serialized_size",
        "orphaned_tool_message",
    ]


def test_single_oversized_message_is_left_for_persistence_layer_to_store() -> None:
    transcript = ConversationTranscript(
        user_id="u_1",
        messages=[_message("user", "x" * 120)],
    )

    transcript.trim_to_serialized_size(20)

    assert len(transcript.messages) == 1
    assert transcript.pull_events() == []


def test_trim_rejects_invalid_limits() -> None:
    transcript = ConversationTranscript(user_id="u_1", messages=[])
    with pytest.raises(ValueError):
        transcript.trim_to_message_limit(0)
    with pytest.raises(ValueError):
        transcript.trim_to_serialized_size(0)
