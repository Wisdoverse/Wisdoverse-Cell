"""Service-layer wiring for PJM core configuration."""

from __future__ import annotations

from shared.config import settings as app_settings

from ..core.config import PJMCoreConfig


def build_pjm_core_config() -> PJMCoreConfig:
    """Build explicit PJM core config from process settings at the service edge."""
    return PJMCoreConfig.from_values(
        decompose_model=app_settings.decompose_model,
        feishu_report_chat_id=app_settings.feishu_report_chat_id,
        decompose_notify_open_id=app_settings.decompose_notify_open_id,
        decompose_project_ids=app_settings.decompose_project_ids,
        feishu_pm_app_token=app_settings.feishu_pm_app_token,
        feishu_pm_member_table_id=app_settings.feishu_pm_member_table_id,
        feishu_pm_project_table_id=app_settings.feishu_pm_project_table_id,
        feishu_pm_rules_table_id=app_settings.feishu_pm_rules_table_id,
        feishu_pm_task_table_id=app_settings.feishu_pm_task_table_id,
    )
