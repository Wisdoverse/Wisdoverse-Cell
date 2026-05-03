"""
Unit Tests - Webhook dedup and Challenge verification

Tests for Redis-based message deduplication and challenge response.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeReplyCardRenderer:
    def build_ai_reply_card(self, *, reply: str, elapsed: float) -> dict:
        return {"kind": "reply", "reply": reply, "elapsed": elapsed}


@pytest.fixture(autouse=True)
def mock_redis():
    """Mock the Redis client used by _is_duplicate."""
    mock_r = AsyncMock()
    with patch("services.gateways.user_interaction.api.webhook._get_redis", return_value=mock_r):
        yield mock_r


@pytest.fixture
def webhook_client():
    """FastAPI client with only the webhook router mounted."""
    from services.gateways.user_interaction.api.webhook import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.mark.asyncio
async def test_is_duplicate_first_time(mock_redis):
    """First time receiving a message - not a duplicate (Redis SET nx returns True)."""
    from services.gateways.user_interaction.api.webhook import _is_duplicate

    mock_redis.set = AsyncMock(return_value=True)  # nx=True succeeds -> key was set
    result = await _is_duplicate("msg_001")
    assert result is False
    mock_redis.set.assert_awaited_once_with("chat:dedup:msg_001", "1", nx=True, ex=300)


@pytest.mark.asyncio
async def test_is_duplicate_second_time(mock_redis):
    """Same message seen again - duplicate (Redis SET nx returns None/False)."""
    from services.gateways.user_interaction.api.webhook import _is_duplicate

    mock_redis.set = AsyncMock(return_value=None)  # nx=True fails -> key already existed
    result = await _is_duplicate("msg_002")
    assert result is True


def test_challenge_response():
    """ChallengeResponse correctly echoes back the challenge value."""
    from services.gateways.user_interaction.api.schemas import ChallengeResponse

    resp = ChallengeResponse(challenge="test_token_abc")
    assert resp.challenge == "test_token_abc"
    assert resp.model_dump() == {"challenge": "test_token_abc"}


def test_feishu_webhook_signed_challenge_returns_challenge(
    webhook_client, monkeypatch
):
    """The Feishu endpoint verifies signatures before accepting challenge traffic."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    feishu_client = MagicMock()
    feishu_client.verify_signature.return_value = True
    monkeypatch.setattr(webhook_mod.settings, "feishu_verify_signature", True)
    monkeypatch.setattr(webhook_mod, "get_feishu_client", lambda: feishu_client)

    payload = {"challenge": "test_token_abc"}
    response = webhook_client.post(
        "/webhook/feishu",
        json=payload,
        headers={
            "X-Lark-Request-Timestamp": "1706169600",
            "X-Lark-Request-Nonce": "nonce_abc",
            "X-Lark-Signature": "valid_signature",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"challenge": "test_token_abc"}
    timestamp, nonce, raw_body, signature = feishu_client.verify_signature.call_args.args
    assert timestamp == "1706169600"
    assert nonce == "nonce_abc"
    assert json.loads(raw_body) == payload
    assert signature == "valid_signature"


def test_feishu_webhook_invalid_signature_rejects_challenge(
    webhook_client, monkeypatch
):
    """Invalid signatures fail closed and do not complete URL verification."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    feishu_client = MagicMock()
    feishu_client.verify_signature.return_value = False
    monkeypatch.setattr(webhook_mod.settings, "feishu_verify_signature", True)
    monkeypatch.setattr(webhook_mod, "get_feishu_client", lambda: feishu_client)

    response = webhook_client.post(
        "/webhook/feishu",
        json={"challenge": "must_not_echo"},
        headers={
            "X-Lark-Request-Timestamp": "1706169600",
            "X-Lark-Request-Nonce": "nonce_abc",
            "X-Lark-Signature": "invalid_signature",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid signature"}


def test_feishu_webhook_rejects_bad_signature_before_json_parse(
    webhook_client, monkeypatch
):
    """Signature verification must run before parsing untrusted JSON bodies."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    feishu_client = MagicMock()
    feishu_client.verify_signature.return_value = False
    monkeypatch.setattr(webhook_mod.settings, "feishu_verify_signature", True)
    monkeypatch.setattr(webhook_mod, "get_feishu_client", lambda: feishu_client)

    response = webhook_client.post(
        "/webhook/feishu",
        content=b"not-json",
        headers={
            "X-Lark-Request-Timestamp": "1706169600",
            "X-Lark-Request-Nonce": "nonce_abc",
            "X-Lark-Signature": "invalid_signature",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid signature"}
    assert feishu_client.verify_signature.called


def test_feishu_webhook_invalid_json_returns_bad_request_when_signature_disabled(
    webhook_client, monkeypatch
):
    """Development-only unsigned mode still rejects malformed webhook bodies."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    monkeypatch.setattr(webhook_mod.settings, "feishu_verify_signature", False)

    response = webhook_client.post(
        "/webhook/feishu",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid JSON"}


def test_build_reply_card_uses_configured_renderer():
    """Webhook replies use the injected card-renderer port."""
    from services.gateways.user_interaction.api.webhook import _build_reply_card
    from services.gateways.user_interaction.core.card_ports import (
        configure_tool_card_renderer,
    )

    configure_tool_card_renderer(FakeReplyCardRenderer())
    try:
        assert _build_reply_card("Done", 1.2) == {
            "kind": "reply",
            "reply": "Done",
            "elapsed": 1.2,
        }
    finally:
        configure_tool_card_renderer(None)


@pytest.mark.asyncio
async def test_process_message_logs_user_hash_for_direct_card(monkeypatch):
    """Message processing logs hashed user identifiers, not raw platform IDs."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    feishu_client = MagicMock()
    feishu_client.add_reaction = AsyncMock()
    agent = MagicMock()
    agent.handle_request = AsyncMock(return_value={"reply": ""})
    logger = MagicMock()

    monkeypatch.setattr(webhook_mod, "get_feishu_client", lambda: feishu_client)
    monkeypatch.setattr(webhook_mod, "get_agent", lambda: agent)
    monkeypatch.setattr(webhook_mod, "logger", logger)
    monkeypatch.setattr(webhook_mod, "_metrics_available", False)

    await webhook_mod._process_message(
        "ou_raw_user",
        "hello",
        {"message_id": "msg_1"},
        "p2p",
    )

    card_call = next(call for call in logger.info.call_args_list if call.args[0] == "msg_card_sent")
    assert card_call.kwargs["user_hash"] == webhook_mod._hash_user_id("ou_raw_user")
    assert "user_id" not in card_call.kwargs


@pytest.mark.asyncio
async def test_process_message_error_logs_user_hash(monkeypatch):
    """Error logs must not include raw platform user IDs."""
    import services.gateways.user_interaction.api.webhook as webhook_mod

    feishu_client = MagicMock()
    feishu_client.add_reaction = AsyncMock()
    feishu_client.send_message = AsyncMock()
    agent = MagicMock()
    agent.handle_request = AsyncMock(side_effect=RuntimeError("boom"))
    logger = MagicMock()

    monkeypatch.setattr(webhook_mod, "get_feishu_client", lambda: feishu_client)
    monkeypatch.setattr(webhook_mod, "get_agent", lambda: agent)
    monkeypatch.setattr(webhook_mod, "logger", logger)
    monkeypatch.setattr(webhook_mod, "_metrics_available", False)

    await webhook_mod._process_message(
        "ou_raw_user",
        "hello",
        {"message_id": "msg_1"},
        "p2p",
    )

    error_call = next(call for call in logger.error.call_args_list if call.args[0] == "msg_process_error")
    assert error_call.kwargs["user_hash"] == webhook_mod._hash_user_id("ou_raw_user")
    assert "user_id" not in error_call.kwargs
