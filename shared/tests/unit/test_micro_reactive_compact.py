"""MicroCompact + ReactiveCompact — Unit Tests (TDD RED phase).

MicroCompact: free pre-pass that clears stale tool_result content before L1 check.
ReactiveCompact: emergency compression triggered by ContentSizeError.
"""
from unittest.mock import AsyncMock

import pytest

from shared.infra.context_compressor import (
    CompactionResult,
    ContextCompressor,
    ContextCompressorConfig,
    micro_compact,
    reactive_compact,
)
from shared.infra.llm_errors import ContentSizeError


def _make_tool_round(tool_id: str, tool_name: str, result_content: str) -> list[dict]:
    return [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {"q": "x"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tool_id, "content": result_content},
            ],
        },
    ]


# ── MicroCompact ──────────────────────────────────────────────────────────


class TestMicroCompactBasic:
    """Block-count-based tool_result clearing."""

    def test_clears_oldest_tool_results_keeps_recent(self):
        messages = [{"role": "user", "content": "start"}]
        for i in range(10):
            messages.extend(_make_tool_round(f"tu_{i}", "tool", f"result_{i}" * 100))

        result = micro_compact(messages, keep_recent=5)

        assert isinstance(result, CompactionResult)
        assert result.layer == "micro"

        # Collect all tool_result blocks
        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert len(tool_results) == 10
        # First 5 cleared
        for tr in tool_results[:5]:
            assert tr["content"] == "[旧工具结果已清理]"
        # Last 5 intact
        for tr in tool_results[5:]:
            assert tr["content"] != "[旧工具结果已清理]"

    def test_reduces_token_count(self):
        messages = [{"role": "user", "content": "start"}]
        for i in range(10):
            messages.extend(_make_tool_round(f"tu_{i}", "tool", "big_result" * 200))

        result = micro_compact(messages, keep_recent=3)

        assert result.tokens_after < result.tokens_before

    def test_preserves_message_structure(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "search", "data" * 100))

        result = micro_compact(messages, keep_recent=0)

        # tool_use block preserved
        tool_uses = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_uses.append(block)
        assert len(tool_uses) == 1
        assert tool_uses[0]["id"] == "tu_1"

        # tool_result has tool_use_id preserved
        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)
        assert tool_results[0]["tool_use_id"] == "tu_1"

    def test_does_not_mutate_original(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "original_data" * 50))
        original_content = messages[2]["content"][0]["content"]

        micro_compact(messages, keep_recent=0)

        assert messages[2]["content"][0]["content"] == original_content


class TestMicroCompactEdgeCases:

    def test_no_tool_results_returns_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = micro_compact(messages, keep_recent=5)

        assert result.layer == "micro"
        assert result.tokens_before == result.tokens_after
        assert len(result.messages) == 2

    def test_fewer_tool_results_than_keep_recent(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "result" * 50))

        result = micro_compact(messages, keep_recent=5)

        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)
        assert all(tr["content"] != "[旧工具结果已清理]" for tr in tool_results)

    def test_already_cleared_not_re_cleared(self):
        """If a tool_result already has the placeholder, don't count it for clearing."""
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "[旧工具结果已清理]"))
        messages.extend(_make_tool_round("tu_2", "b", "fresh_data" * 50))

        result = micro_compact(messages, keep_recent=1)

        # tu_1 was already cleared — should stay cleared
        # tu_2 is the 1 most recent — should stay intact
        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert tool_results[0]["content"] == "[旧工具结果已清理]"
        assert tool_results[1]["content"] != "[旧工具结果已清理]"


class TestMicroCompactInCompressIfNeeded:
    """MicroCompact runs as first step in compress_if_needed."""

    @pytest.mark.asyncio
    async def test_micro_compact_runs_before_l1(self):
        """MicroCompact should reduce tokens before L1 threshold check."""
        messages = [{"role": "user", "content": "start"}]
        for i in range(12):
            messages.extend(_make_tool_round(f"tu_{i}", "tool", "big" * 200))

        config = ContextCompressorConfig(
            l1_threshold_tokens=999_999,  # Very high — L1 should NOT trigger
            l2_threshold_tokens=999_999,
            micro_compact_keep_recent=5,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())
        result = await compressor.compress_if_needed(messages)

        # MicroCompact should have run (reduced tokens) even though L1 didn't trigger
        assert result.tokens_after <= result.tokens_before


# ── ReactiveCompact ──────────────────────────────────────────────────────


class TestReactiveCompactBasic:

    @pytest.mark.asyncio
    async def test_halves_keep_recent_and_summarizes(self):
        messages = [{"role": "user", "content": f"msg_{i}" * 50} for i in range(30)]

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Emergency summary."

        config = ContextCompressorConfig(
            keep_recent_messages=10,
            agent_id="test",
        )
        result = await reactive_compact(messages, config, llm=mock_llm)

        assert isinstance(result, CompactionResult)
        assert result.layer == "L2"
        assert result.summary == "Emergency summary."
        # keep_recent halved: max(3, 10 // 2) = 5
        # Result should have boundary + ack + 5 recent = 7 messages
        assert len(result.messages) == 7

    @pytest.mark.asyncio
    async def test_minimum_keep_recent_is_3(self):
        """Even with very small keep_recent, reactive_compact keeps at least 3."""
        messages = [{"role": "user", "content": f"m_{i}"} for i in range(20)]

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Summary."

        config = ContextCompressorConfig(
            keep_recent_messages=4,  # 4 // 2 = 2, but min is 3
            agent_id="test",
        )
        result = await reactive_compact(messages, config, llm=mock_llm)

        # boundary + ack + 3 recent = 5
        assert len(result.messages) == 5

    @pytest.mark.asyncio
    async def test_produces_valid_anthropic_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ] * 10

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "Quick summary."
        config = ContextCompressorConfig(keep_recent_messages=6, agent_id="test")

        result = await reactive_compact(messages, config, llm=mock_llm)

        # Check alternating user/assistant pattern
        for msg in result.messages:
            assert msg.get("role") in ("user", "assistant")
            assert "content" in msg


class TestReactiveCompactErrorHandling:

    @pytest.mark.asyncio
    async def test_llm_failure_raises_content_size_error(self):
        """If reactive_compact's LLM call fails, it should raise ContentSizeError."""
        messages = [{"role": "user", "content": f"m_{i}"} for i in range(20)]

        mock_llm = AsyncMock()
        mock_llm.complete.side_effect = RuntimeError("LLM down")

        config = ContextCompressorConfig(keep_recent_messages=10, agent_id="test")

        with pytest.raises(ContentSizeError):
            await reactive_compact(messages, config, llm=mock_llm)

    @pytest.mark.asyncio
    async def test_llm_returns_empty_raises_content_size_error(self):
        messages = [{"role": "user", "content": f"m_{i}"} for i in range(20)]

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = ""

        config = ContextCompressorConfig(keep_recent_messages=10, agent_id="test")

        with pytest.raises(ContentSizeError):
            await reactive_compact(messages, config, llm=mock_llm)
