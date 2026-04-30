"""Verify delivery metrics are module-level singletons."""
from shared.messaging.outbound.metrics import (
    OUTBOUND_ERRORS,
    OUTBOUND_LATENCY,
    OUTBOUND_SUCCESS,
    OUTBOUND_TOTAL,
)


def test_metrics_are_importable():
    assert OUTBOUND_TOTAL is not None
    assert OUTBOUND_SUCCESS is not None
    assert OUTBOUND_ERRORS is not None
    assert OUTBOUND_LATENCY is not None


def test_metrics_are_same_on_reimport():
    """Module-level metrics must be singletons."""
    from shared.messaging.outbound import metrics as m1
    from shared.messaging.outbound import metrics as m2
    assert m1.OUTBOUND_TOTAL is m2.OUTBOUND_TOTAL
