"""Unit tests for PJM core configuration values."""

from agents.pjm_agent.core.config import PJMCoreConfig


def test_pjm_core_config_prefers_decompose_notification_open_id() -> None:
    config = PJMCoreConfig.from_values(
        feishu_report_chat_id="report-chat",
        decompose_notify_open_id="approval-open-id",
    )

    assert config.decompose_notification_chat_id == "approval-open-id"


def test_pjm_core_config_falls_back_to_report_chat_id() -> None:
    config = PJMCoreConfig.from_values(
        feishu_report_chat_id="report-chat",
        decompose_notify_open_id="",
    )

    assert config.decompose_notification_chat_id == "report-chat"


def test_pjm_core_config_uses_planner_fallback_model_when_empty() -> None:
    config = PJMCoreConfig.from_values(decompose_model="")

    assert config.decompose_model == "claude-sonnet-4-20250514"
