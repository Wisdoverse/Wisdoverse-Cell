"""Tests for the optional LiteLLM provider path."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from shared.infra.llm_gateway import LLMGateway


def _make_litellm_gateway(monkeypatch, fake_acompletion: AsyncMock) -> LLMGateway:
    """Create a gateway configured for LiteLLM with a fake SDK module."""
    monkeypatch.setitem(
        __import__("sys").modules,
        "litellm",
        SimpleNamespace(acompletion=fake_acompletion),
    )
    with patch("shared.infra.llm_gateway.settings") as s:
        s.llm_provider = "litellm"
        s.anthropic_base_url = ""
        s.litellm_api_base = ""
        s.require_anthropic_proxy = False
        s.default_model = "openai/gpt-5"
        s.chat_model = "openai/gpt-5"
        s.summary_model = "openai/gpt-5-mini"
        s.llm_daily_budget_usd = 100.0
        s.llm_per_request_cost_cap_usd = 5.0
        s.control_plane_llm_budget_enforced = False
        s.redis_url = "redis://localhost:6379"
        gateway = LLMGateway(api_key="test-anthropic-key")
    gateway._track_usage = Mock()
    gateway._track_redis_cost = AsyncMock()
    return gateway


def _litellm_text_response(text: str = "Hello") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    )


@pytest.mark.asyncio
async def test_complete_routes_through_litellm(monkeypatch):
    fake_acompletion = AsyncMock(return_value=_litellm_text_response("Hello via LiteLLM"))
    gateway = _make_litellm_gateway(monkeypatch, fake_acompletion)

    result = await gateway.complete(
        prompt="Hello",
        agent_id="test-agent",
        model="openai/gpt-5",
        system_prompt="Be concise.",
    )

    assert result == "Hello via LiteLLM"
    kwargs = fake_acompletion.call_args.kwargs
    assert kwargs["model"] == "openai/gpt-5"
    assert kwargs["messages"] == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Hello"},
    ]


@pytest.mark.asyncio
async def test_litellm_prefixes_native_claude_model(monkeypatch):
    fake_acompletion = AsyncMock(return_value=_litellm_text_response())
    gateway = _make_litellm_gateway(monkeypatch, fake_acompletion)

    await gateway.complete(
        prompt="Hello",
        agent_id="test-agent",
        model="claude-sonnet-4-20250514",
    )

    kwargs = fake_acompletion.call_args.kwargs
    assert kwargs["model"] == "anthropic/claude-sonnet-4-20250514"
    assert kwargs["api_key"] == "test-anthropic-key"


@pytest.mark.asyncio
async def test_create_messages_converts_tools_and_tool_calls(monkeypatch):
    fake_acompletion = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        tool_calls=[
                            SimpleNamespace(
                                id="call_1",
                                function=SimpleNamespace(
                                    name="tool_search",
                                    arguments='{"query": "send"}',
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5),
        )
    )
    gateway = _make_litellm_gateway(monkeypatch, fake_acompletion)

    response = await gateway.create_messages(
        agent_id="chat-agent",
        model="openai/gpt-5",
        system=[{"type": "text", "text": "Use tools when needed."}],
        messages=[{"role": "user", "content": "Send a message"}],
        tools=[
            {
                "name": "tool_search",
                "description": "Search deferred tools",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }
        ],
    )

    kwargs = fake_acompletion.call_args.kwargs
    assert kwargs["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "tool_search",
                "description": "Search deferred tools",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            },
        }
    ]
    assert response.stop_reason == "tool_use"
    assert response.usage.input_tokens == 20
    assert response.usage.output_tokens == 5
    tool_block = response.content[0]
    assert tool_block.type == "tool_use"
    assert tool_block.id == "call_1"
    assert tool_block.name == "tool_search"
    assert tool_block.input == {"query": "send"}


def test_litellm_converts_anthropic_tool_history_to_openai_messages(monkeypatch):
    gateway = _make_litellm_gateway(monkeypatch, AsyncMock())

    messages = gateway._messages_to_litellm(
        messages=[
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I will search."},
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "tool_search",
                        "input": {"query": "send"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_1",
                        "content": "Found send_feishu_message",
                    }
                ],
            },
        ]
    )

    assert messages == [
        {
            "role": "assistant",
            "content": "I will search.",
            "tool_calls": [
                {
                    "id": "tu_1",
                    "type": "function",
                    "function": {
                        "name": "tool_search",
                        "arguments": '{"query": "send"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "tu_1",
            "content": "Found send_feishu_message",
        },
    ]
