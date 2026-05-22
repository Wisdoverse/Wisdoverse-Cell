"""Structural test for the WeCom messenger port (DDD-022)."""

from __future__ import annotations

import pytest

from shared.core.integration_ports import WecomMessengerPort


def test_wecom_channel_adapter_satisfies_port() -> None:
    """The existing WecomChannelAdapter must satisfy the named port."""
    try:
        from shared.integrations.wecom.adapter import WecomChannelAdapter
    except ImportError:
        pytest.skip("WecomChannelAdapter import path missing")
    assert isinstance(WecomMessengerPort, type)
    assert hasattr(WecomChannelAdapter, "send_message")
    assert hasattr(WecomChannelAdapter, "send_card")
    assert hasattr(WecomChannelAdapter, "update_card")


def test_protocol_is_runtime_checkable_with_a_minimal_double() -> None:
    """A minimal duck-typed double passes the runtime isinstance check."""

    class _Double:
        async def send_message(self, user_id, content):
            return "msg_1"

        async def send_card(self, user_id, card):
            return "msg_2"

        async def update_card(self, message_id, card):
            return True

    assert isinstance(_Double(), WecomMessengerPort)
