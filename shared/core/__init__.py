"""Core framework — Port interfaces, ABCs, engines."""

from .ids import IDPrefix, generate_id, generate_ulid
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
    "IDPrefix",
    "generate_id",
    "generate_ulid",
]
