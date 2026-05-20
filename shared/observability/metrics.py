"""Shared Prometheus metrics for cross-cutting observability concerns.

Metrics defined here are used across multiple agents and services.
Agent-specific metrics live in ``agents/<name>/app/metrics.py``.

Naming convention: ``wisdoverse-cell_{component}_{metric}_{unit}``
"""

from prometheus_client import Counter, Gauge, Histogram

# Event Bus

EVENT_QUEUE_LENGTH = Gauge(
    "wisdoverse-cell_eventbus_queue_length",
    "Current total event queue length across all streams",
)

EVENT_QUEUE_LENGTH_BY_TYPE = Gauge(
    "wisdoverse-cell_eventbus_queue_length_by_type",
    "Current event queue length by stream event type",
    ["event_type"],
)

EVENT_PROCESSING_ERRORS = Counter(
    "wisdoverse-cell_eventbus_processing_errors_total",
    "Total event handler failures in the runtime event loop",
    ["agent_id", "event_type"],
)

EVENT_DLQ_MESSAGES_TOTAL = Counter(
    "wisdoverse-cell_eventbus_dlq_messages_total",
    "Total events written to the event bus dead-letter queue",
    ["failure_stage", "agent_id"],
)

EVENT_DLQ_LENGTH = Gauge(
    "wisdoverse-cell_eventbus_dlq_length",
    "Current event bus dead-letter queue length",
)

# LLM Gateway

LLM_REQUEST_DURATION = Histogram(
    "wisdoverse-cell_llm_request_duration_seconds",
    "LLM API request duration in seconds",
    ["model", "agent_id"],
    buckets=(1, 2, 5, 10, 20, 30, 60, 120),
)

LLM_DAILY_COST_DOLLARS = Gauge(
    "wisdoverse-cell_llm_daily_cost_dollars",
    "Accumulated LLM spend for today in USD (updated after each call)",
)

LLM_COST_DOLLARS_TOTAL = Counter(
    "wisdoverse-cell_llm_cost_dollars_total",
    "Total LLM spend in USD by model and agent",
    ["model", "agent_id"],
)

LLM_TOKEN_TOTAL = Counter(
    "wisdoverse-cell_llm_tokens_total",
    "Total LLM token usage by model, agent, and token type",
    ["model", "agent_id", "token_type"],
)

LLM_ERROR_TOTAL = Counter(
    "wisdoverse-cell_llm_error_total",
    "Total LLM API errors by category",
    ["category", "model", "agent_id"],
)

LLM_FALLBACK_TOTAL = Counter(
    "wisdoverse-cell_llm_fallback_total",
    "Total model fallback events (primary overloaded -> fallback model)",
    ["from_model", "to_model"],
)

# Agent Loop Breaker

LOOP_BREAKER_STATE = Gauge(
    "wisdoverse-cell_loop_breaker_state",
    "Current loop breaker state (0=closed, 1=half_open, 2=open)",
    ["agent_id"],
)

LOOP_BREAKER_TRIPS_TOTAL = Counter(
    "wisdoverse-cell_loop_breaker_trips_total",
    "Total times loop breaker tripped to OPEN",
    ["agent_id", "reason"],
)

LOOP_BREAKER_NO_PROGRESS_ROUNDS = Gauge(
    "wisdoverse-cell_loop_breaker_no_progress_rounds",
    "Current consecutive no-progress round count",
    ["agent_id"],
)

LOOP_BREAKER_OUTPUT_DECLINE_RATIO = Gauge(
    "wisdoverse-cell_loop_breaker_output_decline_ratio",
    "Latest output decline ratio (latest / mean_previous)",
    ["agent_id"],
)

# Outbox Dispatcher
#
# Closes part of Phase 1 audit P0-3 (no outbox lag metrics). Each runtime's
# OutboxDispatcherPlugin should call OUTBOX_DISPATCH_EVENTS.labels(...).inc(N)
# once per cycle and observe OUTBOX_DISPATCH_DURATION_SECONDS on every cycle.

OUTBOX_DISPATCH_EVENTS = Counter(
    "wisdoverse-cell_outbox_dispatch_events_total",
    "Total integration events drained from a runtime's outbox table",
    ["runtime", "outcome"],  # outcome: "published" | "failed" | "total"
)

OUTBOX_DISPATCH_DURATION_SECONDS = Histogram(
    "wisdoverse-cell_outbox_dispatch_duration_seconds",
    "Duration of one outbox dispatcher cycle, per runtime",
    ["runtime"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

OUTBOX_DISPATCH_ERRORS = Counter(
    "wisdoverse-cell_outbox_dispatch_errors_total",
    "Total uncaught errors raised by a runtime's outbox dispatcher loop",
    ["runtime", "error_type"],
)

__all__ = [
    "EVENT_DLQ_LENGTH",
    "EVENT_DLQ_MESSAGES_TOTAL",
    "EVENT_PROCESSING_ERRORS",
    "EVENT_QUEUE_LENGTH",
    "EVENT_QUEUE_LENGTH_BY_TYPE",
    "LLM_COST_DOLLARS_TOTAL",
    "LLM_DAILY_COST_DOLLARS",
    "LLM_ERROR_TOTAL",
    "LLM_FALLBACK_TOTAL",
    "LLM_REQUEST_DURATION",
    "LLM_TOKEN_TOTAL",
    "LOOP_BREAKER_NO_PROGRESS_ROUNDS",
    "LOOP_BREAKER_OUTPUT_DECLINE_RATIO",
    "LOOP_BREAKER_STATE",
    "LOOP_BREAKER_TRIPS_TOTAL",
    "OUTBOX_DISPATCH_DURATION_SECONDS",
    "OUTBOX_DISPATCH_ERRORS",
    "OUTBOX_DISPATCH_EVENTS",
]
