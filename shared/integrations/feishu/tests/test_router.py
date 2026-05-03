"""Tests for shared/services/feishu/router.py

Covers: url_verification, signature verification, event routing,
card action routing, health check, and init_handlers.
"""
import sys as _sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.integrations.feishu.router import init_handlers, router

_feishu_router_mod = _sys.modules["shared.integrations.feishu.router"]
from shared.integrations.feishu.tests.conftest import make_card_action, make_feishu_event

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_handlers():
    """Reset all global handler references before each test."""
    init_handlers(event_h=None, bot_h=None, card_h=None, message_h=None)
    yield
    init_handlers(event_h=None, bot_h=None, card_h=None, message_h=None)


@pytest.fixture
def app():
    """Create a fresh FastAPI app with the feishu router."""
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    """Synchronous TestClient bound to the test app."""
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Patch settings on the router module and return a MagicMock settings object.

    Defaults mirror a fully-enabled configuration.
    """
    s = MagicMock()
    s.feishu_enabled = True
    s.feishu_verify_signature = False
    s.feishu_encrypt_key = ""
    s.feishu_bot_enabled = True
    s.feishu_event_enabled = True
    s.feishu_card_enabled = True
    s.feishu_message_recording_enabled = True
    with patch.object(_feishu_router_mod, "settings", s):
        yield s


@pytest.fixture
def mock_client():
    """MagicMock feishu client returned by feishu_client()."""
    c = MagicMock()
    c.verify_signature = MagicMock(return_value=True)
    c.get_access_token = AsyncMock(return_value="t-test_token")
    return c


def _patch_feishu_client(mock_client):
    """Return a context-manager patch for feishu_client() on the router module."""
    return patch.object(
        _feishu_router_mod,
        "feishu_client",
        return_value=mock_client,
    )


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _wrap_event_callback(event_data, event_type="im.message.receive_v1"):
    """Wrap raw event_data into a full event_callback payload."""
    return {
        "type": "event_callback",
        "header": {"event_type": event_type},
        "event": event_data,
    }


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────


class TestURLVerification:
    """POST /webhook with type=url_verification."""

    def test_post__url_verification_sig_disabled__returns_challenge(
        self, client, mock_settings
    ):
        mock_settings.feishu_verify_signature = False

        response = client.post(
            "/api/feishu/webhook",
            json={"type": "url_verification", "challenge": "test_challenge_abc"},
        )

        assert response.status_code == 200
        assert response.json() == {"challenge": "test_challenge_abc"}

    def test_post__url_verification__verifies_signature_when_enabled(
        self, client, mock_settings, mock_client
    ):
        """URL verification is still external webhook traffic and must be signed."""
        mock_settings.feishu_verify_signature = True
        mock_settings.feishu_encrypt_key = "encrypt_key_for_test"
        mock_client.verify_signature.return_value = True

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                json={"type": "url_verification", "challenge": "signed_challenge"},
                headers=TestSignatureVerification._SIG_HEADERS,
            )

        assert response.status_code == 200
        assert response.json()["challenge"] == "signed_challenge"
        mock_client.verify_signature.assert_called_once()


class TestSignatureVerification:
    """Signature verification gate on non-url_verification requests."""

    _SIG_HEADERS = {
        "x-lark-request-timestamp": "1706169600",
        "x-lark-request-nonce": "nonce_abc",
        "x-lark-signature": "sig_valid",
    }

    def test_post__sig_enabled_valid__returns_200(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_verify_signature = True
        mock_settings.feishu_encrypt_key = "encrypt_key_for_test"
        mock_client.verify_signature.return_value = True

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                json={"type": "event_callback", "header": {"event_type": "other"}, "event": {}},
                headers=self._SIG_HEADERS,
            )

        assert response.status_code == 200
        mock_client.verify_signature.assert_called_once()

    def test_post__sig_enabled_invalid__returns_401(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_verify_signature = True
        mock_settings.feishu_encrypt_key = "encrypt_key_for_test"
        mock_client.verify_signature.return_value = False

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                json={"type": "event_callback", "header": {"event_type": "other"}, "event": {}},
                headers=self._SIG_HEADERS,
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"

    def test_post__sig_enabled_no_encrypt_key__returns_401_before_client_verify(
        self, client, mock_settings, mock_client
    ):
        """Signature verification must fail closed when the key is missing."""
        mock_settings.feishu_verify_signature = True
        mock_settings.feishu_encrypt_key = ""

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                json={"type": "event_callback", "header": {"event_type": "other"}, "event": {}},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Signature verification key is not configured"
        mock_client.verify_signature.assert_not_called()

    def test_post__sig_enabled_invalid__returns_401_before_json_parse(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_verify_signature = True
        mock_settings.feishu_encrypt_key = "encrypt_key_for_test"
        mock_client.verify_signature.return_value = False

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                content=b"not-json",
                headers={**self._SIG_HEADERS, "content-type": "application/json"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid signature"
        mock_client.verify_signature.assert_called_once()

    def test_post__sig_disabled_invalid_json__returns_400(
        self, client, mock_settings
    ):
        mock_settings.feishu_verify_signature = False

        response = client.post(
            "/api/feishu/webhook",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid JSON"

    def test_post__sig_disabled__skips_verification(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_verify_signature = False

        with _patch_feishu_client(mock_client):
            response = client.post(
                "/api/feishu/webhook",
                json={"type": "event_callback", "header": {"event_type": "other"}, "event": {}},
            )

        assert response.status_code == 200
        mock_client.verify_signature.assert_not_called()


class TestEventRouting:
    """POST /webhook with type=event_callback dispatching."""

    def test_post__im_message__calls_bot_and_recorder(
        self, client, mock_settings
    ):
        bot = MagicMock()
        bot.handle_message = AsyncMock()
        recorder = MagicMock()
        recorder.record = AsyncMock()
        init_handlers(bot_h=bot, message_h=recorder)

        event_data = make_feishu_event()
        payload = _wrap_event_callback(event_data, "im.message.receive_v1")

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"code": 0}
        bot.handle_message.assert_awaited_once_with(event_data)
        recorder.record.assert_awaited_once_with(event_data)

    def test_post__im_message_recording_disabled__only_bot_called(
        self, client, mock_settings
    ):
        mock_settings.feishu_message_recording_enabled = False
        bot = MagicMock()
        bot.handle_message = AsyncMock()
        recorder = MagicMock()
        recorder.record = AsyncMock()
        init_handlers(bot_h=bot, message_h=recorder)

        event_data = make_feishu_event()
        payload = _wrap_event_callback(event_data, "im.message.receive_v1")

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        bot.handle_message.assert_awaited_once()
        recorder.record.assert_not_awaited()

    def test_post__im_message_bot_disabled__recorder_still_called(
        self, client, mock_settings
    ):
        mock_settings.feishu_bot_enabled = False
        bot = MagicMock()
        bot.handle_message = AsyncMock()
        recorder = MagicMock()
        recorder.record = AsyncMock()
        init_handlers(bot_h=bot, message_h=recorder)

        event_data = make_feishu_event()
        payload = _wrap_event_callback(event_data, "im.message.receive_v1")

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        bot.handle_message.assert_not_awaited()
        recorder.record.assert_awaited_once()

    def test_post__im_message_no_handlers__returns_200(
        self, client, mock_settings
    ):
        """bot_handler=None and message_recorder=None => graceful no-op."""
        event_data = make_feishu_event()
        payload = _wrap_event_callback(event_data, "im.message.receive_v1")

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"code": 0}

    def test_post__im_message_recorder_raises__still_returns_200(
        self, client, mock_settings
    ):
        """Recorder exception is swallowed; bot_handler still runs."""
        bot = MagicMock()
        bot.handle_message = AsyncMock()
        recorder = MagicMock()
        recorder.record = AsyncMock(side_effect=RuntimeError("db down"))
        init_handlers(bot_h=bot, message_h=recorder)

        event_data = make_feishu_event()
        payload = _wrap_event_callback(event_data, "im.message.receive_v1")

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        recorder.record.assert_awaited_once()
        bot.handle_message.assert_awaited_once()

    def test_post__other_event__dispatches_to_event_handler(
        self, client, mock_settings
    ):
        handler = MagicMock()
        handler.dispatch = AsyncMock(return_value={"code": 0, "msg": "ok"})
        init_handlers(event_h=handler)

        payload = {
            "type": "event_callback",
            "header": {"event_type": "contact.user.created_v3"},
            "event": {"user_id": "ou_new"},
        }

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        handler.dispatch.assert_awaited_once_with("contact.user.created_v3", payload)

    def test_post__other_event_handler_none__returns_200(
        self, client, mock_settings
    ):
        payload = {
            "type": "event_callback",
            "header": {"event_type": "contact.user.created_v3"},
            "event": {},
        }

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"code": 0}

    def test_post__other_event_disabled__returns_200(
        self, client, mock_settings
    ):
        mock_settings.feishu_event_enabled = False
        handler = MagicMock()
        handler.dispatch = AsyncMock()
        init_handlers(event_h=handler)

        payload = {
            "type": "event_callback",
            "header": {"event_type": "contact.user.created_v3"},
            "event": {},
        }

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        handler.dispatch.assert_not_awaited()


class TestUnknownCallbackType:
    """POST /webhook with an unknown type."""

    def test_post__unknown_type__returns_200_code_zero(self, client, mock_settings):
        response = client.post(
            "/api/feishu/webhook",
            json={"type": "some_unknown_type", "data": {}},
        )

        assert response.status_code == 200
        assert response.json() == {"code": 0}


class TestCardActionRouting:
    """POST /webhook with type=card_action or action key."""

    def test_post__card_action_type__calls_card_handler(
        self, client, mock_settings
    ):
        handler = MagicMock()
        handler.handle_action = AsyncMock(return_value={"toast": "done"})
        init_handlers(card_h=handler)

        payload = {"type": "card_action", **make_card_action()}

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        handler.handle_action.assert_awaited_once_with(payload)

    def test_post__action_key_present__calls_card_handler(
        self, client, mock_settings
    ):
        """Payload with 'action' key (no explicit type) still routes to card handler."""
        handler = MagicMock()
        handler.handle_action = AsyncMock(return_value={"toast": "ok"})
        init_handlers(card_h=handler)

        payload = make_card_action()  # has "action" key, no "type"

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        handler.handle_action.assert_awaited_once()

    def test_post__card_handler_none__returns_200(self, client, mock_settings):
        payload = {"type": "card_action", **make_card_action()}

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        assert response.json() == {"code": 0}

    def test_post__card_disabled__returns_200(self, client, mock_settings):
        mock_settings.feishu_card_enabled = False
        handler = MagicMock()
        handler.handle_action = AsyncMock()
        init_handlers(card_h=handler)

        payload = {"type": "card_action", **make_card_action()}

        response = client.post("/api/feishu/webhook", json=payload)

        assert response.status_code == 200
        handler.handle_action.assert_not_awaited()


class TestHealthCheck:
    """GET /health endpoint."""

    def test_get__feishu_enabled_token_valid__returns_healthy(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_enabled = True

        with _patch_feishu_client(mock_client):
            response = client.get("/api/feishu/health")

        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "healthy"
        assert data["feishu_enabled"] is True
        assert data["token_valid"] is True

    def test_get__feishu_enabled_token_exception__returns_degraded(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_enabled = True
        mock_client.get_access_token = AsyncMock(side_effect=Exception("timeout"))

        with _patch_feishu_client(mock_client):
            response = client.get("/api/feishu/health")

        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "degraded"
        assert data["token_valid"] is False

    def test_get__feishu_disabled__returns_disabled(self, client, mock_settings):
        mock_settings.feishu_enabled = False

        response = client.get("/api/feishu/health")

        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "disabled"
        assert data["feishu_enabled"] is False

    def test_get__feishu_enabled_token_none__returns_degraded(
        self, client, mock_settings, mock_client
    ):
        mock_settings.feishu_enabled = True
        mock_client.get_access_token = AsyncMock(return_value=None)

        with _patch_feishu_client(mock_client):
            response = client.get("/api/feishu/health")

        data = response.json()
        assert data["status"] == "degraded"
        assert data["token_valid"] is False


class TestInitHandlers:
    """init_handlers() correctly sets module-level globals."""

    @staticmethod
    def _get_module():
        import sys
        return sys.modules["shared.integrations.feishu.router"]

    def test_init_handlers__sets_all_globals(self):
        mod = self._get_module()

        eh = MagicMock(name="event_handler")
        bh = MagicMock(name="bot_handler")
        ch = MagicMock(name="card_handler")
        mr = MagicMock(name="message_recorder")

        init_handlers(event_h=eh, bot_h=bh, card_h=ch, message_h=mr)

        assert mod.event_handler is eh
        assert mod.bot_handler is bh
        assert mod.card_handler is ch
        assert mod.message_recorder is mr

    def test_init_handlers__defaults_to_none(self):
        mod = self._get_module()

        init_handlers(event_h=MagicMock())
        init_handlers()  # reset

        assert mod.event_handler is None
        assert mod.bot_handler is None
        assert mod.card_handler is None
        assert mod.message_recorder is None
