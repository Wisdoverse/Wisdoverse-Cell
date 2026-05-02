"""StructuredSummaryTemplate — 9-section structured summary for context compression.

Inspired by Claude Code's compact system (services/compact/prompt.ts).
Produces structured summaries that preserve more context than flat text.
"""
import re

DEFAULT_SECTIONS: list[dict[str, str]] = [
    {"key": "intent", "label": "User Intent", "hint": "Main request and goal"},
    {"key": "concepts", "label": "Key Concepts", "hint": "Technical or business concepts involved"},
    {"key": "tools", "label": "Tool Calls", "hint": "Tool names used and important results"},
    {"key": "data", "label": "Key Data", "hint": "Data snippets, query results, file paths"},
    {"key": "errors", "label": "Errors And Fixes", "hint": "Problems encountered and solutions applied"},
    {"key": "decisions", "label": "Decisions", "hint": "Decisions made and why"},
    {"key": "todos", "label": "Open Tasks", "hint": "Tasks that are not finished yet"},
    {"key": "current", "label": "Current Work", "hint": "Most recent active work"},
    {"key": "next", "label": "Recommended Next Step", "hint": "Suggested next action"},
]

_MAX_INPUT_CHARS = 8000
_SECTION_RE = re.compile(r"^##\s*(.+)$", re.MULTILINE)


class StructuredSummaryTemplate:
    """Builds structured prompts and parses structured LLM responses."""

    def __init__(self, sections: list[dict[str, str]] | None = None):
        self._sections = sections or DEFAULT_SECTIONS

    def system_prompt(self) -> str:
        lines = [
            "You are a conversation compression assistant. Extract the conversation into a structured summary.",
            "Use the format below. Mark each section with a ## heading. Skip sections with no content.",
            "",
        ]
        for s in self._sections:
            hint = s.get("hint", "")
            lines.append(f"## {s['label']}")
            if hint:
                lines.append(f"({hint})")
            lines.append("")
        lines.append("Keep it concise: 1-3 sentences per section. Preserve tool names and important data.")
        return "\n".join(lines)

    def format_boundary(self, sections: dict[str, str]) -> str:
        """Format parsed sections into a boundary message content string."""
        parts = ["[Conversation compacted]"]
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
