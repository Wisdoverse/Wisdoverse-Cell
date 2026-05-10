"""Shared Prometheus metrics for cross-cutting concerns.

Metrics defined here are used across multiple agents and services.
Agent-specific metrics live in ``agents/<name>/app/metrics.py``.

Naming convention: ``wisdoverse-cell_{component}_{metric}_{unit}``
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Event Bus ────────────────────────────────────────────────────────────────

EVENT_QUEUE_LENGTH = Gauge(
    "wisdoverse-cell_eventbus_queue_length",
    "Current total event queue length across all streams",
)

EVENT_PROCESSING_ERRORS = Counter(
    "wisdoverse-cell_eventbus_processing_errors_total",
    "Total event handler failures in the runtime event loop",
    ["agent_id", "event_type"],
)

# ── LLM Gateway ──────────────────────────────────────────────────────────────

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
    "Total model fallback events (primary overloaded → fallback model)",
    ["from_model", "to_model"],
)

# ── Agent Loop Breaker ──────────────────────────────────────────────────────

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
