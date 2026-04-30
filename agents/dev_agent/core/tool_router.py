"""Rule engine + config override for AI tool assignment."""
from __future__ import annotations

import fnmatch

from ..models.schemas import ToolRule, WorkflowNode

DEFAULT_RULES = [
    ToolRule(match_tags=["plan", "review", "architecture"], tool="codex", priority=10),
    ToolRule(match_tags=["implement", "fix", "refactor", "core"], tool="claude", priority=5),
    ToolRule(match_tags=["models", "api", "tests", "docs", "config"], tool="gemini", priority=5),
    ToolRule(match_tags=["acceptance", "packaging"], tool="claude", priority=5),
]
DEFAULT_TOOL = "claude"


class ToolRouter:
    def __init__(self, rules: list[ToolRule] | None = None):
        self._rules = sorted(rules or DEFAULT_RULES, key=lambda r: -r.priority)
        self._overrides: dict[str, str] = {}

    def set_overrides(self, overrides: dict[str, str]) -> None:
        self._overrides = overrides

    def route(self, node: WorkflowNode) -> str:
        for pattern, tool in self._overrides.items():
            if fnmatch.fnmatch(node.name, pattern):
                return tool
        node_tags = set(node.config.get("tags", []))
        for rule in self._rules:
            if node_tags & set(rule.match_tags):
                return rule.tool
        return DEFAULT_TOOL
