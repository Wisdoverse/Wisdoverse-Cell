"""Verify BasePlatformAdapter Port interface."""
from shared.core.messaging.platform_adapter import BasePlatformAdapter
from shared.messaging.inbound.adapter import BasePlatformAdapter as GatewayBPA


def test_is_same_base_class():
    assert BasePlatformAdapter is GatewayBPA

def test_has_build_platform_card():
    assert hasattr(BasePlatformAdapter, "build_platform_card")
