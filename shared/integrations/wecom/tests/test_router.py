"""Tests for WeCom webhook router."""

import sys as _sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.api import ApiErrorCode
from shared.integrations.wecom.router import router

_wecom_router_mod = _sys.modules["shared.integrations.wecom.router"]


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestWecomRouter:
    def test_signature_verification_uses_wecom_protocol_contract(self):
        token = "token"
        timestamp = "123"
        nonce = "abc"
        encrypted = "encrypted"
        expected = "eb6446007684a9d284aae2904e88bc1f41a60caa"

        assert _wecom_router_mod._verify_wecom_signature(
            expected,
            timestamp,
            nonce,
            encrypted,
            token,
        )

    def test_url_verification(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = False
            mock_settings.app_env = "development"
            mock_settings.wecom_token.get_secret_value.return_value = ""
            mock_settings.wecom_encoding_aes_key.get_secret_value.return_value = ""
            mock_settings.wecom_corp_id = ""
            response = client.get(
                "/api/wecom/webhook",
                params={
                    "msg_signature": "sig",
                    "timestamp": "123",
                    "nonce": "abc",
                    "echostr": "test_echo",
                },
            )
        assert response.status_code == 200

    def test_url_verification_requires_crypto_config_when_enabled(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = True
            mock_settings.app_env = "production"
            mock_settings.wecom_token.get_secret_value.return_value = ""
            mock_settings.wecom_encoding_aes_key.get_secret_value.return_value = ""
            mock_settings.wecom_corp_id = ""
            response = client.get(
                "/api/wecom/webhook",
                params={
                    "msg_signature": "sig",
                    "timestamp": "123",
                    "nonce": "abc",
                    "echostr": "test_echo",
                },
            )
            assert response.status_code == 503
            assert (
                response.headers["x-error-code"]
                == ApiErrorCode.WECOM_SECURITY_NOT_CONFIGURED.value
            )

    def test_url_verification_rejects_invalid_signature_when_enabled(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = True
            mock_settings.app_env = "development"
            mock_settings.wecom_token.get_secret_value.return_value = "token"
            mock_settings.wecom_encoding_aes_key.get_secret_value.return_value = (
                "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
            )
            mock_settings.wecom_corp_id = "corp123"
            response = client.get(
                "/api/wecom/webhook",
                params={
                    "msg_signature": "invalid",
                    "timestamp": "123",
                    "nonce": "abc",
                    "echostr": "encrypted",
                },
            )
            assert response.status_code == 403
            assert response.json()["detail"] == "Invalid WeCom signature"
            assert (
                response.headers["x-error-code"]
                == ApiErrorCode.WECOM_INVALID_SIGNATURE.value
            )

    def test_webhook_rejects_missing_encrypted_payload_when_enabled(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = True
            mock_settings.app_env = "production"
            mock_settings.wecom_token.get_secret_value.return_value = "token"
            mock_settings.wecom_encoding_aes_key.get_secret_value.return_value = (
                "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
            )
            mock_settings.wecom_corp_id = "corp123"
            response = client.post(
                "/api/wecom/webhook",
                params={
                    "msg_signature": "sig",
                    "timestamp": "123",
                    "nonce": "abc",
                },
                content=b"<xml><MsgType>text</MsgType></xml>",
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Missing encrypted WeCom payload"
        assert (
            response.headers["x-error-code"]
            == ApiErrorCode.WECOM_MISSING_ENCRYPTED_PAYLOAD.value
        )

    def test_webhook_rejects_invalid_xml_when_security_required(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = True
            mock_settings.app_env = "production"
            mock_settings.wecom_token.get_secret_value.return_value = "token"
            mock_settings.wecom_encoding_aes_key.get_secret_value.return_value = (
                "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
            )
            mock_settings.wecom_corp_id = "corp123"
            response = client.post(
                "/api/wecom/webhook",
                params={
                    "msg_signature": "sig",
                    "timestamp": "123",
                    "nonce": "abc",
                },
                content=b"not-xml",
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid WeCom XML payload"
        assert (
            response.headers["x-error-code"]
            == ApiErrorCode.WECOM_INVALID_XML_PAYLOAD.value
        )

    def test_health_check_disabled(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = False
            response = client.get("/api/wecom/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "disabled"

    def test_health_check_enabled(self, client):
        with patch.object(_wecom_router_mod, "settings") as mock_settings:
            mock_settings.wecom_enabled = True
            mock_settings.wecom_bot_enabled = True
            mock_settings.wecom_card_enabled = True
            response = client.get("/api/wecom/health")
            assert response.status_code == 200
            data = response.json()
            assert data["wecom_enabled"] is True
