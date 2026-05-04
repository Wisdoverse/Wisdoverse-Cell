"""StructuredSummaryTemplate unit tests.

Coverage:
1. Default template system prompt contains 9 structured sections.
2. Structured input extraction from conversation messages.
3. Structured LLM response parsing.
4. Plain-text fallback when no section markers are found.
5. Custom section configuration.
6. Integration with summarize_history, using structured output as boundary content.
"""

import pytest

from shared.infra.summary_template import (
    DEFAULT_SECTIONS,
    StructuredSummaryTemplate,
    extract_structured_input,
    parse_structured_summary,
)


class TestDefaultSections:
    def test_has_nine_sections(self):
        assert len(DEFAULT_SECTIONS) == 9

    def test_each_section_has_key_and_label(self):
        for section in DEFAULT_SECTIONS:
            assert "key" in section
            assert "label" in section


class TestStructuredSummaryTemplate:
    def test_system_prompt_contains_all_section_labels(self):
        template = StructuredSummaryTemplate()
        prompt = template.system_prompt()
        for section in DEFAULT_SECTIONS:
            assert section["label"] in prompt

    def test_system_prompt_instructs_structured_output(self):
        template = StructuredSummaryTemplate()
        prompt = template.system_prompt()
        # Should instruct LLM to use section markers
        assert "##" in prompt or "【" in prompt

    def test_custom_sections(self):
        custom = [
            {"key": "summary", "label": "总结"},
            {"key": "actions", "label": "行动项"},
        ]
        template = StructuredSummaryTemplate(sections=custom)
        prompt = template.system_prompt()
        assert "总结" in prompt
        assert "行动项" in prompt
        # Default sections should NOT be present
        assert "用户意图" not in prompt


class TestExtractStructuredInput:
    def test_extracts_text_and_tool_names(self):
        messages = [
            {"role": "user", "content": "查询任务"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "tu_1", "name": "list_tasks", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_1", "content": "3 tasks found"},
                ],
            },
            {"role": "assistant", "content": "找到3个任务。"},
        ]
        result = extract_structured_input(messages)
        assert "查询任务" in result
        assert "list_tasks" in result
        assert "找到3个任务" in result

    def test_caps_output_length(self):
        messages = [
            {"role": "user", "content": f"消息{i}" * 100}
            for i in range(100)
        ]
        result = extract_structured_input(messages)
        # Should not exceed ~8000 chars (roughly 2000 tokens)
        assert len(result) <= 10_000

    def test_empty_messages(self):
        result = extract_structured_input([])
        assert result == ""


class TestParseStructuredSummary:
    def test_parses_sections_from_structured_output(self):
        raw = """## 用户意图
用户想查询项目任务进展

## 关键数据
- 3个任务待完成
- 截止日期: 2026-04-05

## 待办事项
1. 更新飞书表格
2. 通知 DRI"""

        sections = parse_structured_summary(raw)
        assert "用户意图" in sections
        assert "关键数据" in sections
        assert "待办事项" in sections
        assert "项目任务进展" in sections["用户意图"]

    def test_returns_raw_when_no_sections_found(self):
        raw = "这是一个简单的摘要，没有任何结构标记。"
        sections = parse_structured_summary(raw)
        # Should return the raw text under a fallback key
        assert "_raw" in sections
        assert sections["_raw"] == raw

    def test_handles_mixed_format(self):
        raw = """## 用户意图
查询进度

一些没有标记的文本

## 当前工作
正在开发 feature X"""

        sections = parse_structured_summary(raw)
        assert "用户意图" in sections
        assert "当前工作" in sections


class TestIntegrationWithCompressor:
    @pytest.mark.asyncio
    async def test_structured_template_produces_richer_boundary(self):
        """When using structured template, the boundary content is multi-section."""
        template = StructuredSummaryTemplate()

        # Simulate what the compressor would do:
        # 1. Build system prompt from template
        system_prompt = template.system_prompt()
        assert len(system_prompt) > 100  # Not a trivial prompt

        # 2. Simulate LLM response with structured output
        mock_response = """## User Intent
Query project tasks and update progress

## Tool Calls
list_tasks, update_progress

## Key Data
- 5 active tasks
- 2 completed tasks

## Open Tasks
Continue updating remaining tasks"""

        # 3. Parse and format as boundary content
        sections = parse_structured_summary(mock_response)
        boundary_content = template.format_boundary(sections)

        assert "[Conversation compacted]" in boundary_content
        assert "User Intent" in boundary_content
        assert "Open Tasks" in boundary_content
