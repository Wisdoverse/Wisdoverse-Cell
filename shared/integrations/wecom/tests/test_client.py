# shared/integrations/wecom/tests/test_client.py
"""Tests for WeCom API client."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.integrations.wecom.client import WecomClient


class TestWecomClient:
    @pytest.fixture
    def client(self):
        return WecomClient(
            corp_id="ww123",
            secret="secret",
            agent_id=1000001,
            base_url="https://qyapi.weixin.qq.com/cgi-bin"
        )

    def _mock_response(self, json_data: dict):
        """Create a mock response object."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = json_data
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    @pytest.mark.asyncio
    async def test_get_access_token(self, client):
        mock_resp = self._mock_response({
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "test_token",
            "expires_in": 7200
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            token = await client.get_access_token()
            assert token == "test_token"

    @pytest.mark.asyncio
    async def test_get_access_token_cached(self, client):
        mock_resp = self._mock_response({
            "errcode": 0,
            "errmsg": "ok",
            "access_token": "test_token",
            "expires_in": 7200
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            token1 = await client.get_access_token()
            token2 = await client.get_access_token()

            assert token1 == token2
            # Should only call the API once due to caching
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_send_text_message(self, client):
        token_resp = self._mock_response({
            "errcode": 0,
            "access_token": "token",
            "expires_in": 7200
        })
        send_resp = self._mock_response({
            "errcode": 0,
            "errmsg": "ok",
            "msgid": "msg_123"
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=token_resp)
            mock_client.post = AsyncMock(return_value=send_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await client.send_text_message(
                user_id="user1",
                content="Hello"
            )

            assert result == "msg_123"

    @pytest.mark.asyncio
    async def test_send_template_card(self, client):
        token_resp = self._mock_response({
            "errcode": 0,
            "access_token": "token",
            "expires_in": 7200
        })
        send_resp = self._mock_response({
            "errcode": 0,
            "errmsg": "ok",
            "msgid": "msg_456"
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=token_resp)
            mock_client.post = AsyncMock(return_value=send_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            card = {
                "card_type": "button_interaction",
                "main_title": {"title": "Test"},
                "button_list": []
            }

            result = await client.send_template_card(
                user_id="user1",
                card=card
            )

            assert result == "msg_456"

    @pytest.mark.asyncio
    async def test_update_template_card(self, client):
        token_resp = self._mock_response({
            "errcode": 0,
            "access_token": "token",
            "expires_in": 7200
        })
        update_resp = self._mock_response({
            "errcode": 0,
            "errmsg": "ok"
        })

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=token_resp)
            mock_client.post = AsyncMock(return_value=update_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await client.update_template_card(
                response_code="resp_123",
                card={"card_type": "button_interaction"}
            )

            assert result is True
