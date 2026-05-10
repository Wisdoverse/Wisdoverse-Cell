"""
Prometheus business metrics for Sync Module.
"""
from prometheus_client import Counter, Gauge, Histogram

SYNC_RUNS = Counter(
    "wisdoverse-cell_sync_runs_total",
    "Total sync runs",
    ["triggered_by", "status"],
)

SYNC_DURATION = Histogram(
    "wisdoverse-cell_sync_duration_seconds",
    "Sync run duration in seconds",
    buckets=(1, 5, 10, 30, 60, 120, 300),
)

SYNC_RECORDS_PROCESSED = Counter(
    "wisdoverse-cell_sync_records_processed_total",
    "Total records processed during sync",
    ["direction"],
)

SYNC_ERRORS = Counter(
    "wisdoverse-cell_sync_errors_total",
    "Total sync errors",
    ["error_type"],
)

DB_POOL_CHECKED_OUT = Gauge(
    "wisdoverse-cell_sync_db_pool_checked_out",
    "Number of currently checked-out DB connections",
)

EVENTS_PUBLISHED = Counter(
    "wisdoverse-cell_sync_events_published_total",
    "Total events published",
    ["event_type"],
)
