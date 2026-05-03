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


def test_build_bitable_update_result_cards():
    renderer = FeishuToolCardRenderer()

    success = renderer.build_bitable_update_success(
        record_id="rec_1",
        field_lines="- **Status**: Done",
    )
    failure = renderer.build_bitable_update_failure(record_id="rec_1")

    assert success["header"]["template"] == "green"
    assert "`rec_1`" in success["elements"][0]["text"]["content"]
    assert failure["header"]["template"] == "red"
    assert "rec_1" in failure["elements"][0]["text"]["content"]


def test_build_bitable_create_result_cards():
    renderer = FeishuToolCardRenderer()

    success = renderer.build_bitable_create_success(
        record_id="rec_2",
        field_lines="- **Task**: Write docs",
    )
    failure = renderer.build_bitable_create_failure()

    assert success["header"]["template"] == "green"
    assert "`rec_2`" in success["elements"][0]["text"]["content"]
    assert failure["header"]["template"] == "red"


def test_build_bitable_rejection_and_reply_cards():
    renderer = FeishuToolCardRenderer()

    rejection = renderer.build_bitable_rejection(action_type="create")
    reply = renderer.build_ai_reply_card(reply="Done", elapsed=1.2)

    assert rejection["header"]["template"] == "grey"
    assert "创建" in rejection["header"]["title"]["content"]
    assert reply["header"]["template"] == "blue"
    assert "Done" in reply["elements"][0]["text"]["content"]
