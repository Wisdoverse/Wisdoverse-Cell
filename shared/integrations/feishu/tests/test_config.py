"""Test Feishu configuration fields in shared.config.Settings."""

from shared.config import Settings


def _make_settings(**overrides) -> Settings:
    """Create a Settings instance with required fields and no .env loading."""
    defaults = {
        "postgres_password": "test",
        "anthropic_api_key": "test",
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
class TestFeishuConfigDefaults:
    """Verify default values when no env vars are set."""

    def test_feishu_enabled__default__false(self, monkeypatch):
        monkeypatch.delenv("FEISHU_ENABLED", raising=False)
        s = _make_settings()
        assert s.feishu_enabled is False

    def test_verify_signature__default__true(self, monkeypatch):
        monkeypatch.delenv("FEISHU_VERIFY_SIGNATURE", raising=False)
        s = _make_settings()
        assert s.feishu_verify_signature is True

    def test_api_base_url__default__standard_url(self, monkeypatch):
        monkeypatch.delenv("FEISHU_API_BASE_URL", raising=False)
        s = _make_settings()
        assert s.feishu_api_base_url == "https://open.feishu.cn/open-apis"

    def test_token_refresh_buffer__default__300(self, monkeypatch):
        monkeypatch.delenv("FEISHU_TOKEN_REFRESH_BUFFER", raising=False)
        s = _make_settings()
        assert s.feishu_token_refresh_buffer == 300

    def test_bot_enabled__default__true(self, monkeypatch):
        monkeypatch.delenv("FEISHU_BOT_ENABLED", raising=False)
        s = _make_settings()
        assert s.feishu_bot_enabled is True

    def test_credentials__default__none(self, monkeypatch):
        monkeypatch.delenv("FEISHU_APP_ID", raising=False)
        monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
        s = _make_settings()
        assert s.feishu_app_id is None
        assert s.feishu_app_secret is None


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------
class TestFeishuConfigFromEnv:
    """Verify fields load from environment variables."""

    def test_app_id_and_secret__from_env(self, monkeypatch):
        monkeypatch.setenv("FEISHU_APP_ID", "cli_test123")
        monkeypatch.setenv("FEISHU_APP_SECRET", "secret123")
        s = _make_settings()
        assert s.feishu_app_id == "cli_test123"
        assert s.feishu_app_secret.get_secret_value() == "secret123"

    def test_enabled__from_env(self, monkeypatch):
        monkeypatch.setenv("FEISHU_ENABLED", "true")
        s = _make_settings()
        assert s.feishu_enabled is True


# ---------------------------------------------------------------------------
# Message recording
# ---------------------------------------------------------------------------
class TestMessageRecordingConfig:
    """Verify message-recording defaults and env overrides."""

    def test_recording_defaults__disabled(self, monkeypatch):
        monkeypatch.delenv("FEISHU_MESSAGE_RECORDING_ENABLED", raising=False)
        monkeypatch.delenv("FEISHU_MONITORED_CHAT_IDS_RAW", raising=False)
        monkeypatch.delenv("FEISHU_SESSION_TIMEOUT", raising=False)
        monkeypatch.delenv("FEISHU_MIN_MESSAGES_TO_EXTRACT", raising=False)
        s = _make_settings()
        assert s.feishu_message_recording_enabled is False
        assert s.feishu_session_timeout == 300
        assert s.feishu_min_messages_to_extract == 5

    def test_recording_from_env__enabled_with_timeout(self, monkeypatch):
        monkeypatch.setenv("FEISHU_MESSAGE_RECORDING_ENABLED", "true")
        monkeypatch.setenv("FEISHU_SESSION_TIMEOUT", "600")
        s = _make_settings()
        assert s.feishu_message_recording_enabled is True
        assert s.feishu_session_timeout == 600


# ---------------------------------------------------------------------------
# Monitored chat IDs (computed property)
# ---------------------------------------------------------------------------
class TestMonitoredChatIds:
    """Verify feishu_monitored_chat_ids property parsing."""

    def test_empty_string__returns_empty_list(self):
        s = _make_settings(feishu_monitored_chat_ids_raw="")
        assert s.feishu_monitored_chat_ids == []

    def test_comma_separated__returns_list(self):
        s = _make_settings(feishu_monitored_chat_ids_raw="oc_chat1,oc_chat2,oc_chat3")
        assert s.feishu_monitored_chat_ids == ["oc_chat1", "oc_chat2", "oc_chat3"]

    def test_single_item__returns_single_element_list(self):
        s = _make_settings(feishu_monitored_chat_ids_raw="oc_only")
        assert s.feishu_monitored_chat_ids == ["oc_only"]
