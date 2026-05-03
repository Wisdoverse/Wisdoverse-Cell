"""Tests for the PJM Feishu card renderer adapter."""

from agents.pjm_agent.adapters.feishu_cards import FeishuPJMCardRenderer


def _stats() -> dict:
    return {
        "total": 2,
        "op_total": 1,
        "feishu_total": 1,
        "avg_progress": 50,
        "by_status": {"In Progress": 1, "Done": 1},
        "by_project": {
            "Project A": {
                "total": 2,
                "by_status": {"In Progress": 1, "Done": 1},
                "source": "op",
            }
        },
        "by_assignee": {
            "Alice": {
                "total": 2,
                "progress_sum": 100,
                "by_status": {"In Progress": 1, "Done": 1},
            }
        },
        "overdue": [],
    }


def test_build_daily_report_card_returns_feishu_payload():
    card = FeishuPJMCardRenderer().build_daily_report_card(_stats())

    assert card["header"]["title"]["content"].startswith("📋 项目日报")
    assert card["config"]["wide_screen_mode"] is True
    assert card["elements"]


def test_build_weekly_report_card_returns_feishu_payload():
    card = FeishuPJMCardRenderer().build_weekly_report_card(_stats())

    assert card["header"]["title"]["content"].startswith("📊 项目周报")
    assert card["config"]["wide_screen_mode"] is True
    assert card["elements"]


def test_build_decomposition_approval_card_returns_feishu_payload():
    card = FeishuPJMCardRenderer().build_decomposition_approval_card(
        wp_id=123,
        subject="Split feature",
        wbs_result={
            "summary": "Split feature",
            "subtasks": [
                {
                    "subject": "Story",
                    "priority": "medium",
                    "estimated_days": 1,
                    "children": [],
                }
            ],
        },
    )

    assert card["header"]["title"]["content"] == "📊 任务拆解待审批"
    assert card["elements"]
