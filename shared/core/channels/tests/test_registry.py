"""Tests for the canonical channel registry."""

from shared.core.channels import ChannelRegistry


class FakeChannel:
    def __init__(self, name: str):
        self.channel_name = name


def setup_function() -> None:
    ChannelRegistry.clear()


def teardown_function() -> None:
    ChannelRegistry.clear()


def test_register_get_and_list_channels() -> None:
    channel = FakeChannel("feishu")

    ChannelRegistry.register(channel)

    assert ChannelRegistry.get("feishu") is channel
    assert ChannelRegistry.all() == {"feishu": channel}
    assert ChannelRegistry.list_channels() == {"feishu": channel}


def test_list_channels_returns_copy() -> None:
    channel = FakeChannel("wecom")
    ChannelRegistry.register(channel)

    listed = ChannelRegistry.list_channels()
    listed["fake"] = FakeChannel("fake")

    assert ChannelRegistry.get("fake") is None
