"""
Custom Prometheus business metrics for Wisdoverse Cell.

Usage:
    from .metrics import REQUIREMENTS_EXTRACTED, LLM_REQUESTS
    REQUIREMENTS_EXTRACTED.labels(source="upload").inc()
"""
from prometheus_client import Counter, Gauge, Histogram

# ── Requirements ──────────────────────────────────────────────────────────
REQUIREMENTS_EXTRACTED = Counter(
    "projectcell_requirements_extracted_total",
    "Total requirements extracted",
    ["source"],
)

REQUIREMENTS_CONFIRMED = Counter(
    "projectcell_requirements_confirmed_total",
    "Total requirements confirmed by humans",
)

# ── LLM ───────────────────────────────────────────────────────────────────
LLM_REQUESTS = Counter(
    "projectcell_llm_requests_total",
    "Total LLM API requests",
    ["model", "task_type", "success"],
)

LLM_LATENCY = Histogram(
    "projectcell_llm_latency_seconds",
    "LLM request latency in seconds",
    ["model", "task_type"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60),
)

LLM_TOKENS = Counter(
    "projectcell_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "direction"],
)

# ── Database Pool ─────────────────────────────────────────────────────────
DB_POOL_CHECKED_OUT = Gauge(
    "projectcell_db_pool_checked_out",
    "Number of currently checked-out DB connections",
)

# ── Events ────────────────────────────────────────────────────────────────
EVENTS_PUBLISHED = Counter(
    "projectcell_events_published_total",
    "Total events published to the event bus",
    ["event_type"],
)
