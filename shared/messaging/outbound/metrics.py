"""Delivery metrics -- module-level prometheus counters.

Follows the project pattern from agents/requirement_manager/app/metrics.py.
Module-level to avoid prometheus_client duplicate registration errors.
"""
from prometheus_client import Counter, Histogram

OUTBOUND_TOTAL = Counter(
    "delivery_outbound_total",
    "Total outbound message attempts",
    ["channel"],
)

OUTBOUND_SUCCESS = Counter(
    "delivery_outbound_success",
    "Successful outbound message deliveries",
    ["channel"],
)

OUTBOUND_ERRORS = Counter(
    "delivery_outbound_errors",
    "Failed outbound message deliveries",
    ["channel", "error"],
)

OUTBOUND_LATENCY = Histogram(
    "delivery_outbound_latency_seconds",
    "Outbound message delivery latency",
    ["channel"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
