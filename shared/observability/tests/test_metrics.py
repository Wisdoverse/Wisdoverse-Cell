"""Tests for the canonical observability metrics boundary."""

from shared.infra import metrics as infra_metrics
from shared.observability import metrics as observability_metrics


def test_infra_metrics_shim_reuses_observability_collectors() -> None:
    assert infra_metrics.EVENT_QUEUE_LENGTH is observability_metrics.EVENT_QUEUE_LENGTH
    assert infra_metrics.EVENT_PROCESSING_ERRORS is observability_metrics.EVENT_PROCESSING_ERRORS
    assert infra_metrics.LLM_DAILY_COST_DOLLARS is observability_metrics.LLM_DAILY_COST_DOLLARS
    assert (
        infra_metrics.OUTBOX_DISPATCH_EVENTS
        is observability_metrics.OUTBOX_DISPATCH_EVENTS
    )
