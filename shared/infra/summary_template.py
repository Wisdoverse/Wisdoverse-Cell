"""StructuredSummaryTemplate — 9-section structured summary for context compression.

Inspired by Claude Code's compact system (services/compact/prompt.ts).
Produces structured summaries that preserve more context than flat text.
"""
import re

DEFAULT_SECTIONS: list[dict[str, str]] = [
    {"key": "intent", "label": "用户意图", "hint": "主要请求和目标"},
    {"key": "concepts", "label": "关键概念", "hint": "涉及的技术概念或业务领域"},
    {"key": "tools", "label": "工具调用", "hint": "使用过的工具名称和关键结果"},
    {"key": "data", "label": "关键数据", "hint": "数据片段、查询结果、文件路径"},
    {"key": "errors", "label": "错误与修复", "hint": "遇到的问题和解决方案"},
    {"key": "decisions", "label": "决策记录", "hint": "已做出的决定和原因"},
    {"key": "todos", "label": "待办事项", "hint": "尚未完成的任务"},
    {"key": "current", "label": "当前工作", "hint": "最近正在进行的工作"},
    {"key": "next", "label": "建议下一步", "hint": "建议的下一步操作"},
]

_MAX_INPUT_CHARS = 8000
_SECTION_RE = re.compile(r"^##\s*(.+)$", re.MULTILINE)


class StructuredSummaryTemplate:
    """Builds structured prompts and parses structured LLM responses."""

    def __init__(self, sections: list[dict[str, str]] | None = None):
        self._sections = sections or DEFAULT_SECTIONS

    def system_prompt(self) -> str:
        lines = [
            "你是一个对话压缩助手。请将以下对话内容提取为结构化摘要。",
            "使用以下格式，每个段落用 ## 标题标记。跳过没有内容的段落。",
            "",
        ]
        for s in self._sections:
            hint = s.get("hint", "")
            lines.append(f"## {s['label']}")
            if hint:
                lines.append(f"（{hint}）")
            lines.append("")
        lines.append("保持简洁，每段 1-3 句话。保留工具名称和关键数据。")
        return "\n".join(lines)

    def format_boundary(self, sections: dict[str, str]) -> str:
        """Format parsed sections into a boundary message content string."""
        parts = ["[对话已压缩]"]
        if "_raw" in sections:
            parts.append(sections["_raw"])
        else:
            for s in self._sections:
                label = s["label"]
                if label in sections and sections[label].strip():
                    parts.append(f"## {label}\n{sections[label].strip()}")
        return "\n\n".join(parts)


def extract_structured_input(messages: list[dict]) -> str:
    """Extract human-readable text from messages for structured summarization."""
    if not messages:
        return ""
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            parts.append(f"{role}: {content[:200]}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append(f"{role}: {block.get('text', '')[:200]}")
                elif block.get("type") == "tool_use":
                    parts.append(f"[tool_use: {block.get('name', '?')}]")
                elif block.get("type") == "tool_result":
                    tid = block.get("tool_use_id", "?")
                    parts.append(f"[tool_result: {tid}]")

    text = "\n".join(parts[-50:])
    if len(text) > _MAX_INPUT_CHARS:
        text = text[-_MAX_INPUT_CHARS:]
    return text


def parse_structured_summary(raw: str) -> dict[str, str]:
    """Parse structured LLM output into section dict.

    Returns dict mapping section labels to content.
    Falls back to {"_raw": raw} if no ## markers found.
    """
    matches = list(_SECTION_RE.finditer(raw))
    if not matches:
        return {"_raw": raw}

    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        label = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        content = raw[start:end].strip()
        sections[label] = content

    return sections
