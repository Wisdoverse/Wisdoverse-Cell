# shared/integrations/wecom/tests/test_config.py
"""Tests for WeCom configuration."""
import os
from unittest.mock import patch

from shared.integrations.wecom.config import WecomConfig


class TestWecomConfig:
    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            config = WecomConfig(
                corp_id="ww123",
                agent_id=1000001,
                secret="secret",
                token="token",
                encoding_aes_key="aes_key"
            )
            assert config.corp_id == "ww123"
            assert config.agent_id == 1000001
            assert config.api_base_url == "https://qyapi.weixin.qq.com/cgi-bin"

    def test_from_env(self):
        env = {
            "WECOM_CORP_ID": "ww456",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_SECRET": "my_secret",
            "WECOM_TOKEN": "my_token",
            "WECOM_ENCODING_AES_KEY": "my_aes_key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = WecomConfig()
            assert config.corp_id == "ww456"
            assert config.agent_id == 1000002

    def test_enabled_default_false(self):
        config = WecomConfig(
            corp_id="ww123",
            agent_id=1000001,
            secret="secret",
            token="token",
            encoding_aes_key="aes_key"
        )
        assert config.enabled is False

    def test_token_refresh_buffer(self):
        config = WecomConfig(
            corp_id="ww123",
            agent_id=1000001,
            secret="secret",
            token="token",
            encoding_aes_key="aes_key"
        )
        assert config.token_refresh_buffer == 300
