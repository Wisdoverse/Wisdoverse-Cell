"""ConversationEngine — Unit Tests (TDD RED phase).

Shared multi-turn tool-calling loop with AsyncGenerator streaming,
state separation, compression integration, and error recovery.
"""
from unittest.mock import AsyncMock, Mock

import pytest

from shared.infra.conversation_engine import (
    ConversationConfig,
    ConversationEngine,
    StopReason,
)
from shared.infra.llm_errors import ContentSizeError


def _mock_response(text="OK", stop_reason="end_turn", tool_use_blocks=None):
    """Build a mock Anthropic Message response."""
    content = []
    if tool_use_blocks:
        for tu in tool_use_blocks:
            block = Mock()
            block.type = "tool_use"
            block.id = tu["id"]
            block.name = tu["name"]
            block.input = tu.get("input", {})
            block.text = None
            content.append(block)
    if text:
        text_block = Mock()
        text_block.type = "text"
        text_block.text = text
        content.append(text_block)
    resp = Mock()
    resp.content = content
    resp.stop_reason = stop_reason
    resp.usage = Mock(input_tokens=10, output_tokens=20)
    return resp


async def _collect_events(engine, message):
    """Helper: collect all events from engine.run()."""
    events = []
    async for event in engine.run(message):
        events.append(event)
    return events


def _make_engine(
    llm_responses=None,
    tool_executor=None,
    compressor=None,
    messages=None,
    **config_overrides,
):
    """Helper: build engine with mocked dependencies."""
    mock_llm = AsyncMock()
    if llm_responses:
        mock_llm.create_messages = AsyncMock(side_effect=llm_responses)
    else:
        mock_llm.create_messages = AsyncMock(
            return_value=_mock_response("Hello")
        )

    mock_compressor = compressor or AsyncMock()
    if compressor is None:
        # Default: compress_if_needed returns messages unchanged
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

    config = ConversationConfig(
        model="claude-sonnet-4-20250514",
        system_prompt="You are a helper.",
        tools=[{"name": "test_tool", "description": "test", "input_schema": {"type": "object"}}],
        **config_overrides,
    )

    return ConversationEngine(
        config,
        llm_gateway=mock_llm,
        compressor=mock_compressor,
        tool_executor=tool_executor,
        messages=messages,
    ), mock_llm


# ── Basic Behavior ────────────────────────────────────────────────────────


class TestConversationEngineBasic:

    @pytest.mark.asyncio
    async def test_single_turn_text_response(self):
        engine, _ = _make_engine()
        events = await _collect_events(engine, "Hello")

        # Should yield LLMResponseEvent + TurnCompleteEvent
        event_types = [e.event_type for e in events]
        assert "llm_response" in event_types
        assert "turn_complete" in event_types

    @pytest.mark.asyncio
    async def test_turn_complete_has_end_turn_reason(self):
        engine, _ = _make_engine()
        events = await _collect_events(engine, "Hello")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.END_TURN

    @pytest.mark.asyncio
    async def test_llm_response_contains_text(self):
        engine, _ = _make_engine()
        events = await _collect_events(engine, "Hello")

        llm_event = [e for e in events if e.event_type == "llm_response"][0]
        assert llm_event.text == "Hello"

    @pytest.mark.asyncio
    async def test_messages_state_grows(self):
        engine, _ = _make_engine()
        await _collect_events(engine, "Hello")

        # Should have: user message + assistant response
        assert len(engine.messages) >= 2
        assert engine.messages[0]["role"] == "user"
        assert engine.messages[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_usage_tracked(self):
        engine, _ = _make_engine()
        await _collect_events(engine, "Hello")

        assert engine.total_usage["input_tokens"] > 0
        assert engine.total_usage["output_tokens"] > 0


# ── Multi-Turn Tool Calling ───────────────────────────────────────────────


class TestConversationEngineToolCalling:

    @pytest.mark.asyncio
    async def test_tool_use_triggers_executor(self):
        tool_response = _mock_response(
            text=None,
            stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "search", "input": {"q": "test"}}],
        )
        final_response = _mock_response("Search result: found it")

        executor = AsyncMock(return_value="search result data")
        engine, _ = _make_engine(
            llm_responses=[tool_response, final_response],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "Search for X")

        executor.assert_called_once_with("search", {"q": "test"}, {})
        event_types = [e.event_type for e in events]
        assert "tool_execution" in event_types

    @pytest.mark.asyncio
    async def test_tool_execution_event_has_tool_name(self):
        tool_response = _mock_response(
            text=None,
            stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "list_tasks"}],
        )
        final_response = _mock_response("Done")

        executor = AsyncMock(return_value="tasks list")
        engine, _ = _make_engine(
            llm_responses=[tool_response, final_response],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "List tasks")

        tool_event = [e for e in events if e.event_type == "tool_execution"][0]
        assert tool_event.tool_name == "list_tasks"

    @pytest.mark.asyncio
    async def test_multi_tool_round(self):
        """Multiple tool calls in a single response should all execute."""
        tool_response = _mock_response(
            text=None,
            stop_reason="tool_use",
            tool_use_blocks=[
                {"id": "tu_1", "name": "search"},
                {"id": "tu_2", "name": "read_file"},
            ],
        )
        final_response = _mock_response("Combined result")

        executor = AsyncMock(return_value="data")
        engine, _ = _make_engine(
            llm_responses=[tool_response, final_response],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "Do both")

        assert executor.call_count == 2
        tool_events = [e for e in events if e.event_type == "tool_execution"]
        assert len(tool_events) == 2

    @pytest.mark.asyncio
    async def test_tool_calls_cumulative_count(self):
        """tool_calls counts cumulative across turns (2 per round × 2 rounds = 4)."""
        round1 = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "a"}, {"id": "tu_2", "name": "b"}],
        )
        round2 = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_3", "name": "c"}, {"id": "tu_4", "name": "d"}],
        )
        final = _mock_response("Done")

        executor = AsyncMock(return_value="ok")
        engine, mock_llm = _make_engine(
            llm_responses=[round1, round2, final],
            tool_executor=executor,
            max_tool_calls=10,
        )
        await _collect_events(engine, "Do it")

        assert executor.call_count == 4

    @pytest.mark.asyncio
    async def test_tool_executor_returns_str(self):
        """Engine should accept str return from tool_executor (existing ToolExecutor compat)."""
        tool_response = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "search"}],
        )
        final = _mock_response("Done")

        executor = AsyncMock(return_value='{"results": [1,2,3]}')  # str return
        engine, _ = _make_engine(
            llm_responses=[tool_response, final],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "Search")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.END_TURN


# ── Max Tool Calls ────────────────────────────────────────────────────────


class TestConversationEngineMaxToolCalls:

    @pytest.mark.asyncio
    async def test_max_tool_calls_triggers_final_call(self):
        """When max_tool_calls reached, make one more LLM call with tools included."""
        responses = []
        for i in range(6):
            responses.append(_mock_response(
                text=None, stop_reason="tool_use",
                tool_use_blocks=[{"id": f"tu_{i}", "name": "tool"}],
            ))
        responses.append(_mock_response("Finally done"))

        executor = AsyncMock(return_value="ok")
        engine, mock_llm = _make_engine(
            llm_responses=responses,
            tool_executor=executor,
            max_tool_calls=5,
        )
        events = await _collect_events(engine, "Loop")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.MAX_TOOL_CALLS

    @pytest.mark.asyncio
    async def test_final_call_still_has_tools(self):
        """The final call after max_tool_calls should still include tools param."""
        tool_resp = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "t"}],
        )
        final = _mock_response("Done")

        executor = AsyncMock(return_value="ok")
        engine, mock_llm = _make_engine(
            llm_responses=[tool_resp, final],
            tool_executor=executor,
            max_tool_calls=1,
        )
        await _collect_events(engine, "Go")

        # The last create_messages call should still have tools
        last_call_kwargs = mock_llm.create_messages.call_args_list[-1].kwargs
        assert "tools" in last_call_kwargs
        assert last_call_kwargs["tools"] is not None


# ── Error Recovery ────────────────────────────────────────────────────────


class TestConversationEngineErrorRecovery:

    @pytest.mark.asyncio
    async def test_content_size_triggers_reactive_compact(self):
        """ContentSizeError → reactive_compact → retry once."""
        mock_llm = AsyncMock()
        create_call_count = 0

        async def create_messages_side_effect(**kwargs):
            nonlocal create_call_count
            create_call_count += 1
            if create_call_count == 1:
                raise ContentSizeError("prompt too long")
            return _mock_response("OK after compact")

        mock_llm.create_messages = create_messages_side_effect
        mock_llm.complete = AsyncMock(return_value="Emergency summary.")

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

        config = ConversationConfig(
            model="claude-sonnet-4-20250514",
            system_prompt="test",
            tools=[],
        )
        # Pre-fill with enough messages so reactive_compact's summarize_history works
        existing_history = [
            {"role": "user", "content": f"old message {i}"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"old reply {i}"}
            for i in range(20)
        ]
        engine = ConversationEngine(
            config,
            llm_gateway=mock_llm,
            compressor=mock_compressor,
            tool_executor=None,
            messages=existing_history,
        )

        events = await _collect_events(engine, "Big message")

        event_types = [e.event_type for e in events]
        assert "error_recovery" in event_types
        assert "turn_complete" in event_types
        assert create_call_count == 2

    @pytest.mark.asyncio
    async def test_reactive_compact_only_once_per_run(self):
        """ReactiveCompact should only attempt once — no infinite loop."""
        mock_llm = AsyncMock()
        mock_llm.create_messages = AsyncMock(
            side_effect=ContentSizeError("still too long")
        )
        # reactive_compact calls llm.complete() — give it a summary so it "succeeds"
        # but create_messages still fails → second attempt hits the guard
        mock_llm.complete = AsyncMock(return_value="Summary.")

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

        config = ConversationConfig(model="test", system_prompt="test", tools=[])
        engine = ConversationEngine(
            config, llm_gateway=mock_llm, compressor=mock_compressor, tool_executor=None,
        )

        events = await _collect_events(engine, "Big")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.ERROR


# ── Tool Executor Errors ──────────────────────────────────────────────────


class TestConversationEngineToolErrors:

    @pytest.mark.asyncio
    async def test_tool_exception_yields_error_result(self):
        """Tool executor raises → tool_result with is_error, loop continues."""
        tool_response = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "broken_tool"}],
        )
        final = _mock_response("I see the error, let me try another way")

        executor = AsyncMock(side_effect=RuntimeError("tool crashed"))
        engine, _ = _make_engine(
            llm_responses=[tool_response, final],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "Try broken")

        # Should still complete (engine handles tool error gracefully)
        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.END_TURN


# ── Compression Integration ───────────────────────────────────────────────


class TestConversationEngineCompression:

    @pytest.mark.asyncio
    async def test_compressor_called_before_llm(self):
        """compress_if_needed should be called before each LLM call."""
        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=80, layer="L1",
            )
        )

        engine, mock_llm = _make_engine(compressor=mock_compressor)
        await _collect_events(engine, "Hello")

        mock_compressor.compress_if_needed.assert_called()
        # Compressor called before LLM
        assert mock_compressor.compress_if_needed.call_count >= 1

    @pytest.mark.asyncio
    async def test_compression_event_yielded(self):
        """When compression actually happens (layer != none), yield CompressionEvent."""
        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=1000, tokens_after=500, layer="L1",
            )
        )

        engine, _ = _make_engine(compressor=mock_compressor)
        events = await _collect_events(engine, "Hello")

        event_types = [e.event_type for e in events]
        assert "compression" in event_types


# ── No Tools Mode ─────────────────────────────────────────────────────────


# ── Max Turns Enforcement ────────────────────────────────────────────────


class TestConversationEngineMaxTurns:

    @pytest.mark.asyncio
    async def test_max_turns_enforced(self):
        """Engine should stop after max_turns even if LLM keeps requesting tools."""
        # Each round: LLM requests a tool, tool returns, loop continues
        # With max_turns=3, should stop after 3 turns
        responses = []
        for i in range(10):  # More than max_turns
            responses.append(_mock_response(
                text=None, stop_reason="tool_use",
                tool_use_blocks=[{"id": f"tu_{i}", "name": "tool"}],
            ))
        # Final response after max_turns
        responses.append(_mock_response("Done"))

        executor = AsyncMock(return_value="ok")
        engine, _ = _make_engine(
            llm_responses=responses,
            tool_executor=executor,
            max_turns=3,
            max_tool_calls=100,  # High so it doesn't trigger first
        )
        events = await _collect_events(engine, "Loop forever")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.MAX_TURNS

    @pytest.mark.asyncio
    async def test_max_turns_default_25(self):
        """Default max_turns should be 25."""
        config = ConversationConfig(
            model="test", system_prompt="test", tools=[],
        )
        assert config.max_turns == 25


# ── Tool Error Logging ───────────────────────────────────────────────────


class TestConversationEngineToolErrorLogging:

    @pytest.mark.asyncio
    async def test_tool_exception_is_logged(self):
        """Tool executor exception must be logged with tool_name."""
        tool_response = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "broken_tool"}],
        )
        final = _mock_response("Handled error")

        executor = AsyncMock(side_effect=RuntimeError("db connection failed"))
        engine, _ = _make_engine(
            llm_responses=[tool_response, final],
            tool_executor=executor,
        )

        # Run the engine — it should log the error
        with _capture_logs("infra.conversation_engine") as logs:
            await _collect_events(engine, "Try broken")

        error_logs = [entry for entry in logs if entry["level"] == "error"]
        assert len(error_logs) >= 1
        assert error_logs[0]["kwargs"].get("tool_name") == "broken_tool"

    @pytest.mark.asyncio
    async def test_tool_error_event_has_is_error_true(self):
        """ToolExecutionEvent should have is_error=True when tool raises."""
        tool_response = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "broken"}],
        )
        final = _mock_response("OK")

        executor = AsyncMock(side_effect=ValueError("bad input"))
        engine, _ = _make_engine(
            llm_responses=[tool_response, final],
            tool_executor=executor,
        )
        events = await _collect_events(engine, "Go")

        tool_event = [e for e in events if e.event_type == "tool_execution"][0]
        assert tool_event.is_error is True


# ── ContentSizeError Logging ─────────────────────────────────────────────


class TestConversationEngineContentSizeLogging:

    @pytest.mark.asyncio
    async def test_unrecoverable_content_size_is_logged(self):
        """After reactive_compact fails, error must be logged."""
        mock_llm = AsyncMock()
        mock_llm.create_messages = AsyncMock(
            side_effect=ContentSizeError("still too long")
        )
        mock_llm.complete = AsyncMock(return_value="Summary.")

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

        config = ConversationConfig(model="test", system_prompt="test", tools=[])
        engine = ConversationEngine(
            config, llm_gateway=mock_llm, compressor=mock_compressor,
        )

        with _capture_logs("infra.conversation_engine") as logs:
            events = await _collect_events(engine, "Big")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.ERROR
        error_logs = [entry for entry in logs if entry["level"] == "error"]
        assert len(error_logs) >= 1, "ContentSizeError after reactive_compact should be logged"

    @pytest.mark.asyncio
    async def test_unrecoverable_content_size_has_user_text(self):
        """TurnCompleteEvent after unrecoverable ContentSizeError should have helpful text."""
        mock_llm = AsyncMock()
        mock_llm.create_messages = AsyncMock(
            side_effect=ContentSizeError("too long")
        )
        mock_llm.complete = AsyncMock(return_value="Summary.")

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

        config = ConversationConfig(model="test", system_prompt="test", tools=[])
        engine = ConversationEngine(
            config, llm_gateway=mock_llm, compressor=mock_compressor,
        )
        events = await _collect_events(engine, "Big")

        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.text != "", "Should provide user-facing error message"


# ── Max Tool Calls Final Call Error Handling ──────────────────────────────


class TestConversationEngineMaxToolCallsFinalError:

    @pytest.mark.asyncio
    async def test_content_size_on_final_call_handled(self):
        """ContentSizeError on the final call at max_tool_calls should be handled, not crash."""
        tool_resp = _mock_response(
            text=None, stop_reason="tool_use",
            tool_use_blocks=[{"id": "tu_1", "name": "t"}],
        )

        mock_llm = AsyncMock()
        call_count = 0

        async def side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return tool_resp
            # Final call raises ContentSizeError
            raise ContentSizeError("too long on final")

        mock_llm.create_messages = side_effect

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=100, tokens_after=100, layer="none",
            )
        )

        executor = AsyncMock(return_value="ok")
        config = ConversationConfig(
            model="test", system_prompt="test", tools=[{"name": "t"}],
            max_tool_calls=1,
        )
        engine = ConversationEngine(
            config, llm_gateway=mock_llm, compressor=mock_compressor,
            tool_executor=executor,
        )

        # Should NOT raise — should yield error event
        events = await _collect_events(engine, "Go")
        complete = [e for e in events if e.event_type == "turn_complete"][0]
        assert complete.reason == StopReason.ERROR


# ── Helper ───────────────────────────────────────────────────────────────

from contextlib import contextmanager


@contextmanager
def _capture_logs(logger_name, level=None):
    """Capture structlog calls from the conversation engine logger."""
    captured = []
    original_logger = None

    # Patch the module-level logger in conversation_engine
    import shared.infra.conversation_engine as ce_mod
    original_logger = ce_mod.logger

    class CapturingLogger:
        def __getattr__(self, name):
            def log_method(*args, **kwargs):
                captured.append({"level": name, "args": args, "kwargs": kwargs})
                # Also call original so output still works
                getattr(original_logger, name)(*args, **kwargs)
            return log_method

    ce_mod.logger = CapturingLogger()
    try:
        yield captured
    finally:
        ce_mod.logger = original_logger


# ── No Tools Mode ─────────────────────────────────────────────────────────


class TestConversationEngineNoTools:

    @pytest.mark.asyncio
    async def test_no_tools_single_turn(self):
        """Engine with no tool_executor should work for single-turn."""
        config = ConversationConfig(
            model="test", system_prompt="test", tools=[],
        )
        mock_llm = AsyncMock()
        mock_llm.create_messages = AsyncMock(return_value=_mock_response("Reply"))

        mock_compressor = AsyncMock()
        from shared.infra.context_compressor import CompactionResult
        mock_compressor.compress_if_needed = AsyncMock(
            side_effect=lambda msgs: CompactionResult(
                messages=msgs, tokens_before=10, tokens_after=10, layer="none",
            )
        )

        engine = ConversationEngine(
            config, llm_gateway=mock_llm, compressor=mock_compressor, tool_executor=None,
        )
        events = await _collect_events(engine, "Hi")

        assert any(e.event_type == "turn_complete" for e in events)
