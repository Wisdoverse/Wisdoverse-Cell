"""Verify channels compat layer."""


def test_message_channel_same():
    from shared.integrations.channels import MessageChannel as New
    from shared.services.channels import MessageChannel as Old
    assert New is Old


def test_channel_card_same():
    from shared.integrations.channels import ChannelCard as New
    from shared.services.channels import ChannelCard as Old
    assert New is Old


def test_channel_registry_same():
    from shared.integrations.channels import ChannelRegistry as New
    from shared.services.channels import ChannelRegistry as Old
    assert New is Old
