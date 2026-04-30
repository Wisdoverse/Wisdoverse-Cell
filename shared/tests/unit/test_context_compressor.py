"""Context compressor unit tests — L1 tool-result trimming + L2 summarization."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from shared.infra.context_compressor import (
    CompactionResult,
    ContextCompressor,
    ContextCompressorConfig,
    find_snip_indices,
    find_split_point,
    summarize_history,
    trim_tool_results,
)


def _make_tool_round(tool_id: str, tool_name: str, result_content: str) -> list[dict]:
    """Helper: create a tool_use + tool_result message pair."""
    return [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name,
                    "input": {"query": "test"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result_content,
                }
            ],
        },
    ]


class TestTrimToolResultsBasic:
    """L1: Clear old tool_result content, keep recent ones."""

    def test_trims_old_tool_results_keeps_recent(self):
        messages = [{"role": "user", "content": "start"}]
        for i in range(10):
            messages.extend(
                _make_tool_round(f"tu_{i}", "list_tasks", f"result_{i}" * 100)
            )

        result, _snip = trim_tool_results(messages, keep_recent=5)

        assert isinstance(result, CompactionResult)
        assert result.layer == "L1"
        assert result.tokens_before > result.tokens_after

        # Check: oldest 5 tool_results are cleared
        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        # First 5 should be cleared
        for tr in tool_results[:5]:
            assert tr["content"] == "[旧工具结果已清理]"
        # Last 5 should be intact
        for tr in tool_results[5:]:
            assert tr["content"] != "[旧工具结果已清理]"

    def test_preserves_tool_use_blocks(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "search", "big result" * 200))

        result, _snip = trim_tool_results(messages, keep_recent=0)

        tool_uses = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_uses.append(block)

        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "search"
        assert tool_uses[0]["id"] == "tu_1"

    def test_preserves_tool_result_structure(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "data" * 100))

        result, _snip = trim_tool_results(messages, keep_recent=0)

        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert len(tool_results) == 1
        assert tool_results[0]["type"] == "tool_result"
        assert tool_results[0]["tool_use_id"] == "tu_1"


class TestTrimToolResultsEdgeCases:
    """Edge cases for L1 trimming."""

    def test_no_tool_results_returns_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        original = deepcopy(messages)
        result, _snip = trim_tool_results(messages, keep_recent=5)

        assert result.messages == original
        assert result.layer == "L1"
        assert result.tokens_before == result.tokens_after

    def test_fewer_tool_results_than_keep_recent(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "result" * 50))

        result, _snip = trim_tool_results(messages, keep_recent=5)

        # Only 1 tool_result, keep_recent=5 → nothing trimmed
        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert all(tr["content"] != "[旧工具结果已清理]" for tr in tool_results)

    def test_error_tool_results_also_trimmed(self):
        messages = [
            {"role": "user", "content": "start"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "a", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_1",
                        "content": "Error: timeout",
                        "is_error": True,
                    },
                ],
            },
        ]
        result, _snip = trim_tool_results(messages, keep_recent=0)

        tool_results = []
        for msg in result.messages:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_results.append(block)

        assert tool_results[0]["content"] == "[旧工具结果已清理]"

    def test_does_not_mutate_original_messages(self):
        messages = [{"role": "user", "content": "start"}]
        messages.extend(_make_tool_round("tu_1", "a", "original_data"))
        original_content = messages[2]["content"][0]["content"]

        trim_tool_results(messages, keep_recent=0)

        assert messages[2]["content"][0]["content"] == original_content


# ── L2: LLM Summarization ──────────────────────────────────────────────────


class TestSummarizeHistoryBasic:
    """L2: Summarize old messages using LLM, keep recent ones."""

    @pytest.mark.asyncio
    async def test_summarizes_old_messages_keeps_recent(self):
        messages = [
            {"role": "user", "content": f"message_{i}"}
            for i in range(20)
        ]
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "用户讨论了20个话题。"

        config = ContextCompressorConfig(keep_recent_messages=5, agent_id="test")
        result = await summarize_history(messages, config, llm=mock_llm)

        assert isinstance(result, CompactionResult)
        assert result.layer == "L2"
        assert result.summary == "用户讨论了20个话题。"
        # Should have: boundary + ack + 5 recent = 7 messages
        assert len(result.messages) == 7
        # First message is the compact boundary
        assert "[对话已压缩]" in result.messages[0]["content"]
        # Second is assistant acknowledgment
        assert result.messages[1]["role"] == "assistant"
        # Last 5 are the recent messages
        for i, msg in enumerate(result.messages[2:]):
            assert msg["content"] == f"message_{i + 15}"

    @pytest.mark.asyncio
    async def test_llm_called_with_summary_prompt(self):
        messages = [
            {"role": "user", "content": "task query"},
            {"role": "assistant", "content": "here are your tasks"},
        ] * 10
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "摘要内容"

        config = ContextCompressorConfig(keep_recent_messages=3, agent_id="test")
        await summarize_history(messages, config, llm=mock_llm)

        mock_llm.complete.assert_called_once()
        call_kwargs = mock_llm.complete.call_args.kwargs
        assert call_kwargs["task_type"] == "summarize"
        assert "概括" in call_kwargs["system_prompt"] or "摘要" in call_kwargs["system_prompt"]

    @pytest.mark.asyncio
    async def test_tokens_decrease_after_summarization(self):
        messages = [
            {"role": "user", "content": "x" * 500}
            for _ in range(30)
        ]
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "短摘要。"

        config = ContextCompressorConfig(keep_recent_messages=5, agent_id="test")
        result = await summarize_history(messages, config, llm=mock_llm)

        assert result.tokens_after < result.tokens_before


class TestSummarizeHistoryErrorHandling:
    """Error handling for L2 summarization."""

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_recent_messages(self):
        messages = [
            {"role": "user", "content": f"msg_{i}"}
            for i in range(20)
        ]
        mock_llm = AsyncMock()
        mock_llm.complete.side_effect = RuntimeError("LLM unavailable")

        config = ContextCompressorConfig(keep_recent_messages=10, agent_id="test")
        result = await summarize_history(messages, config, llm=mock_llm)

        assert result.layer == "L2"
        assert result.summary is None
        # Fallback: just the recent 10 messages
        assert len(result.messages) == 10
        for i, msg in enumerate(result.messages):
            assert msg["content"] == f"msg_{i + 10}"

    @pytest.mark.asyncio
    async def test_llm_returns_empty_falls_back(self):
        messages = [
            {"role": "user", "content": f"msg_{i}"}
            for i in range(20)
        ]
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = ""

        config = ContextCompressorConfig(keep_recent_messages=10, agent_id="test")
        result = await summarize_history(messages, config, llm=mock_llm)

        assert result.summary is None
        assert len(result.messages) == 10


class TestSummarizeHistoryEdgeCases:
    """Edge cases for L2 summarization."""

    @pytest.mark.asyncio
    async def test_all_messages_within_keep_recent(self):
        messages = [
            {"role": "user", "content": "short"},
            {"role": "assistant", "content": "reply"},
        ]
        mock_llm = AsyncMock()
        config = ContextCompressorConfig(keep_recent_messages=10, agent_id="test")
        result = await summarize_history(messages, config, llm=mock_llm)

        # Nothing to summarize — all messages are recent
        mock_llm.complete.assert_not_called()
        assert result.messages == messages
        assert result.layer == "L2"

    @pytest.mark.asyncio
    async def test_tool_messages_extracted_as_tool_names(self):
        messages = [
            {"role": "user", "content": "start"},
            *_make_tool_round("tu_1", "list_bitable_records", '{"records": []}'),
            {"role": "assistant", "content": "查询完毕"},
        ] * 5
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "用户多次查询飞书表格。"

        config = ContextCompressorConfig(keep_recent_messages=2, agent_id="test")
        await summarize_history(messages, config, llm=mock_llm)

        # The summary prompt should mention tool names
        prompt_text = mock_llm.complete.call_args.kwargs["prompt"]
        assert "list_bitable_records" in prompt_text


# ── Orchestrator: compress_if_needed ────────────────────────────────────────


class TestCompressIfNeededOrchestrator:
    """Orchestrator runs L1 then L2 as needed."""

    @pytest.mark.asyncio
    async def test_below_l1_threshold_no_compression(self):
        messages = [{"role": "user", "content": "short"}]
        mock_llm = AsyncMock()
        config = ContextCompressorConfig(
            l1_threshold_tokens=50_000, l2_threshold_tokens=80_000, agent_id="test"
        )
        compressor = ContextCompressor(config, llm=mock_llm)
        result = await compressor.compress_if_needed(messages)

        assert result.layer == "none"
        assert result.messages == messages
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_above_l1_below_l2_runs_l1_only(self):
        # Build messages with big tool_results to exceed L1 threshold
        messages = [{"role": "user", "content": "start"}]
        for i in range(20):
            messages.extend(
                _make_tool_round(f"tu_{i}", "big_tool", "x" * 2000)
            )

        mock_llm = AsyncMock()
        config = ContextCompressorConfig(
            l1_threshold_tokens=100,  # Very low to trigger
            l2_threshold_tokens=999_999,  # Very high to skip
            keep_recent_tool_results=5,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=mock_llm)
        result = await compressor.compress_if_needed(messages)

        assert result.layer == "L1"
        assert result.tokens_after < result.tokens_before
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_above_l2_runs_l1_then_l2(self):
        messages = [{"role": "user", "content": f"msg_{i}" * 50} for i in range(30)]
        for i in range(10):
            messages.extend(
                _make_tool_round(f"tu_{i}", "tool", "result" * 500)
            )

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "短摘要。"

        config = ContextCompressorConfig(
            l1_threshold_tokens=100,  # Trigger L1
            l2_threshold_tokens=200,  # Trigger L2
            keep_recent_messages=5,
            keep_recent_tool_results=3,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=mock_llm)
        result = await compressor.compress_if_needed(messages)

        assert result.layer == "L2"
        assert result.tokens_after < result.tokens_before
        mock_llm.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_l1_sufficient_skips_l2(self):
        # Many tool results but few text messages
        messages = [{"role": "user", "content": "start"}]
        for i in range(10):
            messages.extend(
                _make_tool_round(f"tu_{i}", "tool", "huge_result" * 1000)
            )

        mock_llm = AsyncMock()
        config = ContextCompressorConfig(
            l1_threshold_tokens=100,  # Trigger L1
            l2_threshold_tokens=999_999,  # High enough that L1 reduces below this
            keep_recent_tool_results=2,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=mock_llm)
        result = await compressor.compress_if_needed(messages)

        assert result.layer == "L1"
        mock_llm.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_compact_restore_callback_called(self):
        messages = [{"role": "user", "content": f"msg_{i}" * 100} for i in range(30)]

        mock_llm = AsyncMock()
        mock_llm.complete.return_value = "摘要。"

        extra_context = [{"role": "user", "content": "[系统上下文] 当前项目状态..."}]
        restore_fn = AsyncMock(return_value=extra_context)

        config = ContextCompressorConfig(
            l1_threshold_tokens=100,
            l2_threshold_tokens=200,
            keep_recent_messages=5,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=mock_llm, post_compact_restore=restore_fn)
        result = await compressor.compress_if_needed(messages)

        restore_fn.assert_called_once()
        # The extra context should be appended
        assert result.messages[-1]["content"] == "[系统上下文] 当前项目状态..."

    @pytest.mark.asyncio
    async def test_l2_fails_returns_l1_result(self):
        messages = [{"role": "user", "content": f"msg_{i}" * 100} for i in range(30)]
        for i in range(10):
            messages.extend(_make_tool_round(f"tu_{i}", "t", "r" * 500))

        mock_llm = AsyncMock()
        mock_llm.complete.side_effect = RuntimeError("LLM down")

        config = ContextCompressorConfig(
            l1_threshold_tokens=100,
            l2_threshold_tokens=200,
            keep_recent_messages=5,
            keep_recent_tool_results=3,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=mock_llm)
        result = await compressor.compress_if_needed(messages)

        # L2 failed, but L1 should have run successfully
        assert result.layer == "L2"  # L2 was attempted
        assert result.summary is None  # But failed


# ── Part A: Dynamic Thresholds ────────────────────────────────────────────────


class TestDynamicThresholds:
    """Dynamic threshold computation from max_context_tokens."""

    def test_auto_threshold_from_max_context(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_ratio=0.4,
            l2_ratio=0.6,
        )
        assert config.effective_l1_threshold == 80_000
        assert config.effective_l2_threshold == 120_000

    def test_explicit_threshold_overrides_auto(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_threshold_tokens=50_000,
            l2_threshold_tokens=90_000,
        )
        assert config.effective_l1_threshold == 50_000
        assert config.effective_l2_threshold == 90_000

    def test_no_max_context_uses_explicit_defaults(self):
        config = ContextCompressorConfig()
        assert config.effective_l1_threshold == 40_000
        assert config.effective_l2_threshold == 70_000

    def test_partial_override_l1_only(self):
        config = ContextCompressorConfig(
            max_context_tokens=200_000,
            l1_threshold_tokens=30_000,
        )
        # l1 was explicitly overridden → 30K
        assert config.effective_l1_threshold == 30_000
        # l2 was NOT overridden (still default 70K) → auto = 200K * 0.6 = 120K
        assert config.effective_l2_threshold == 120_000


# ── Part B: Snip Boundaries ───────────────────────────────────────────────────


class TestSnipBoundaries:
    """Snip index detection and split-point selection."""

    def test_snip_indices_after_tool_sequences(self):
        messages = [
            {"role": "user", "content": "start"},
            *_make_tool_round("tu_0", "search", "result_0"),
            *_make_tool_round("tu_1", "read", "result_1"),
            {"role": "assistant", "content": "done"},
        ]
        # Messages layout:
        # 0: user "start"
        # 1: assistant tool_use tu_0
        # 2: user tool_result tu_0  ← snip
        # 3: assistant tool_use tu_1
        # 4: user tool_result tu_1  ← snip
        # 5: assistant "done"
        snips = find_snip_indices(messages)
        assert snips == [3, 5]

    def test_no_snip_in_pure_text(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "bye"},
        ]
        assert find_snip_indices(messages) == []

    def test_split_point_at_snip(self):
        # 10 messages, snips at [4, 6], keep=3, target=10-3=7
        # Largest snip <= 7 is 6
        assert find_split_point(10, [4, 6], keep_recent=3) == 6

    def test_split_point_fallback_when_no_snip(self):
        # No snip indices → fallback to 10-3=7
        assert find_split_point(10, [], keep_recent=3) == 7

    def test_split_point_snip_beyond_target_uses_fallback(self):
        # snip at [9], target = 10-3 = 7, snip 9 > 7 → fallback 7
        assert find_split_point(10, [9], keep_recent=3) == 7

    def test_no_orphaned_tool_use_after_split(self):
        """Splitting at a snip boundary must not leave an orphaned tool_use
        at the start of the recent portion."""
        messages = [
            {"role": "user", "content": "start"},
            *_make_tool_round("tu_0", "search", "r0"),
            *_make_tool_round("tu_1", "read", "r1"),
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "follow-up"},
            {"role": "assistant", "content": "reply"},
        ]
        # 0: user
        # 1: assistant tool_use tu_0
        # 2: user tool_result tu_0  ← snip
        # 3: assistant tool_use tu_1
        # 4: user tool_result tu_1  ← snip
        # 5: user "question"
        # 6: assistant "answer"
        # 7: user "follow-up"
        # 8: assistant "reply"
        snips = find_snip_indices(messages)
        split = find_split_point(len(messages), snips, keep_recent=4)
        recent = messages[split:]
        # Verify no orphaned tool_use (a tool_use without its matching tool_result)
        for msg in recent:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block["id"]
                        # Must find matching tool_result in recent
                        found = False
                        for other in recent:
                            other_c = other.get("content")
                            if isinstance(other_c, list):
                                for ob in other_c:
                                    if (
                                        isinstance(ob, dict)
                                        and ob.get("type") == "tool_result"
                                        and ob.get("tool_use_id") == tool_id
                                    ):
                                        found = True
                        assert found, f"Orphaned tool_use {tool_id} after split"


# ── Unit 1: Auto-Compact Gate + Compression Circuit Breaker ──────────────


class TestAutoCompactGate:
    """compress_if_needed should skip compression when utilization < auto_compact_ratio."""

    @pytest.mark.asyncio
    async def test_skips_when_under_threshold(self):
        """Below 85% utilization → compress_if_needed returns immediately."""
        config = ContextCompressorConfig(
            max_context_tokens=100_000,
            auto_compact_ratio=0.85,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())
        messages = [{"role": "user", "content": "hi"}]
        result = await compressor.compress_if_needed(messages)
        assert result.layer == "none"

    @pytest.mark.asyncio
    async def test_proceeds_when_over_threshold(self):
        """Above 85% utilization → compression runs (at least L1 check)."""
        config = ContextCompressorConfig(
            max_context_tokens=1000,
            auto_compact_ratio=0.85,
            l1_threshold_tokens=500,
            l2_threshold_tokens=900,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())
        big_content = "x" * 4000  # ~1000 tokens at bytes/4
        messages = [{"role": "user", "content": big_content}]
        result = await compressor.compress_if_needed(messages)
        assert result.layer != "none"

    @pytest.mark.asyncio
    async def test_no_max_context_tokens_skips_gate(self):
        """When max_context_tokens is None, auto-compact gate is skipped."""
        config = ContextCompressorConfig(
            max_context_tokens=None,
            auto_compact_ratio=0.85,
            l1_threshold_tokens=10,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())
        messages = [{"role": "user", "content": "hello world test message"}]
        result = await compressor.compress_if_needed(messages)
        assert result.layer == "L1"

    @pytest.mark.asyncio
    async def test_auto_compact_ratio_one_never_triggers(self):
        """auto_compact_ratio=1.0 → never auto-triggers."""
        config = ContextCompressorConfig(
            max_context_tokens=100,
            auto_compact_ratio=1.0,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())
        messages = [{"role": "user", "content": "short"}]
        result = await compressor.compress_if_needed(messages)
        assert result.layer == "none"


class TestCompressionCircuitBreaker:
    """L2 failures should trip a circuit breaker after 3 consecutive failures."""

    @pytest.mark.asyncio
    async def test_three_failures_skips_l2(self):
        """After 3 consecutive L2 failures, L2 is skipped — returns L1 result."""
        config = ContextCompressorConfig(
            l1_threshold_tokens=10,
            l2_threshold_tokens=20,
            keep_recent_messages=1,
            agent_id="test",
        )
        mock_llm = AsyncMock()
        # Return None to simulate LLM failure (summarize_history catches and returns None summary)
        mock_llm.complete = AsyncMock(return_value=None)
        compressor = ContextCompressor(config, llm=mock_llm)

        big_messages = [{"role": "user", "content": "x" * 400}]

        # Fail 3 times (summary=None = failure)
        for _ in range(3):
            result = await compressor.compress_if_needed(big_messages)
            assert result.summary is None

        # 4th call: circuit breaker should skip L2 entirely
        mock_llm.complete.reset_mock()
        result = await compressor.compress_if_needed(big_messages)
        assert result.layer == "L1"
        # LLM should NOT be called on 4th attempt
        mock_llm.complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_success_resets_failure_counter(self):
        """A successful L2 resets the consecutive failure counter."""
        config = ContextCompressorConfig(
            l1_threshold_tokens=10,
            l2_threshold_tokens=20,
            keep_recent_messages=1,
            agent_id="test",
        )
        call_count = 0

        async def flaky_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return None  # Failure: summarize_history returns None summary
            return "Summary of conversation."

        mock_llm = AsyncMock()
        mock_llm.complete = flaky_complete
        compressor = ContextCompressor(config, llm=mock_llm)

        # Need multiple messages so summarize_history actually calls LLM
        big_messages = [
            {"role": "user", "content": "x" * 200},
            {"role": "assistant", "content": "y" * 200},
            {"role": "user", "content": "z" * 200},
        ]

        # Fail twice (summary=None)
        await compressor.compress_if_needed(big_messages)
        await compressor.compress_if_needed(big_messages)
        assert compressor.stats.consecutive_l2_failures == 2

        # 3rd call succeeds → resets counter
        result = await compressor.compress_if_needed(big_messages)
        assert result.summary is not None
        assert compressor.stats.consecutive_l2_failures == 0


class TestCompressionStats:
    """CompressionStats tracks cumulative compression data."""

    @pytest.mark.asyncio
    async def test_stats_track_compressions(self):
        config = ContextCompressorConfig(
            l1_threshold_tokens=10,
            l2_threshold_tokens=100_000,
            agent_id="test",
        )
        compressor = ContextCompressor(config, llm=AsyncMock())

        messages = [{"role": "user", "content": "x" * 400}]
        await compressor.compress_if_needed(messages)

        stats = compressor.stats
        assert stats.total_compressions >= 1
        assert stats.total_tokens_saved >= 0
        assert stats.last_layer == "L1"
