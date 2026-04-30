"""Verify core messaging models are importable and match gateway models."""
from shared.core.messaging.models import (
    UnifiedMessage,
)


def test_unified_message_is_same_class():
    from shared.messaging.inbound.models import UnifiedMessage as GatewayUM
    assert UnifiedMessage is GatewayUM

def test_all_exports_present():
    import shared.core.messaging.models as m
    expected = ["UnifiedMessage", "UnifiedCard", "UnifiedAction",
                "AgentResponse", "ActionResponse", "CardAction",
                "CardActionStyle", "MessageType", "Platform"]
    for name in expected:
        assert hasattr(m, name), f"Missing: {name}"
