"""Verify channel_gateway compat layer after move to messaging/outbound."""


def test_registry_same_class():
    from shared.messaging.outbound.core.registry import AdapterRegistry as New
    from shared.services.channel_gateway.core.registry import AdapterRegistry as Old
    assert New is Old


def test_base_adapter_same():
    from shared.messaging.outbound.core.base_adapter import BaseChannelAdapter as New
    from shared.services.channel_gateway.core.base_adapter import BaseChannelAdapter as Old
    assert New is Old


def test_models_same():
    from shared.messaging.outbound.models.messages import InboundMessage as New
    from shared.services.channel_gateway.models.messages import InboundMessage as Old
    assert New is Old


def test_metrics_same():
    from shared.messaging.outbound.metrics import OUTBOUND_TOTAL as New
    from shared.services.channel_gateway.metrics import OUTBOUND_TOTAL as Old
    assert New is Old
