"""Service-layer wiring for user interaction gateway core configuration."""

from __future__ import annotations

from shared.config import settings as app_settings

from ..core.config import UserInteractionCoreConfig


def build_user_interaction_core_config() -> UserInteractionCoreConfig:
    """Build explicit gateway core config from process settings at the service edge."""
    return UserInteractionCoreConfig.from_values(
        chat_model=app_settings.chat_model,
        summary_model=app_settings.summary_model,
        redis_url=app_settings.redis_url,
        feishu_bitable_app_token=app_settings.feishu_bitable_app_token,
        feishu_bitable_member_table_id=app_settings.feishu_bitable_member_table_id,
        feishu_bitable_table_id=app_settings.feishu_bitable_table_id,
        feishu_bitable_category_table_id=app_settings.feishu_bitable_category_table_id,
        feishu_bitable_report_table_id=app_settings.feishu_bitable_report_table_id,
    )
