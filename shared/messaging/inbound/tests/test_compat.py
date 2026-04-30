"""Verify gateway compat layer after move to messaging/inbound."""
import shared.services.gateway as old


def test_unified_gateway_same():
    from shared.messaging.inbound import UnifiedGateway
    assert UnifiedGateway is old.UnifiedGateway


def test_unified_message_same():
    from shared.messaging.inbound import UnifiedMessage
    assert UnifiedMessage is old.UnifiedMessage


def test_base_adapter_same():
    from shared.messaging.inbound import BasePlatformAdapter
    assert BasePlatformAdapter is old.BasePlatformAdapter


def test_user_service_same():
    from shared.messaging.inbound import UserService
    assert UserService is old.UserService
