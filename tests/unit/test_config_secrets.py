"""
Tests for SecretStr migration in shared.config.Settings.

Verifies that sensitive fields are wrapped in SecretStr so that
str(field) never leaks the actual value, while .get_secret_value()
still returns the plaintext when needed.
"""

import pytest
from pydantic import SecretStr, ValidationError


@pytest.fixture()
def secret_settings(monkeypatch):
    """Create a Settings instance with known secret values."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key-12345")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pg-pass-secret")
    monkeypatch.setenv("REDIS_PASSWORD", "redis-pass-secret")
    monkeypatch.setenv("MILVUS_TOKEN", "milvus-tok-secret")
    monkeypatch.setenv("FEISHU_APP_SECRET", "fs-app-secret")
    monkeypatch.setenv("FEISHU_ENCRYPT_KEY", "fs-enc-key")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "fs-verify-tok")
    monkeypatch.setenv("WECOM_SECRET", "wc-secret")
    monkeypatch.setenv("WECOM_TOKEN", "wc-token")
    monkeypatch.setenv("WECOM_ENCODING_AES_KEY", "wc-aes-key")
    monkeypatch.setenv("GITLAB_QA_TOKEN", "gl-qa-tok")
    monkeypatch.setenv("OPENPROJECT_API_KEY", "op-api-key")
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "oc-gw-tok")
    monkeypatch.setenv("SECRET_KEY", "my-secret-key-value")
    monkeypatch.setenv("A2A_JWT_SECRET", "my-a2a-jwt-secret")

    from shared.config import Settings

    return Settings()


class TestSecretStrFields:
    """Ensure secret fields are SecretStr and never leak via str()."""

    def test_anthropic_api_key_is_secret(self, secret_settings):
        assert isinstance(secret_settings.anthropic_api_key, SecretStr)
        assert "test-anthropic-key-12345" not in str(secret_settings.anthropic_api_key)
        assert "**********" in str(secret_settings.anthropic_api_key)

    def test_secret_value_accessible(self, secret_settings):
        assert secret_settings.anthropic_api_key.get_secret_value() == "test-anthropic-key-12345"

    def test_postgres_password_is_secret(self, secret_settings):
        assert isinstance(secret_settings.postgres_password, SecretStr)
        assert secret_settings.postgres_password.get_secret_value() == "pg-pass-secret"

    def test_redis_password_is_secret(self, secret_settings):
        assert isinstance(secret_settings.redis_password, SecretStr)
        assert secret_settings.redis_password.get_secret_value() == "redis-pass-secret"

    def test_milvus_token_is_secret(self, secret_settings):
        assert isinstance(secret_settings.milvus_token, SecretStr)

    def test_feishu_app_secret_is_secret(self, secret_settings):
        assert isinstance(secret_settings.feishu_app_secret, SecretStr)

    def test_wecom_secret_is_secret(self, secret_settings):
        assert isinstance(secret_settings.wecom_secret, SecretStr)

    def test_secret_key_is_secret(self, secret_settings):
        assert isinstance(secret_settings.secret_key, SecretStr)

    def test_a2a_jwt_secret_is_secret(self, secret_settings):
        assert isinstance(secret_settings.a2a_jwt_secret, SecretStr)

    def test_all_15_fields_are_secret(self, secret_settings):
        """All 15 migrated fields must be SecretStr."""
        secret_fields = [
            "anthropic_api_key",
            "postgres_password",
            "redis_password",
            "milvus_token",
            "feishu_app_secret",
            "feishu_encrypt_key",
            "feishu_verification_token",
            "wecom_secret",
            "wecom_token",
            "wecom_encoding_aes_key",
            "gitlab_qa_token",
            "openproject_api_key",
            "openclaw_gateway_token",
            "secret_key",
            "a2a_jwt_secret",
        ]
        for field_name in secret_fields:
            val = getattr(secret_settings, field_name)
            assert isinstance(val, SecretStr), f"{field_name} should be SecretStr, got {type(val)}"


class TestEmptySecrets:
    """SecretStr with empty string must be valid."""

    def test_empty_secret_works(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        from shared.config import Settings

        s = Settings()
        assert isinstance(s.anthropic_api_key, SecretStr)
        assert s.anthropic_api_key.get_secret_value() == ""


class TestDatabaseUrl:
    """database_url property must still embed the actual password."""

    def test_database_url_contains_password(self, secret_settings):
        url = secret_settings.database_url
        assert "pg-pass-secret" in url
        assert "postgresql+asyncpg://" in url

    def test_database_read_url_contains_password(self, secret_settings, monkeypatch):
        monkeypatch.setattr(secret_settings, "db_read_host", "replica-host")
        url = secret_settings.database_read_url
        assert "pg-pass-secret" in url


class TestRedisUrl:
    """redis_url property must still embed the actual password."""

    def test_redis_url_with_password(self, secret_settings):
        url = secret_settings.redis_url
        assert "redis-pass-secret" in url
        assert url.startswith("redis://:")

    def test_redis_url_without_password(self, monkeypatch):
        from shared.config import Settings

        s = Settings()
        # redis_password defaults to None
        url = s.redis_url
        assert "redis://" in url
        # No password segment
        assert ":@" not in url

    def test_redis_event_bus_url_with_password(self, secret_settings):
        url = secret_settings.redis_event_bus_url
        assert "redis-pass-secret" in url


class TestNonSecretFieldsUnchanged:
    """pm_api_key and internal_service_key stay as plain str."""

    def test_pm_api_key_is_str(self, secret_settings):
        assert isinstance(secret_settings.pm_api_key, str)

    def test_internal_service_key_is_str(self, secret_settings):
        assert isinstance(secret_settings.internal_service_key, str)


class TestProductionSecretValidation:
    """Production config must fail closed when required secrets are default or empty."""

    def test_production_rejects_default_or_empty_secrets(self):
        from shared.config import Settings

        with pytest.raises(
            ValidationError, match="production settings require non-default secrets"
        ):
            Settings(
                _env_file=None,
                app_env="production",
                postgres_password="",
                redis_password="",
                anthropic_api_key="",
                secret_key="change-me-in-production",
                pm_api_key="",
                internal_service_key="",
                a2a_jwt_secret="change-me-in-production-a2a",
            )

    def test_production_accepts_required_secrets(self):
        from shared.config import Settings

        settings = Settings(
            _env_file=None,
            app_env="production",
            postgres_password="pg-secret",
            redis_password="redis-secret",
            anthropic_api_key="llm-secret",
            secret_key="secret-key",
            pm_api_key="pm-key",
            internal_service_key="internal-key",
            a2a_jwt_secret="a2a-secret",
        )
        assert settings.app_env == "production"

    def test_production_rejects_enabled_feishu_without_signature_secret(self):
        from shared.config import Settings

        with pytest.raises(ValidationError, match="FEISHU"):
            Settings(
                _env_file=None,
                app_env="production",
                postgres_password="pg-secret",
                redis_password="redis-secret",
                anthropic_api_key="llm-secret",
                secret_key="secret-key",
                pm_api_key="pm-key",
                internal_service_key="internal-key",
                a2a_jwt_secret="a2a-secret",
                feishu_enabled=True,
                feishu_verify_signature=False,
                feishu_encrypt_key="",
            )

    def test_production_rejects_enabled_wecom_without_callback_secrets(self):
        from shared.config import Settings

        with pytest.raises(ValidationError, match="WECOM"):
            Settings(
                _env_file=None,
                app_env="production",
                postgres_password="pg-secret",
                redis_password="redis-secret",
                anthropic_api_key="llm-secret",
                secret_key="secret-key",
                pm_api_key="pm-key",
                internal_service_key="internal-key",
                a2a_jwt_secret="a2a-secret",
                wecom_enabled=True,
                wecom_token="",
                wecom_encoding_aes_key="",
            )
