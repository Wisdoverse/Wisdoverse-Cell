"""Unit tests for user interaction gateway core configuration values."""

from services.gateways.user_interaction.core.config import UserInteractionCoreConfig


def test_user_interaction_core_config_preserves_models() -> None:
    config = UserInteractionCoreConfig.from_values(
        chat_model="chat-model",
        summary_model="summary-model",
    )

    assert config.chat_model == "chat-model"
    assert config.summary_model == "summary-model"


def test_user_interaction_core_config_uses_model_defaults_when_empty() -> None:
    config = UserInteractionCoreConfig.from_values(chat_model="", summary_model="")

    assert config.chat_model == "claude-sonnet-4-20250514"
    assert config.summary_model == "claude-haiku-4-5-20251001"
