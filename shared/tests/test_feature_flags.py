"""B12: Feature flag tests."""
from shared.config import Settings


class TestDeliveryServiceFeatureFlag:
    """Verify use_new_delivery_service feature flag."""

    def test_default_is_false(self):
        settings = Settings(
            postgres_password="test",
            _env_file=None,
        )
        assert settings.use_new_delivery_service is False

    def test_can_enable_via_constructor(self):
        settings = Settings(
            postgres_password="test",
            use_new_delivery_service=True,
            _env_file=None,
        )
        assert settings.use_new_delivery_service is True
