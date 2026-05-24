"""Chat-agent business metrics."""

from prometheus_client import Counter

TOOL_CALLS = Counter(
    "wisdoverse-cell_chat_tool_calls_total",
    "Total tool calls executed in the chat service tool-calling loop",
    ["tool_name"],
)
