"""Token estimator unit tests."""

import json

from shared.infra.token_estimator import estimate_tokens


class TestEstimateTokensBasic:
    """Basic token estimation for message arrays."""

    def test_empty_messages_returns_zero(self):
        result = estimate_tokens([])
        assert result.total_tokens == 0
        assert result.tool_result_tokens == 0
        assert result.text_tokens == 0

    def test_single_text_message(self):
        messages = [{"role": "user", "content": "Hello world"}]
        result = estimate_tokens(messages)
        assert result.total_tokens > 0
        assert result.text_tokens > 0
        assert result.tool_result_tokens == 0

    def test_estimate_proportional_to_content_length(self):
        short = [{"role": "user", "content": "Hi"}]
        long = [{"role": "user", "content": "x" * 1000}]
        short_result = estimate_tokens(short)
        long_result = estimate_tokens(long)
        assert long_result.total_tokens > short_result.total_tokens


class TestEstimateTokensToolMessages:
    """Token estimation with tool_use and tool_result blocks."""

    def test_tool_result_tokens_separated(self):
        messages = [
            {"role": "user", "content": "query tasks"},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "list_tasks",
                        "input": {"status": "open"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_1",
                        "content": json.dumps(
                            [{"id": i, "title": f"Task {i}"} for i in range(50)]
                        ),
                    }
                ],
            },
        ]
        result = estimate_tokens(messages)
        assert result.tool_result_tokens > 0
        assert result.text_tokens > 0
        assert result.total_tokens == result.text_tokens + result.tool_result_tokens

    def test_multiple_tool_results_accumulated(self):
        messages = [
            {"role": "user", "content": "do stuff"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "a", "input": {}},
                    {"type": "tool_use", "id": "tu_2", "name": "b", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "r" * 500},
                    {"type": "tool_result", "tool_use_id": "tu_2", "content": "s" * 500},
                ],
            },
        ]
        result = estimate_tokens(messages)
        assert result.tool_result_tokens > 0


class TestEstimateTokensEdgeCases:
    """Edge cases for token estimation."""

    def test_chinese_content_accounts_for_multibyte(self):
        messages = [{"role": "user", "content": "你好世界" * 100}]
        result = estimate_tokens(messages)
        assert result.total_tokens > 0

    def test_deeply_nested_tool_result(self):
        nested = {"a": {"b": {"c": [{"d": "value"} for _ in range(100)]}}}
        messages = [
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_1", "content": json.dumps(nested)},
            ]},
        ]
        result = estimate_tokens(messages)
        assert result.total_tokens > 0

    def test_content_as_string_vs_list_both_handled(self):
        str_msg = [{"role": "assistant", "content": "hello"}]
        list_msg = [{"role": "assistant", "content": [{"type": "text", "text": "hello"}]}]
        str_result = estimate_tokens(str_msg)
        list_result = estimate_tokens(list_msg)
        # Both should produce non-zero results
        assert str_result.total_tokens > 0
        assert list_result.total_tokens > 0
