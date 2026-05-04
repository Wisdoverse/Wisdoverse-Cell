"""Unit tests for user interaction gateway core configuration values."""

from services.gateways.user_interaction.core.config import UserInteractionCoreConfig


def test_user_interaction_core_config_preserves_models() -> None:
    config = UserInteractionCoreConfig.from_values(
        chat_model="chat-model",
        summary_model="summary-model",
        redis_url="redis://redis:6379/1",
        feishu_bitable_app_token="app-token",
        feishu_bitable_member_table_id="member-table",
        feishu_bitable_table_id="task-table",
        feishu_bitable_category_table_id="category-table",
        feishu_bitable_report_table_id="report-table",
    )

    assert config.chat_model == "chat-model"
    assert config.summary_model == "summary-model"
    assert config.redis_url == "redis://redis:6379/1"
    assert config.feishu_bitable_app_token == "app-token"
    assert config.feishu_bitable_member_table_id == "member-table"
    assert config.feishu_bitable_table_id == "task-table"
    assert config.feishu_bitable_category_table_id == "category-table"
    assert config.feishu_bitable_report_table_id == "report-table"


def test_user_interaction_core_config_uses_model_defaults_when_empty() -> None:
    config = UserInteractionCoreConfig.from_values(chat_model="", summary_model="")

    assert config.chat_model == "claude-sonnet-4-20250514"
    assert config.summary_model == "claude-haiku-4-5-20251001"
