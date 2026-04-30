"""Tests for FeishuClient (lark-oapi SDK based).

Covers: verify_signature, get_access_token, send_card, send_message,
        update_card, reply_message, get_user_info, get_feishu_client.
"""
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.integrations.feishu.client import FeishuClient, get_feishu_client
from shared.integrations.feishu.errors import FeishuAPIError

# ── Shared fixture ──────────────────────────────────────────────


@pytest.fixture
def client():
    """FeishuClient with dummy credentials."""
    return FeishuClient(app_id="cli_test", app_secret="secret_test")


# ── Helpers ─────────────────────────────────────────────────────


def _sha256_sig(timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    """Compute the same SHA-256 hex digest the real method uses."""
    content = f"{timestamp}{nonce}{encrypt_key}".encode() + body
    return hashlib.sha256(content).hexdigest()


def _ok_msg_response(message_id: str = "msg_001") -> MagicMock:
    """Build a successful SDK message response."""
    resp = MagicMock()
    resp.success.return_value = True
    resp.data = MagicMock()
    resp.data.message_id = message_id
    return resp


def _fail_response(code: int = 99999, msg: str = "some error") -> MagicMock:
    """Build a failed SDK response."""
    resp = MagicMock()
    resp.success.return_value = False
    resp.code = code
    resp.msg = msg
    return resp


# ================================================================
# TestVerifySignature
# ================================================================


class TestVerifySignature:
    """verify_signature: SHA-256 check with fail-closed key handling."""

    TIMESTAMP = "1706169600"
    NONCE = "nonce_abc123"
    BODY = b'{"event_type":"im.message.receive_v1"}'
    ENCRYPT_KEY = "encrypt_key_for_test"

    @pytest.mark.parametrize(
        "encrypt_key, signature_fn, expected",
        [
            pytest.param(
                "encrypt_key_for_test",
                lambda ts, n, k, b: _sha256_sig(ts, n, k, b),
                True,
                id="valid_key_valid_sig",
            ),
            pytest.param(
                "encrypt_key_for_test",
                lambda *_: "deadbeef0000",
                False,
                id="valid_key_invalid_sig",
            ),
            pytest.param(
                "",
                lambda *_: "anything",
                False,
                id="empty_encrypt_key_fails_closed",
            ),
            pytest.param(
                "encrypt_key_for_test",
                lambda *_: "",
                False,
                id="valid_key_empty_signature",
            ),
            pytest.param(
                "encrypt_key_for_test",
                lambda ts, n, k, b: _sha256_sig(ts, n, k, b"tampered_body"),
                False,
                id="valid_key_tampered_body",
            ),
        ],
    )
    def test_verify_signature__parametrized__expected(
        self, client, monkeypatch, encrypt_key, signature_fn, expected
    ):
        from pydantic import SecretStr

        import shared.integrations.feishu.client as _client_mod

        monkeypatch.setattr(
            _client_mod.settings, "feishu_encrypt_key",
            SecretStr(encrypt_key),
        )
        sig = signature_fn(
            self.TIMESTAMP, self.NONCE, encrypt_key, self.BODY
        )
        result = client.verify_signature(
            self.TIMESTAMP, self.NONCE, self.BODY, sig
        )
        assert result is expected


# ================================================================
# TestGetAccessToken
# ================================================================


class TestGetAccessToken:
    """get_access_token: SDK auth API call."""

    @pytest.mark.asyncio
    async def test_get_access_token__success__returns_token(self, client):
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.tenant_access_token = "t-abcdef123456"

        with patch.object(
            client._sdk.auth.v3.tenant_access_token,
            "ainternal",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            token = await client.get_access_token()

        assert token == "t-abcdef123456"

    @pytest.mark.asyncio
    async def test_get_access_token__api_failure__raises_feishu_api_error(
        self, client
    ):
        mock_resp = _fail_response(code=10003, msg="Invalid app_secret")

        with patch.object(
            client._sdk.auth.v3.tenant_access_token,
            "ainternal",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(FeishuAPIError) as exc_info:
                await client.get_access_token()

        assert exc_info.value.code == 10003
        assert "get_access_token" in exc_info.value.message


# ================================================================
# TestSendCard
# ================================================================


class TestSendCard:
    """send_card: interactive card via im.v1.message.acreate."""

    CARD = {"header": {"title": {"content": "Alert"}}, "elements": []}

    @pytest.mark.asyncio
    async def test_send_card__success__returns_message_id(self, client):
        mock_resp = _ok_msg_response("msg_card_200")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            msg_id = await client.send_card("oc_chat1", "chat_id", self.CARD)

        assert msg_id == "msg_card_200"

    @pytest.mark.asyncio
    async def test_send_card__api_error__raises_feishu_api_error(self, client):
        mock_resp = _fail_response(code=230001, msg="Invalid receive_id")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(FeishuAPIError) as exc_info:
                await client.send_card("bad_id", "chat_id", self.CARD)

        assert exc_info.value.code == 230001

    @pytest.mark.asyncio
    async def test_send_card__json_serialization__card_encoded(self, client):
        mock_resp = _ok_msg_response("msg_json_ok")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_create:
            await client.send_card("oc_chat1", "chat_id", self.CARD)

        req = mock_create.call_args[0][0]
        body = req.request_body
        assert body.content == json.dumps(self.CARD)
        assert body.msg_type == "interactive"

    @pytest.mark.asyncio
    async def test_send_card__receive_id_type__forwarded_to_request(
        self, client
    ):
        mock_resp = _ok_msg_response("msg_open_id")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_create:
            await client.send_card("ou_user1", "open_id", self.CARD)

        req = mock_create.call_args[0][0]
        assert req.receive_id_type == "open_id"
        assert req.request_body.receive_id == "ou_user1"


# ================================================================
# TestSendMessage
# ================================================================


class TestSendMessage:
    """send_message: generic message via im.v1.message.acreate."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "msg_type, content",
        [
            pytest.param("text", '{"text": "hello"}', id="text_type"),
            pytest.param(
                "interactive",
                '{"elements": []}',
                id="interactive_type",
            ),
        ],
    )
    async def test_send_message__msg_type__returns_message_id(
        self, client, msg_type, content
    ):
        mock_resp = _ok_msg_response("msg_send_300")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_create:
            msg_id = await client.send_message(
                "ou_user1", "open_id", msg_type=msg_type, content=content
            )

        assert msg_id == "msg_send_300"
        req = mock_create.call_args[0][0]
        body = req.request_body
        assert body.msg_type == msg_type
        assert body.content == content

    @pytest.mark.asyncio
    async def test_send_message__api_error__raises_feishu_api_error(
        self, client
    ):
        mock_resp = _fail_response(code=230002, msg="msg send failed")

        with patch.object(
            client._sdk.im.v1.message,
            "acreate",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(FeishuAPIError) as exc_info:
                await client.send_message(
                    "ou_user1", "open_id", msg_type="text", content='{"text":"hi"}'
                )

        assert exc_info.value.code == 230002


# ================================================================
# TestUpdateCard
# ================================================================


class TestUpdateCard:
    """update_card: patch existing card via im.v1.message.apatch."""

    CARD = {"header": {"title": {"content": "Updated"}}, "elements": []}

    @pytest.mark.asyncio
    async def test_update_card__success__returns_true(self, client):
        mock_resp = MagicMock()
        mock_resp.success.return_value = True

        with patch.object(
            client._sdk.im.v1.message,
            "apatch",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await client.update_card("msg_100", self.CARD)

        assert result is True

    @pytest.mark.asyncio
    async def test_update_card__failure__raises_feishu_api_error(self, client):
        mock_resp = _fail_response(code=230010, msg="message not found")

        with patch.object(
            client._sdk.im.v1.message,
            "apatch",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(FeishuAPIError) as exc_info:
                await client.update_card("msg_gone", self.CARD)

        assert exc_info.value.code == 230010


# ================================================================
# TestReplyMessage
# ================================================================


class TestReplyMessage:
    """reply_message: text wrapping and passthrough."""

    @pytest.mark.asyncio
    async def test_reply_message__text_type__wraps_in_json(self, client):
        mock_resp = _ok_msg_response("msg_reply_400")

        with patch.object(
            client._sdk.im.v1.message,
            "areply",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_reply:
            msg_id = await client.reply_message(
                "msg_orig", "Hello!", msg_type="text"
            )

        assert msg_id == "msg_reply_400"
        req = mock_reply.call_args[0][0]
        body = req.request_body
        assert body.msg_type == "text"
        assert body.content == json.dumps({"text": "Hello!"})

    @pytest.mark.asyncio
    async def test_reply_message__interactive_type__passthrough(self, client):
        card_content = '{"elements": [{"tag": "div"}]}'
        mock_resp = _ok_msg_response("msg_reply_401")

        with patch.object(
            client._sdk.im.v1.message,
            "areply",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_reply:
            msg_id = await client.reply_message(
                "msg_orig", card_content, msg_type="interactive"
            )

        assert msg_id == "msg_reply_401"
        req = mock_reply.call_args[0][0]
        body = req.request_body
        assert body.msg_type == "interactive"
        assert body.content == card_content

    @pytest.mark.asyncio
    async def test_reply_message__default_msg_type__uses_text(self, client):
        """Calling reply_message without msg_type defaults to 'text' wrapping."""
        mock_resp = _ok_msg_response("msg_reply_402")

        with patch.object(
            client._sdk.im.v1.message,
            "areply",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_reply:
            await client.reply_message("msg_orig", "default text")

        req = mock_reply.call_args[0][0]
        body = req.request_body
        assert body.msg_type == "text"
        assert body.content == json.dumps({"text": "default text"})

    @pytest.mark.asyncio
    async def test_reply_message__api_error__raises_feishu_api_error(
        self, client
    ):
        mock_resp = _fail_response(code=230020, msg="reply failed")

        with patch.object(
            client._sdk.im.v1.message,
            "areply",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(FeishuAPIError) as exc_info:
                await client.reply_message("msg_orig", "text")

        assert exc_info.value.code == 230020


# ================================================================
# TestGetUserInfo
# ================================================================


class TestGetUserInfo:
    """get_user_info: contact.v3 lookup with fallback."""

    @pytest.mark.asyncio
    async def test_get_user_info__success__returns_user_dict(self, client):
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = MagicMock()
        mock_resp.data.user = MagicMock()
        mock_resp.data.user.name = "Alice"
        mock_resp.data.user.email = "alice@example.com"

        with patch.object(
            client._sdk.contact.v3.user,
            "aget",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            user = await client.get_user_info("ou_alice")

        assert user == {
            "name": "Alice",
            "email": "alice@example.com",
            "open_id": "ou_alice",
        }

    @pytest.mark.asyncio
    async def test_get_user_info__api_failure__returns_fallback(self, client):
        mock_resp = _fail_response(code=99991, msg="user not found")

        with patch.object(
            client._sdk.contact.v3.user,
            "aget",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            user = await client.get_user_info("ou_unknown")

        assert user == {"name": "Unknown", "open_id": "ou_unknown"}
        assert "email" not in user

    @pytest.mark.asyncio
    async def test_get_user_info__missing_email_attr__returns_empty_string(
        self, client
    ):
        """When the user object has no email attribute, getattr fallback gives ''."""
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_resp.data = MagicMock()
        user_obj = MagicMock(spec=["name"])  # spec excludes 'email'
        user_obj.name = "NoEmail"
        mock_resp.data.user = user_obj

        with patch.object(
            client._sdk.contact.v3.user,
            "aget",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            user = await client.get_user_info("ou_noemail")

        assert user["name"] == "NoEmail"
        assert user["email"] == ""
        assert user["open_id"] == "ou_noemail"

    @pytest.mark.asyncio
    async def test_get_user_info__exception__returns_fallback(self, client):
        with patch.object(
            client._sdk.contact.v3.user,
            "aget",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection lost"),
        ):
            user = await client.get_user_info("ou_error")

        assert user == {"name": "Unknown", "open_id": "ou_error"}


# ================================================================
# TestGetFeishuClient
# ================================================================


class TestGetFeishuClient:
    """get_feishu_client: singleton factory."""

    def test_get_feishu_client__singleton__returns_same_instance(self, monkeypatch):
        import shared.integrations.feishu.client as _client_mod

        monkeypatch.setattr(_client_mod, "_feishu_client", None)

        first = get_feishu_client()
        second = get_feishu_client()

        assert first is second
        assert isinstance(first, FeishuClient)

        monkeypatch.setattr(_client_mod, "_feishu_client", None)
