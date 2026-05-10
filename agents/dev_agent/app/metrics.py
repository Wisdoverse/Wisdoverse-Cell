"""Prometheus metrics for dev_agent."""

from prometheus_client import Counter, Gauge, Histogram

# === Business metrics ===
WORKFLOWS_CREATED = Counter(
    "wisdoverse-cell_dev_workflows_created_total",
    "Total workflows created",
)
TASKS_COMPLETED = Counter(
    "wisdoverse-cell_dev_tasks_completed_total",
    "Total tasks completed successfully",
)
TASKS_FAILED = Counter(
    "wisdoverse-cell_dev_tasks_failed_total",
    "Total tasks failed",
    ["reason"],
)
TASK_DURATION = Histogram(
    "wisdoverse-cell_dev_task_duration_seconds",
    "Task duration from creation to completion",
    buckets=(60, 300, 600, 1800, 3600, 7200, 14400),
)
RETRY_COUNT = Counter(
    "wisdoverse-cell_dev_retry_count_total",
    "Total automatic retries",
)
ACTIVE_WORKFLOWS = Gauge(
    "wisdoverse-cell_dev_active_workflows",
    "Currently executing workflows",
)
PENDING_TASKS = Gauge(
    "wisdoverse-cell_dev_pending_tasks_count",
    "Tasks waiting in queue",
)

# === Infrastructure metrics ===
LLM_CALL_DURATION = Histogram(
    "wisdoverse-cell_dev_llm_call_duration_seconds",
    "WorkflowPlanner LLM call latency",
    buckets=(1, 5, 10, 30, 60),
)
LLM_CALL_ERRORS = Counter(
    "wisdoverse-cell_dev_llm_call_errors_total",
    "LLM call failures",
)
FORGE_API_LATENCY = Histogram(
    "wisdoverse-cell_dev_forge_api_latency_seconds",
    "ForgeClient API call latency",
    buckets=(0.1, 0.5, 1, 5, 10, 30),
)
FORGE_POLL_ERRORS = Counter(
    "wisdoverse-cell_dev_forge_poll_errors_total",
    "Polling failures",
)
MR_CREATION_ERRORS = Counter(
    "wisdoverse-cell_dev_mr_creation_errors_total",
    "MR creation failures",
)
CIRCUIT_BREAKER_STATE = Gauge(
    "wisdoverse-cell_dev_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["target"],
)
