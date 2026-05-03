"""Tests for user-interaction Feishu card rendering adapters."""

from shared.integrations.feishu.cards.tools import (
    FeishuToolCardRenderer,
)


def test_build_bitable_update_confirmation_contains_action_id():
    card = FeishuToolCardRenderer().build_bitable_update_confirmation(
        title="Task A",
        record_id="rec_1",
        field_lines="- **Status**: Done",
        action_id="action_1",
        is_group_chat=True,
    )

    assert card["header"]["title"]["content"] == "📝 表格修改确认"
    actions = card["elements"][2]["actions"]
    assert actions[0]["value"]["action_id"] == "action_1"
    assert any(el.get("tag") == "note" for el in card["elements"])


def test_build_bitable_create_confirmation_contains_action_id():
    card = FeishuToolCardRenderer().build_bitable_create_confirmation(
        field_lines="- **Task**: Write docs",
        action_id="action_2",
        is_group_chat=False,
    )

    assert card["header"]["title"]["content"] == "📋 新建任务确认"
    actions = card["elements"][2]["actions"]
    assert actions[0]["value"]["action_id"] == "action_2"
