"""
Prometheus business metrics for PJM Agent.
"""

from prometheus_client import Counter, Gauge, Histogram

ALERTS_TRIGGERED = Counter(
    "projectcell_pm_alerts_triggered_total",
    "Total PM alerts triggered",
    ["alert_type", "severity"],
)

ALERT_CHECK_DURATION = Histogram(
    "projectcell_pm_alert_check_duration_seconds",
    "Alert check duration in seconds",
    buckets=(0.5, 1, 2, 5, 10, 30),
)

CONFIG_REFRESHES = Counter(
    "projectcell_pm_config_refreshes_total",
    "Total PM config refreshes",
    ["status"],
)

ACTIVE_MEMBERS = Gauge(
    "projectcell_pm_active_members",
    "Number of active members in PM config",
)

EVENTS_PUBLISHED = Counter(
    "projectcell_pm_events_published_total",
    "Total events published",
    ["event_type"],
)
