"""Structural tests for the conversation-engine port seed (DDD-017)."""

from __future__ import annotations

import pytest

from services.gateways.user_interaction.core.chat_ports import (
    ConversationEngineFactory,
    ConversationEnginePort,
)


class _DoubleEngine:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def run(self, user_message):
        yield {"event_type": "turn_complete", "text": f"echo: {user_message}"}


class _DoubleFactory:
    def __call__(
        self,
        *,
        system_prompt,
        history,
        tools_provider,
        max_tool_calls,
        agent_id,
    ):
        engine = _DoubleEngine()
        engine.messages = list(history)
        return engine


def test_engine_port_runtime_checkable_with_double() -> None:
    assert isinstance(_DoubleEngine(), ConversationEnginePort)


def test_factory_port_runtime_checkable_with_double() -> None:
    assert isinstance(_DoubleFactory(), ConversationEngineFactory)


@pytest.mark.asyncio
async def test_double_engine_yields_typed_events() -> None:
    engine = _DoubleEngine()
    events = [event async for event in engine.run("hello")]
    assert len(events) == 1
    assert events[0]["text"] == "echo: hello"
