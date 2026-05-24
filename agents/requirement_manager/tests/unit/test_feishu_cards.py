"""Tests for Requirement Manager Feishu card adapters."""

from agents.requirement_manager.adapters.feishu_cards import (
    FeishuRequirementCardRenderer,
)


def test_extraction_result_card_renders_feishu_card() -> None:
    renderer = FeishuRequirementCardRenderer()

    card = renderer.extraction_result_card(
        requirements=[
            {
                "id": "req_1",
                "title": "Offline recording",
                "description": "Support recording without a network connection.",
                "priority": "HIGH",
                "category": "feature",
            }
        ],
        meeting_title="Product review",
        questions_count=1,
    )

    assert card["header"]["title"]["content"] == "📋 提取了 1 个新需求"
    assert any(
        element.get("tag") == "action" for element in card.get("elements", [])
    )
