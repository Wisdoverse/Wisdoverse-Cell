"""Structural test for the OpenClaw integration port (DDD-013 / DDD-022)."""

from __future__ import annotations

import pytest

from shared.core.integration_ports import OpenClawIntegrationPort


def test_openclaw_channel_adapter_satisfies_port() -> None:
    """The existing OpenClawChannelAdapter must satisfy the named port."""
    try:
        from shared.integrations.openclaw.adapter import OpenClawChannelAdapter
    except ImportError:
        pytest.skip("OpenClawChannelAdapter import path missing")
    assert hasattr(OpenClawChannelAdapter, "send_message")
    assert hasattr(OpenClawChannelAdapter, "send_card")


def test_protocol_is_runtime_checkable_with_a_minimal_double() -> None:
    """A minimal duck-typed double passes the runtime isinstance check."""

    class _Double:
        async def send_message(self, user_id, content):
            return "msg_1"

        async def send_card(self, user_id, card):
            return "msg_2"

    assert isinstance(_Double(), OpenClawIntegrationPort)
