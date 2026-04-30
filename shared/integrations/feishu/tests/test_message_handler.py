"""Tests for MessageRecorder — feishu message handler.

Organised by concern: message type filtering, short message filtering,
content extraction, whitelist, deduplication, sender name cache,
timestamp parsing, full record flow, record without session manager.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.integrations.feishu.handlers import message as _msg_handler_mod
from shared.integrations.feishu.handlers.message import MessageRecorder

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_recorder(
    feishu_client=None,
    db=None,
    session_manager=None,
) -> MessageRecorder:
    """Construct a MessageRecorder with sensible mock defaults."""
    if feishu_client is None:
        feishu_client = MagicMock()
        feishu_client.get_user_info = AsyncMock(return_value={"name": "TestUser"})
    if db is None:
        db = MagicMock()
        session = AsyncMock()
        session.commit = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        db.session.return_value = ctx
    return MessageRecorder(feishu_client, db, session_manager)


def _text_message(text: str) -> dict:
    """Build a minimal message dict with message_type=text."""
    return {
        "message_type": "text",
        "content": json.dumps({"text": text}),
    }


# ──────────────────────────────────────────────
# Message Type Filtering
# ──────────────────────────────────────────────


class TestMessageTypeFiltering:
    """_should_record returns True for recordable types, False for skipped types."""

    @pytest.fixture
    def recorder(self):
        return _make_recorder()

    @pytest.mark.parametrize(
        "msg_type, content_json, expected",
        [
            pytest.param(
                "text",
                json.dumps({"text": "hello world test"}),
                True,
                id="text-should-record",
            ),
            pytest.param(
                "post",
                json.dumps({"title": "T", "content": [[{"tag": "text", "text": "body"}]]}),
                True,
                id="post-should-record",
            ),
            pytest.param(
                "image",
                json.dumps({"image_key": "img_001"}),
                True,
                id="image-should-record",
            ),
            pytest.param(
                "file",
                json.dumps({"file_key": "fk_001", "file_name": "a.pdf"}),
                True,
                id="file-should-record",
            ),
            pytest.param("sticker", "{}", False, id="sticker-skip"),
            pytest.param("system", "{}", False, id="system-skip"),
            pytest.param("share_card", "{}", False, id="share_card-skip"),
            pytest.param("share_user", "{}", False, id="share_user-skip"),
        ],
    )
    def test_should_record__type_filter__returns_expected(
        self, recorder, msg_type, content_json, expected
    ):
        message = {"message_type": msg_type, "content": content_json}
        assert recorder._should_record(message) is expected


# ──────────────────────────────────────────────
# Short Message Filtering
# ──────────────────────────────────────────────


class TestShortMessageFiltering:
    """Text messages at or below the minimum text length threshold are skipped."""

    @pytest.fixture
    def recorder(self):
        return _make_recorder()

    @pytest.mark.parametrize(
        "text, expected",
        [
            pytest.param("ab", False, id="2-chars-skip"),
            pytest.param("abc", False, id="3-chars-boundary-skip"),
            pytest.param("abcd", True, id="4-chars-pass"),
            pytest.param("\u4f60\u597d", False, id="chinese-2-chars-skip"),
            pytest.param("\u4f60\u597d\u4e16\u754c\u5417", True, id="chinese-5-chars-pass"),
        ],
    )
    def test_should_record__short_text__returns_expected(self, recorder, text, expected):
        message = _text_message(text)
        assert recorder._should_record(message) is expected


# ──────────────────────────────────────────────
# Content Extraction
# ──────────────────────────────────────────────


class TestContentExtraction:
    """_extract_content returns the right string for every message_type."""

    @pytest.fixture
    def recorder(self):
        return _make_recorder()

    @pytest.mark.parametrize(
        "msg_type, content_dict, expected",
        [
            pytest.param(
                "text",
                {"text": "hello world"},
                "hello world",
                id="text-plain",
            ),
            pytest.param(
                "post",
                {
                    "title": "Notes",
                    "content": [[{"tag": "text", "text": "line1"}]],
                },
                "Notes line1",
                id="post-simple",
            ),
            pytest.param(
                "image",
                {"image_key": "img_abc"},
                "[图片: img_abc]",
                id="image-key",
            ),
            pytest.param(
                "file",
                {"file_key": "fk_xyz", "file_name": "report.pdf"},
                "[文件: report.pdf (fk_xyz)]",
                id="file-key-name",
            ),
            pytest.param(
                "audio",
                {"file_key": "audio_001"},
                "[语音消息]",
                id="audio-placeholder",
            ),
            pytest.param(
                "video",
                {"file_key": "video_001"},
                "[视频消息]",
                id="video-placeholder",
            ),
            pytest.param(
                "merge_forward",
                {},
                "[merge_forward]",
                id="unknown-type-bracket",
            ),
        ],
    )
    def test_extract_content__various_types__returns_expected(
        self, recorder, msg_type, content_dict, expected
    ):
        message = {
            "message_type": msg_type,
            "content": json.dumps(content_dict),
        }
        assert recorder._extract_content(message) == expected

    def test_extract_content__post_complex_nested__returns_joined_text(self, recorder):
        """Multi-paragraph post with at/a tags should be joined by space."""
        content = {
            "title": "Meeting Notes",
            "content": [
                [
                    {"tag": "text", "text": "Discussion:"},
                    {"tag": "a", "text": "Link", "href": "https://example.com"},
                ],
                [
                    {"tag": "at", "user_id": "ou_1", "user_name": "Alice"},
                    {"tag": "text", "text": "please review"},
                ],
            ],
        }
        message = {"message_type": "post", "content": json.dumps(content)}
        result = recorder._extract_content(message)
        assert result == "Meeting Notes Discussion: Link @Alice please review"

    def test_extract_content__json_decode_failure__returns_raw_string(self, recorder):
        message = {"message_type": "text", "content": "not-valid-json"}
        assert recorder._extract_content(message) == "not-valid-json"


# ──────────────────────────────────────────────
# Whitelist (monitored chat)
# ──────────────────────────────────────────────


class TestWhitelist:
    """_is_monitored_chat checks settings.feishu_monitored_chat_ids."""

    @pytest.fixture
    def recorder(self):
        return _make_recorder()

    def test_is_monitored_chat__hit__returns_true(self, recorder):
        with patch.object(_msg_handler_mod, "settings") as mock_settings:
            mock_settings.feishu_monitored_chat_ids = ["oc_chat_1", "oc_chat_2"]
            assert recorder._is_monitored_chat("oc_chat_1") is True

    def test_is_monitored_chat__miss__returns_false(self, recorder):
        with patch.object(_msg_handler_mod, "settings") as mock_settings:
            mock_settings.feishu_monitored_chat_ids = ["oc_chat_1", "oc_chat_2"]
            assert recorder._is_monitored_chat("oc_other") is False

    def test_is_monitored_chat__empty_whitelist__returns_false(self, recorder):
        with patch.object(_msg_handler_mod, "settings") as mock_settings:
            mock_settings.feishu_monitored_chat_ids = []
            assert recorder._is_monitored_chat("oc_any") is False


# ──────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────


class TestDeduplication:
    """_exists delegates to MessageRepository.get_by_feishu_message_id."""

    @pytest.fixture
    def recorder(self, mock_db_session):
        return _make_recorder(db=mock_db_session)

    @pytest.mark.asyncio
    async def test_exists__new_message__returns_false(self, recorder, mock_message_repo):
        mock_message_repo.get_by_feishu_message_id = AsyncMock(return_value=None)
        with patch.object(
            _msg_handler_mod, "MessageRepository",
            return_value=mock_message_repo,
        ):
            result = await recorder._exists("msg_new_001")
            assert result is False
            mock_message_repo.get_by_feishu_message_id.assert_called_once_with("msg_new_001")

    @pytest.mark.asyncio
    async def test_exists__duplicate_message__returns_true(self, recorder, mock_message_repo):
        mock_message_repo.get_by_feishu_message_id = AsyncMock(return_value=MagicMock())
        with patch.object(
            _msg_handler_mod, "MessageRepository",
            return_value=mock_message_repo,
        ):
            result = await recorder._exists("msg_dup_001")
            assert result is True


# ──────────────────────────────────────────────
# Sender Name Cache
# ──────────────────────────────────────────────


class TestSenderNameCache:
    """_get_sender_name caches API results and handles errors."""

    @pytest.fixture
    def client(self):
        client = MagicMock()
        client.get_user_info = AsyncMock(return_value={"name": "Alice"})
        return client

    @pytest.fixture
    def recorder(self, client):
        return _make_recorder(feishu_client=client)

    @pytest.mark.asyncio
    async def test_get_sender_name__api_fetch__returns_name_and_caches(self, recorder, client):
        client.get_user_info = AsyncMock(return_value={"name": "Bob"})
        name = await recorder._get_sender_name("ou_bob")
        assert name == "Bob"
        client.get_user_info.assert_called_once_with("ou_bob")
        assert recorder._user_cache["ou_bob"] == "Bob"

    @pytest.mark.asyncio
    async def test_get_sender_name__cache_hit__no_api_call(self, recorder, client):
        recorder._user_cache["ou_cached"] = "CachedUser"
        client.get_user_info = AsyncMock()

        name = await recorder._get_sender_name("ou_cached")
        assert name == "CachedUser"
        client.get_user_info.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_sender_name__api_exception__returns_unknown(self, recorder, client):
        client.get_user_info = AsyncMock(side_effect=RuntimeError("timeout"))
        name = await recorder._get_sender_name("ou_error")
        assert name == "Unknown"

    @pytest.mark.asyncio
    async def test_get_sender_name__empty_open_id__returns_unknown(self, recorder):
        name = await recorder._get_sender_name("")
        assert name == "Unknown"


# ──────────────────────────────────────────────
# Timestamp Parsing
# ──────────────────────────────────────────────


class TestTimestamp:
    """_parse_timestamp converts millisecond strings to UTC datetime."""

    @pytest.fixture
    def recorder(self):
        return _make_recorder()

    def test_parse_timestamp__valid_ms__correct_datetime(self, recorder):
        # 1706169600000 ms -> 2024-01-25 08:00:00 UTC
        result = recorder._parse_timestamp("1706169600000")
        assert result == datetime(2024, 1, 25, 8, 0, 0, tzinfo=UTC)

    def test_parse_timestamp__empty_string__returns_now_utc(self, recorder):
        result = recorder._parse_timestamp("")
        now = datetime.now(UTC)
        assert abs((result - now).total_seconds()) < 2

    def test_parse_timestamp__invalid_string__returns_now_utc(self, recorder):
        result = recorder._parse_timestamp("not_a_number")
        now = datetime.now(UTC)
        assert abs((result - now).total_seconds()) < 2

    def test_parse_timestamp__none_equivalent__returns_now_utc(self, recorder):
        """Empty string (falsy) triggers the `if not timestamp_str` branch."""
        result = recorder._parse_timestamp("")
        now = datetime.now(UTC)
        assert abs((result - now).total_seconds()) < 2


# ──────────────────────────────────────────────
# Full Record Flow
# ──────────────────────────────────────────────


class TestRecordFullFlow:
    """record() orchestrates whitelist -> filter -> dedup -> extract -> save."""

    @pytest.fixture
    def client(self, mock_feishu_client):
        mock_feishu_client.get_user_info = AsyncMock(return_value={"name": "Sender"})
        return mock_feishu_client

    @pytest.fixture
    def session_manager(self):
        sm = MagicMock()
        sm.get_or_create_session = AsyncMock(return_value="ses_flow_001")
        return sm

    @pytest.fixture
    def recorder(self, client, mock_db_session, session_manager):
        return MessageRecorder(client, mock_db_session, session_manager)

    @pytest.mark.asyncio
    async def test_record__full_flow__creates_chat_message(
        self, recorder, client, mock_message_repo, session_manager
    ):
        event = {
            "message": {
                "chat_id": "oc_monitored",
                "message_id": "msg_full_001",
                "message_type": "text",
                "content": json.dumps({"text": "Full flow test message"}),
                "create_time": "1706169600000",
            },
            "sender": {
                "sender_id": {"open_id": "ou_sender_full"},
            },
        }

        with (
            patch.object(
                _msg_handler_mod, "settings"
            ) as mock_settings,
            patch.object(
                _msg_handler_mod, "MessageRepository",
                return_value=mock_message_repo,
            ),
            patch.object(
                _msg_handler_mod, "generate_id",
                return_value="msg_generated_ulid",
            ),
        ):
            mock_settings.feishu_monitored_chat_ids = ["oc_monitored"]
            mock_message_repo.get_by_feishu_message_id = AsyncMock(return_value=None)

            result = await recorder.record(event)

        assert result is not None
        assert result.id == "msg_generated_ulid"
        assert result.chat_id == "oc_monitored"
        assert result.message_id == "msg_full_001"
        assert result.sender_id == "ou_sender_full"
        assert result.sender_name == "Sender"
        assert result.message_type == "text"
        assert result.content == "Full flow test message"
        assert result.session_id == "ses_flow_001"
        assert result.sent_at == datetime(2024, 1, 25, 8, 0, 0, tzinfo=UTC)

        mock_message_repo.create.assert_called_once()
        session_manager.get_or_create_session.assert_called_once_with("oc_monitored")
        client.get_user_info.assert_called_once_with("ou_sender_full")

    @pytest.mark.asyncio
    async def test_record__not_monitored__returns_none(self, recorder, mock_message_repo):
        event = {
            "message": {
                "chat_id": "oc_unmonitored",
                "message_id": "msg_skip_001",
                "message_type": "text",
                "content": json.dumps({"text": "Should not record"}),
                "create_time": "1706169600000",
            },
            "sender": {"sender_id": {"open_id": "ou_x"}},
        }
        with patch.object(_msg_handler_mod, "settings") as mock_settings:
            mock_settings.feishu_monitored_chat_ids = ["oc_other"]
            result = await recorder.record(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_record__filtered_type__returns_none(self, recorder, mock_message_repo):
        event = {
            "message": {
                "chat_id": "oc_monitored",
                "message_id": "msg_sticker_001",
                "message_type": "sticker",
                "content": "{}",
                "create_time": "1706169600000",
            },
            "sender": {"sender_id": {"open_id": "ou_x"}},
        }
        with patch.object(_msg_handler_mod, "settings") as mock_settings:
            mock_settings.feishu_monitored_chat_ids = ["oc_monitored"]
            result = await recorder.record(event)
        assert result is None

    @pytest.mark.asyncio
    async def test_record__duplicate__returns_none(self, recorder, mock_message_repo):
        event = {
            "message": {
                "chat_id": "oc_monitored",
                "message_id": "msg_dup_full",
                "message_type": "text",
                "content": json.dumps({"text": "Duplicate text message"}),
                "create_time": "1706169600000",
            },
            "sender": {"sender_id": {"open_id": "ou_x"}},
        }
        mock_message_repo.get_by_feishu_message_id = AsyncMock(return_value=MagicMock())
        with (
            patch.object(_msg_handler_mod, "settings") as mock_settings,
            patch.object(
                _msg_handler_mod, "MessageRepository",
                return_value=mock_message_repo,
            ),
        ):
            mock_settings.feishu_monitored_chat_ids = ["oc_monitored"]
            result = await recorder.record(event)
        assert result is None


# ──────────────────────────────────────────────
# Record Without Session Manager
# ──────────────────────────────────────────────


class TestRecordWithoutSessionManager:
    """When session_manager is None, session_id should be None."""

    @pytest.fixture
    def recorder(self, mock_feishu_client, mock_db_session):
        mock_feishu_client.get_user_info = AsyncMock(return_value={"name": "NoSession"})
        return MessageRecorder(mock_feishu_client, mock_db_session, session_manager=None)

    @pytest.mark.asyncio
    async def test_record__no_session_manager__session_id_is_none(
        self, recorder, mock_message_repo
    ):
        event = {
            "message": {
                "chat_id": "oc_monitored",
                "message_id": "msg_nosm_001",
                "message_type": "text",
                "content": json.dumps({"text": "No session manager message"}),
                "create_time": "1706169600000",
            },
            "sender": {"sender_id": {"open_id": "ou_sender_nosm"}},
        }
        mock_message_repo.get_by_feishu_message_id = AsyncMock(return_value=None)

        with (
            patch.object(_msg_handler_mod, "settings") as mock_settings,
            patch.object(
                _msg_handler_mod, "MessageRepository",
                return_value=mock_message_repo,
            ),
            patch.object(
                _msg_handler_mod, "generate_id",
                return_value="msg_nosm_ulid",
            ),
        ):
            mock_settings.feishu_monitored_chat_ids = ["oc_monitored"]
            result = await recorder.record(event)

        assert result is not None
        assert result.session_id is None
        assert result.sender_name == "NoSession"
        assert result.content == "No session manager message"
        mock_message_repo.create.assert_called_once()
