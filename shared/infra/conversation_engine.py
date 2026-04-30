"""ConversationEngine — shared multi-turn tool-calling loop.

Inspired by Claude Code v2.1.88 QueryEngine. Manages the LLM conversation
lifecycle with AsyncGenerator-based event streaming, integrated compression,
and category-aware error recovery.

Per-request lifetime: create per request, pass loaded history as messages=.
After run() completes, caller extracts engine.messages and saves.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from shared.infra.context_compressor import (
    ContextCompressor,
    reactive_compact,
)
from shared.infra.llm_errors import ContentSizeError
from shared.utils.logger import get_logger

logger = get_logger("infra.conversation_engine")


# ── Event Types (frozen dataclasses, not Pydantic) ────────────────────────


@dataclass(frozen=True)
class LLMResponseEvent:
    event_type: str = "llm_response"
    text: str = ""
    usage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolExecutionEvent:
    event_type: str = "tool_execution"
    tool_name: str = ""
    tool_use_id: str = ""
    result: str = ""
    is_error: bool = False


@dataclass(frozen=True)
class CompressionEvent:
    event_type: str = "compression"
    layer: str = ""
    tokens_before: int = 0
    tokens_after: int = 0


@dataclass(frozen=True)
class ErrorRecoveryEvent:
    event_type: str = "error_recovery"
    error_type: str = ""
    action: str = ""


@dataclass(frozen=True)
class TurnCompleteEvent:
    event_type: str = "turn_complete"
    reason: str = ""
    text: str = ""


class StopReason(str, Enum):
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    MAX_TOOL_CALLS = "max_tool_calls"
    ABORTED = "aborted"
    ERROR = "error"


# ── Config ────────────────────────────────────────────────────────────────

# Tool executor callback type
ToolExecutorFn = Callable[[str, dict, dict], Awaitable[str | dict]]
ToolsProvider = Callable[[], list[dict]]


@dataclass
class ConversationConfig:
    model: str
    system_prompt: str
    tools: list[dict] | ToolsProvider
    max_tool_calls: int = 10
    max_turns: int = 25
    agent_id: str = "unknown"
    retry_config: Any = None  # LLMRetryConfig, optional


# ── Engine ────────────────────────────────────────────────────────────────

ConversationEvent = (
    LLMResponseEvent
    | ToolExecutionEvent
    | CompressionEvent
    | ErrorRecoveryEvent
    | TurnCompleteEvent
)


class ConversationEngine:
    """Multi-turn conversation engine with tool calling.

    Usage::

        engine = ConversationEngine(config, llm_gateway=gw, compressor=comp, tool_executor=exec)
        async for event in engine.run("user message"):
            handle(event)
        final_messages = engine.messages
    """

    def __init__(
        self,
        config: ConversationConfig,
        *,
        llm_gateway,
        compressor: ContextCompressor,
        tool_executor: ToolExecutorFn | None = None,
        messages: list[dict] | None = None,
    ):
        self._config = config
        self._llm = llm_gateway
        self._compressor = compressor
        self._tool_executor = tool_executor
        self.messages: list[dict] = list(messages) if messages else []
        self.total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    def _current_tools(self) -> list[dict] | None:
        tools = self._config.tools() if callable(self._config.tools) else self._config.tools
        return tools or None

    async def run(
        self, user_message: str
    ) -> AsyncGenerator[ConversationEvent, None]:
        """Main entry point. Yields events for each significant action."""
        self.messages.append({"role": "user", "content": user_message})
        cumulative_tool_calls = 0
        has_reactive_compacted = False

        try:
            turn_count = 0
            while True:
                turn_count += 1
                if turn_count > self._config.max_turns:
                    yield TurnCompleteEvent(reason=StopReason.MAX_TURNS)
                    return

                # Compress before LLM call
                compress_result = await self._compressor.compress_if_needed(
                    self.messages
                )
                self.messages = compress_result.messages

                if compress_result.layer != "none":
                    yield CompressionEvent(
                        layer=compress_result.layer,
                        tokens_before=compress_result.tokens_before,
                        tokens_after=compress_result.tokens_after,
                    )

                # Call LLM
                try:
                    response = await self._llm.create_messages(
                        agent_id=self._config.agent_id,
                        model=self._config.model,
                        max_tokens=4096,
                        system=[{"type": "text", "text": self._config.system_prompt}],
                        messages=self.messages,
                        tools=self._current_tools(),
                    )
                except ContentSizeError:
                    if has_reactive_compacted:
                        logger.error(
                            "content_size_unrecoverable",
                            agent_id=self._config.agent_id,
                            message_count=len(self.messages),
                        )
                        yield TurnCompleteEvent(
                            reason=StopReason.ERROR,
                            text="对话内容过长，压缩后仍超出限制。请使用 /clear 清除历史后重试。",
                        )
                        return
                    has_reactive_compacted = True
                    yield ErrorRecoveryEvent(
                        error_type="content_size",
                        action="reactive_compact",
                    )
                    from shared.infra.context_compressor import ContextCompressorConfig
                    rc_config = (
                        self._compressor._config
                        if isinstance(getattr(self._compressor, "_config", None), ContextCompressorConfig)
                        else ContextCompressorConfig(agent_id=self._config.agent_id)
                    )
                    try:
                        rc_result = await reactive_compact(
                            self.messages,
                            rc_config,
                            llm=self._llm,
                        )
                        self.messages = rc_result.messages
                    except ContentSizeError:
                        logger.error(
                            "reactive_compact_failed",
                            agent_id=self._config.agent_id,
                            message_count=len(self.messages),
                        )
                        yield TurnCompleteEvent(
                            reason=StopReason.ERROR,
                            text="对话内容过长，压缩后仍超出限制。请使用 /clear 清除历史后重试。",
                        )
                        return
                    continue  # Retry LLM call with compacted messages

                # Track usage
                if hasattr(response, "usage"):
                    self.total_usage["input_tokens"] += response.usage.input_tokens
                    self.total_usage["output_tokens"] += response.usage.output_tokens

                # Extract text and tool_use blocks
                text_parts = []
                tool_use_blocks = []
                for block in response.content:
                    if block.type == "text" and block.text:
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)

                text = "".join(text_parts)

                # Yield LLM response event
                if text:
                    yield LLMResponseEvent(
                        text=text,
                        usage={
                            "input_tokens": response.usage.input_tokens,
                            "output_tokens": response.usage.output_tokens,
                        },
                    )

                # No tool use → conversation done
                if response.stop_reason != "tool_use" or not tool_use_blocks:
                    # Append assistant response to messages
                    self.messages.append(
                        {"role": "assistant", "content": text or "(no response)"}
                    )
                    yield TurnCompleteEvent(
                        reason=StopReason.END_TURN, text=text,
                    )
                    return

                # Tool calling
                cumulative_tool_calls += len(tool_use_blocks)

                # Serialize assistant content for history
                serializable_content = []
                for block in response.content:
                    if block.type == "text":
                        serializable_content.append(
                            {"type": "text", "text": block.text}
                        )
                    elif block.type == "tool_use":
                        serializable_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                self.messages.append(
                    {"role": "assistant", "content": serializable_content}
                )

                # Execute tools
                tool_results = []
                for tu_block in tool_use_blocks:
                    tool_result_content: str | dict = ""
                    is_error = False

                    if self._tool_executor:
                        try:
                            tool_result_content = await self._tool_executor(
                                tu_block.name,
                                tu_block.input,
                                {},
                            )
                        except Exception as exc:
                            logger.error(
                                "tool_execution_failed",
                                tool_name=tu_block.name,
                                tool_use_id=tu_block.id,
                                error=str(exc),
                                exc_info=True,
                            )
                            tool_result_content = f"Tool error: {exc}"
                            is_error = True

                    yield ToolExecutionEvent(
                        tool_name=tu_block.name,
                        tool_use_id=tu_block.id,
                        result=str(tool_result_content),
                        is_error=is_error,
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu_block.id,
                        "content": str(tool_result_content),
                        **({"is_error": True} if is_error else {}),
                    })

                self.messages.append({"role": "user", "content": tool_results})

                # Check max_tool_calls
                if cumulative_tool_calls >= self._config.max_tool_calls:
                    # One final call with tools still included
                    try:
                        final_response = await self._llm.create_messages(
                            agent_id=self._config.agent_id,
                            model=self._config.model,
                            max_tokens=4096,
                            system=[
                                {"type": "text", "text": self._config.system_prompt}
                            ],
                            messages=self.messages,
                            tools=self._current_tools(),
                        )
                    except ContentSizeError:
                        logger.warning(
                            "content_size_at_max_tools",
                            agent_id=self._config.agent_id,
                        )
                        yield TurnCompleteEvent(
                            reason=StopReason.ERROR,
                            text="对话内容过长，压缩后仍超出限制。请使用 /clear 清除历史后重试。",
                        )
                        return

                    if hasattr(final_response, "usage"):
                        self.total_usage["input_tokens"] += (
                            final_response.usage.input_tokens
                        )
                        self.total_usage["output_tokens"] += (
                            final_response.usage.output_tokens
                        )

                    final_text = "".join(
                        b.text
                        for b in final_response.content
                        if b.type == "text" and b.text
                    )
                    self.messages.append(
                        {"role": "assistant", "content": final_text or "(limit reached)"}
                    )
                    if final_text:
                        yield LLMResponseEvent(text=final_text)
                    yield TurnCompleteEvent(
                        reason=StopReason.MAX_TOOL_CALLS, text=final_text,
                    )
                    return

                # Continue loop for next LLM call

        finally:
            # Ensure messages state is consistent on cancellation
            pass
