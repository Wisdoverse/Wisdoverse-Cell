"""Verify AdapterRegistry is instance-based and test-safe."""
from unittest.mock import MagicMock

from shared.messaging.outbound.core.registry import AdapterRegistry


def test_separate_instances_are_isolated():
    """Two registry instances must not share state."""
    r1 = AdapterRegistry()
    r2 = AdapterRegistry()
    mock_adapter = MagicMock()
    mock_adapter.channel_id = "test-channel"
    mock_adapter.status = "active"
    r1.register(mock_adapter)
    assert r1.has("test-channel")
    assert not r2.has("test-channel")


def test_register_and_get():
    reg = AdapterRegistry()
    mock = MagicMock()
    mock.channel_id = "ch1"
    reg.register(mock)
    assert reg.get("ch1") is mock


def test_clear():
    reg = AdapterRegistry()
    mock = MagicMock()
    mock.channel_id = "ch1"
    reg.register(mock)
    reg.clear()
    assert not reg.has("ch1")
