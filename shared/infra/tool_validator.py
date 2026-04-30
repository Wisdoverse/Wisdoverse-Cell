"""Validate LLM-generated tool_use blocks before execution."""

import json

from shared.utils.logger import get_logger

logger = get_logger("tool_validator")

_MAX_TOOL_INPUT_BYTES = 100_000  # 100KB


class ToolValidationError(ValueError):
    """Raised when tool use validation fails."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class ToolValidator:
    """Validates LLM tool_use blocks against registered tool definitions."""

    def __init__(
        self, *, registered_tools: list[dict], max_input_bytes: int = _MAX_TOOL_INPUT_BYTES
    ):
        self._tool_names = {t["name"] for t in registered_tools}
        self._max_input_bytes = max_input_bytes

    def validate_tool_use(self, tool_use: dict) -> None:
        """Validate a single tool_use block. Raises ToolValidationError on failure."""
        name = tool_use.get("name", "")
        if name not in self._tool_names:
            logger.warning("unknown_tool_rejected", tool_name=name)
            raise ToolValidationError("unknown_tool", f"Tool '{name}' is not registered")

        tool_input = tool_use.get("input", {})
        size = len(json.dumps(tool_input, ensure_ascii=False).encode("utf-8"))
        if size > self._max_input_bytes:
            logger.warning("tool_input_too_large", tool_name=name, size=size)
            raise ToolValidationError(
                "tool_input_too_large",
                f"Tool input is {size} bytes, limit is {self._max_input_bytes}",
            )

    def add_tools(self, names: set[str]) -> None:
        """Dynamically add tool names (e.g., after tool_search loads deferred tools)."""
        self._tool_names |= names
