"""Core framework — Port interfaces, ABCs, engines."""

from .integration_ports import (
    BitableTablePort,
    FeishuContactLookupPort,
    FeishuMessengerPort,
    FeishuWebhookPort,
    GitLabMergeRequestNotePort,
    GitLabMergeRequestPort,
    OpenProjectWorkPackagePort,
)

__all__ = [
    "BitableTablePort",
    "FeishuContactLookupPort",
    "FeishuMessengerPort",
    "FeishuWebhookPort",
    "GitLabMergeRequestPort",
    "GitLabMergeRequestNotePort",
    "OpenProjectWorkPackagePort",
]
