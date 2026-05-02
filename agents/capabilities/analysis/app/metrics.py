"""
Prometheus business metrics for Analysis Agent.
"""
from prometheus_client import Counter, Histogram

REPORTS_GENERATED = Counter(
    "projectcell_reports_generated_total",
    "Total reports generated",
    ["report_type"],
)

REPORT_DURATION = Histogram(
    "projectcell_report_duration_seconds",
    "Report generation duration in seconds",
    ["report_type"],
    buckets=(1, 5, 10, 30, 60, 120),
)

RISKS_DETECTED = Counter(
    "projectcell_risks_detected_total",
    "Total risks detected",
    ["risk_level"],
)

QUALITY_EVALUATIONS = Counter(
    "projectcell_quality_evaluations_total",
    "Total quality evaluations performed",
    ["quality_grade"],
)

EVENTS_PUBLISHED = Counter(
    "projectcell_analysis_events_published_total",
    "Total events published",
    ["event_type"],
)
