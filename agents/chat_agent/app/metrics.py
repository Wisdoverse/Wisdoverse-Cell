"""
Prometheus business metrics for Chat Agent.
"""
from prometheus_client import Counter, Histogram

MESSAGES_RECEIVED = Counter(
    "projectcell_chat_messages_received_total",
    "Total messages received from Feishu",
    ["chat_type"],
)

MESSAGES_REPLIED = Counter(
    "projectcell_chat_messages_replied_total",
    "Total messages replied",
    ["status"],
)

CHAT_LATENCY = Histogram(
    "projectcell_chat_latency_seconds",
    "Chat response latency in seconds",
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)

MESSAGE_DEDUP = Counter(
    "projectcell_chat_message_dedup_total",
    "Total deduplicated messages",
)

EVENTS_PUBLISHED = Counter(
    "projectcell_chat_events_published_total",
    "Total events published",
    ["event_type"],
)

TOOL_CALLS = Counter(
    "projectcell_chat_tool_calls_total",
    "Total tool calls executed in the chat service tool-calling loop",
    ["tool_name"],
)
