"""Channel gateway enumerations."""
from enum import Enum


class ChannelCapability(str, Enum):
    """Capabilities that a channel adapter may support."""

    TEXT = "text"
    RICH_MEDIA = "rich_media"
    EDIT_MESSAGE = "edit_message"
    DELETE_MESSAGE = "delete_message"
    REACTIONS = "reactions"
    READ_RECEIPTS = "read_receipts"
    TYPING_INDICATOR = "typing_indicator"
    GROUP_MANAGEMENT = "group_management"
    WEBHOOKS = "webhooks"


class ChannelStatus(str, Enum):
    """Stability status of a channel adapter."""

    STABLE = "stable"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


class ChatType(str, Enum):
    """Type of chat conversation."""

    DM = "dm"
    GROUP = "group"
    CHANNEL = "channel"


class MediaType(str, Enum):
    """Type of media attachment."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    STICKER = "sticker"
    VOICE = "voice"


class ParseMode(str, Enum):
    """Message content parse mode."""

    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
