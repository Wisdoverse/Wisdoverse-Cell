"""Tests for channel gateway enums."""
from shared.messaging.outbound.core.enums import (
    ChannelCapability,
    ChannelStatus,
    ChatType,
    MediaType,
    ParseMode,
)


class TestChannelCapability:
    def test_has_text_capability(self):
        assert ChannelCapability.TEXT == "text"

    def test_has_rich_media_capability(self):
        assert ChannelCapability.RICH_MEDIA == "rich_media"

    def test_has_edit_message_capability(self):
        assert ChannelCapability.EDIT_MESSAGE == "edit_message"

    def test_has_delete_message_capability(self):
        assert ChannelCapability.DELETE_MESSAGE == "delete_message"

    def test_has_reactions_capability(self):
        assert ChannelCapability.REACTIONS == "reactions"

    def test_has_read_receipts_capability(self):
        assert ChannelCapability.READ_RECEIPTS == "read_receipts"

    def test_has_typing_indicator_capability(self):
        assert ChannelCapability.TYPING_INDICATOR == "typing_indicator"

    def test_has_group_management_capability(self):
        assert ChannelCapability.GROUP_MANAGEMENT == "group_management"

    def test_has_webhooks_capability(self):
        assert ChannelCapability.WEBHOOKS == "webhooks"


class TestChannelStatus:
    def test_has_stable_status(self):
        assert ChannelStatus.STABLE == "stable"

    def test_has_experimental_status(self):
        assert ChannelStatus.EXPERIMENTAL == "experimental"

    def test_has_deprecated_status(self):
        assert ChannelStatus.DEPRECATED == "deprecated"


class TestChatType:
    def test_has_dm_type(self):
        assert ChatType.DM == "dm"

    def test_has_group_type(self):
        assert ChatType.GROUP == "group"

    def test_has_channel_type(self):
        assert ChatType.CHANNEL == "channel"


class TestMediaType:
    def test_has_image_type(self):
        assert MediaType.IMAGE == "image"

    def test_has_audio_type(self):
        assert MediaType.AUDIO == "audio"

    def test_has_video_type(self):
        assert MediaType.VIDEO == "video"

    def test_has_file_type(self):
        assert MediaType.FILE == "file"

    def test_has_sticker_type(self):
        assert MediaType.STICKER == "sticker"

    def test_has_voice_type(self):
        assert MediaType.VOICE == "voice"


class TestParseMode:
    def test_has_plain_mode(self):
        assert ParseMode.PLAIN == "plain"

    def test_has_markdown_mode(self):
        assert ParseMode.MARKDOWN == "markdown"

    def test_has_html_mode(self):
        assert ParseMode.HTML == "html"
