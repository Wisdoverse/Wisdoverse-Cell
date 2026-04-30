"""Prometheus metrics for QA Agent."""

try:
    from prometheus_client import Counter, Histogram

    ACCEPTANCE_RUNS = Counter(
        "qa_acceptance_runs_total",
        "Total acceptance runs",
        ["agent_name", "trigger", "l0_status"],
    )
    ACCEPTANCE_DURATION = Histogram(
        "qa_acceptance_duration_seconds",
        "Acceptance check duration",
        ["agent_name"],
        buckets=[1, 5, 10, 20, 30, 60, 120],
    )
except ImportError:
    ACCEPTANCE_RUNS = None
    ACCEPTANCE_DURATION = None
