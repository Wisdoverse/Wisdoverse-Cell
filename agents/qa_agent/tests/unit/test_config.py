"""Unit tests for QA core configuration values."""

from agents.qa_agent.core.config import QACoreConfig


def test_parses_high_severity_checks_from_comma_separated_string() -> None:
    config = QACoreConfig.from_values(
        high_severity_check_list="secrets, dependency-risk, , flaky-test"
    )

    assert config.high_severity_check_list == (
        "secrets",
        "dependency-risk",
        "flaky-test",
    )


def test_prefers_qa_specific_feishu_webhook() -> None:
    config = QACoreConfig.from_values(
        qa_feishu_webhook_url="https://hook.qa.example.com",
        feishu_webhook_url="https://hook.default.example.com",
    )

    assert config.notification_webhook_url == "https://hook.qa.example.com"


def test_falls_back_to_default_feishu_webhook() -> None:
    config = QACoreConfig.from_values(
        qa_feishu_webhook_url="",
        feishu_webhook_url="https://hook.default.example.com",
    )

    assert config.notification_webhook_url == "https://hook.default.example.com"
