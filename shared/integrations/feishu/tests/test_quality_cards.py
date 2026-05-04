"""Tests for QA Feishu card renderers."""

from shared.integrations.feishu.cards.quality import FeishuQualityCardRenderer


def test_acceptance_alert_message_renders_failure_card() -> None:
    card = FeishuQualityCardRenderer().build_acceptance_alert_message(
        agent_name="qa-agent",
        summary={"l0_gate": "FAIL", "l1_check": "PASS"},
        findings=[
            {
                "level": "L0",
                "status": "FAIL",
                "check": "secrets",
                "details": "Secret detected in config",
                "file": "app.py",
                "line": 12,
            }
        ],
        mr_iid=137,
        gitlab_api_url="https://gitlab.example.com/api/v4",
        gitlab_project_id="42",
    )

    assert card["msg_type"] == "interactive"
    assert card["card"]["header"]["template"] == "red"
    assert card["card"]["header"]["title"]["content"] == "\u274c QA: qa-agent L0=FAIL L1=PASS"

    content = card["card"]["elements"][0]["content"]
    assert "[L0] **secrets**" in content
    assert "`app.py:12`" in content
    assert "https://gitlab.example.com/42/-/merge_requests/137" in content


def test_acceptance_alert_message_renders_warn_card_without_mr_link() -> None:
    card = FeishuQualityCardRenderer().build_acceptance_alert_message(
        agent_name="qa-agent",
        summary={"l0_gate": "PASS", "l1_check": "WARN"},
        findings=[],
    )

    assert card["card"]["header"]["template"] == "orange"
    assert card["card"]["elements"][0]["content"].endswith("No issues")
