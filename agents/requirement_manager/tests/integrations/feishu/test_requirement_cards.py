"""Tests for requirements Feishu card templates."""

from datetime import UTC, datetime

import pytest

from agents.requirement_manager.integrations.feishu.cards.requirement import (
    build_batch_confirmation_card,
    build_batch_result_card,
    build_bot_help_card,
    build_calendar_reminder_card,
    build_prd_preview_card,
    build_requirement_confirmed_card,
    build_requirement_extracted_card,
    build_requirement_list_card,
    build_requirement_rejected_card,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_requirement(
    req_id: str = "req_001",
    title: str = "离线录音",
    description: str = "支持离线录音功能",
    priority: str = "HIGH",
    category: str = "功能",
) -> dict:
    return {
        "id": req_id,
        "title": title,
        "description": description,
        "priority": priority,
        "category": category,
    }


class TestRequirementCards:

    @pytest.mark.parametrize(
        ("priority", "expected_icon", "expected_color"),
        [
            pytest.param("HIGH", "🔴", "red", id="high-red"),
            pytest.param("MEDIUM", "🟡", "orange", id="medium-orange"),
            pytest.param("LOW", "🟢", "green", id="low-green"),
        ],
    )
    def test_priority_mapping(self, priority, expected_icon, expected_color):
        from agents.requirement_manager.integrations.feishu.cards.requirement import (
            PRIORITY_COLORS,
            PRIORITY_ICONS,
        )

        assert PRIORITY_ICONS[priority] == expected_icon
        assert PRIORITY_COLORS[priority] == expected_color

    # -- build_requirement_extracted_card ------------------------------------

    def test_build_extracted_card__with_meeting_title__includes_subtitle(self):
        reqs = [_make_requirement()]
        card = build_requirement_extracted_card(
            requirements=reqs, meeting_title="产品周会"
        )

        assert card["header"]["subtitle"]["content"] == "产品周会"
        assert "提取了 1 个新需求" in card["header"]["title"]["content"]

    def test_build_extracted_card__without_meeting_title__no_subtitle(self):
        reqs = [_make_requirement()]
        card = build_requirement_extracted_card(requirements=reqs, meeting_title="")

        assert "subtitle" not in card["header"]

    def test_build_extracted_card__with_questions__includes_warning(self):
        reqs = [_make_requirement()]
        card = build_requirement_extracted_card(
            requirements=reqs, questions_count=3
        )

        # There should be a markdown element containing the warning text
        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("待确认问题" in c and "3" in c for c in md_contents)

    def test_build_extracted_card__with_detail_url__includes_link_button(self):
        reqs = [_make_requirement()]
        card = build_requirement_extracted_card(
            requirements=reqs, detail_url="https://example.com/panel"
        )

        # Last action element should contain the link button
        action_elements = [el for el in card["elements"] if el.get("tag") == "action"]
        last_action = action_elements[-1]
        link_button = last_action["actions"][0]
        assert link_button["url"] == "https://example.com/panel"
        assert "打开面板" in link_button["text"]["content"]

    # -- build_requirement_confirmed_card ------------------------------------

    def test_build_confirmed_card__structure(self):
        req = _make_requirement(priority="HIGH")
        ts = datetime(2026, 2, 1, 10, 30, tzinfo=UTC)
        card = build_requirement_confirmed_card(
            requirement=req, confirmed_by="张三", confirmed_at=ts
        )

        assert card["header"]["title"]["content"] == "✅ 需求已确认"
        assert card["header"]["template"] == "green"

        # Check priority icon appears in markdown
        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("🔴" in c and "HIGH" in c for c in md_contents)

        # Check note with confirmer and timestamp
        notes = [el for el in card["elements"] if el.get("tag") == "note"]
        assert len(notes) == 1
        note_text = notes[0]["elements"][0]["content"]
        assert "张三" in note_text
        assert "2026-02-01 10:30" in note_text

    # -- build_requirement_rejected_card -------------------------------------

    def test_build_rejected_card__structure(self):
        req = _make_requirement(title="某需求")
        ts = datetime(2026, 3, 15, 14, 0, tzinfo=UTC)
        card = build_requirement_rejected_card(
            requirement=req,
            rejected_by="李四",
            reason="不符合产品方向",
            rejected_at=ts,
        )

        assert card["header"]["title"]["content"] == "❌ 需求已拒绝"
        assert card["header"]["template"] == "red"

        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("不符合产品方向" in c for c in md_contents)

        notes = [el for el in card["elements"] if el.get("tag") == "note"]
        note_text = notes[0]["elements"][0]["content"]
        assert "李四" in note_text
        assert "2026-03-15 14:00" in note_text

    # -- build_batch_confirmation_card ---------------------------------------

    def test_build_batch_confirmation_card__empty_list(self):
        card = build_batch_confirmation_card(requirements=[], chat_id="oc_abc")

        assert card["header"]["title"]["content"] == "📋 批量确认 (0 个需求)"
        assert "config" in card
        # Action buttons should still exist (with empty req_ids)
        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        assert len(action_els) == 1
        confirm_btn = action_els[0]["actions"][0]
        assert confirm_btn["value"]["req_ids"] == []
        assert confirm_btn["value"]["action"] == "batch_confirm_all"

    def test_build_batch_confirmation_card__with_data(self):
        reqs = [
            _make_requirement(req_id="r1", title="需求A", priority="HIGH"),
            _make_requirement(req_id="r2", title="需求B", priority="LOW"),
        ]
        card = build_batch_confirmation_card(requirements=reqs, chat_id="oc_x")

        assert "2 个需求" in card["header"]["title"]["content"]

        # Requirement titles should appear in markdown elements
        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("需求A" in c for c in md_contents)
        assert any("需求B" in c for c in md_contents)

        # Batch action buttons carry both req ids
        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        confirm_btn = action_els[0]["actions"][0]
        reject_btn = action_els[0]["actions"][1]
        assert set(confirm_btn["value"]["req_ids"]) == {"r1", "r2"}
        assert reject_btn["value"]["action"] == "batch_reject_all"
        assert reject_btn["value"]["chat_id"] == "oc_x"

    def test_build_batch_confirmation_card__more_than_10__truncated(self):
        reqs = [
            _make_requirement(req_id=f"r{i}", title=f"需求{i}")
            for i in range(15)
        ]
        card = build_batch_confirmation_card(requirements=reqs)

        # Header should show total count = 15
        assert "15 个需求" in card["header"]["title"]["content"]

        # Only first 10 titles rendered as markdown divs
        md_with_numbered = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el and "**" in el["text"]["content"]
        ]
        assert len(md_with_numbered) == 10

        # Should have a truncation note "还有 5 个需求"
        notes = [el for el in card["elements"] if el.get("tag") == "note"]
        note_texts = [n["elements"][0]["content"] for n in notes]
        assert any("还有 5 个需求" in t for t in note_texts)

        # But batch buttons still carry all 15 ids
        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        confirm_btn = action_els[0]["actions"][0]
        assert len(confirm_btn["value"]["req_ids"]) == 15

    # -- build_batch_result_card ---------------------------------------------

    def test_build_batch_result_card__confirm_type(self):
        card = build_batch_result_card(
            action_type="confirm",
            success_count=5,
            failed_count=0,
            operator_name="张三",
        )

        assert card["header"]["title"]["content"] == "✅ 批量确认完成"
        assert card["header"]["template"] == "green"

        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("张三" in c for c in md_contents)
        assert any("5/5 成功" in c for c in md_contents)

        # No failure warning when failed_count=0
        assert not any("⚠️" in c for c in md_contents)

    def test_build_batch_result_card__reject_with_failures(self):
        card = build_batch_result_card(
            action_type="reject",
            success_count=3,
            failed_count=2,
            operator_name="李四",
        )

        assert card["header"]["title"]["content"] == "❌ 批量拒绝完成"
        assert card["header"]["template"] == "red"

        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("3/5 成功" in c for c in md_contents)
        assert any("2 个需求处理失败" in c for c in md_contents)

    # -- build_requirement_list_card -----------------------------------------

    def test_build_list_card__page_1__no_prev_button(self):
        reqs = [_make_requirement(req_id="r1", title="需求A")]
        card = build_requirement_list_card(
            requirements=reqs, page=1, total_pages=3, total_count=10, chat_id="oc_1"
        )

        # Pagination action should have only "next" button
        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        # Last action element is pagination (per-req actions come first)
        pagination = action_els[-1]
        button_labels = [b["text"]["content"] for b in pagination["actions"]]
        assert any("下一页" in lbl for lbl in button_labels)
        assert not any("上一页" in lbl for lbl in button_labels)

        # Next page value should be 2
        next_btn = [b for b in pagination["actions"] if "下一页" in b["text"]["content"]][0]
        assert next_btn["value"]["page"] == 2
        assert next_btn["value"]["action"] == "list_next_page"

    def test_build_list_card__middle_page__both_buttons(self):
        reqs = [_make_requirement(req_id="r2", title="需求B")]
        card = build_requirement_list_card(
            requirements=reqs, page=2, total_pages=3, total_count=10, chat_id="oc_1"
        )

        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        pagination = action_els[-1]
        button_labels = [b["text"]["content"] for b in pagination["actions"]]
        assert any("上一页" in lbl for lbl in button_labels)
        assert any("下一页" in lbl for lbl in button_labels)

        prev_btn = [b for b in pagination["actions"] if "上一页" in b["text"]["content"]][0]
        next_btn = [b for b in pagination["actions"] if "下一页" in b["text"]["content"]][0]
        assert prev_btn["value"]["page"] == 1
        assert next_btn["value"]["page"] == 3

    def test_build_list_card__last_page__no_next_button(self):
        reqs = [_make_requirement(req_id="r3", title="需求C")]
        card = build_requirement_list_card(
            requirements=reqs, page=3, total_pages=3, total_count=10, chat_id="oc_1"
        )

        action_els = [el for el in card["elements"] if el.get("tag") == "action"]
        pagination = action_els[-1]
        button_labels = [b["text"]["content"] for b in pagination["actions"]]
        assert any("上一页" in lbl for lbl in button_labels)
        assert not any("下一页" in lbl for lbl in button_labels)

    def test_build_list_card__empty_requirements__shows_all_processed(self):
        card = build_requirement_list_card(
            requirements=[], page=1, total_pages=1, total_count=0, chat_id="oc_1"
        )

        md_contents = [
            el.get("text", {}).get("content", "")
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]
        assert any("暂无待确认需求" in c for c in md_contents)

    # -- build_prd_preview_card ----------------------------------------------

    def test_build_prd_preview_card__truncates_at_500_chars(self):
        long_content = "A" * 600
        ts = datetime(2026, 1, 20, 8, 0, tzinfo=UTC)
        card = build_prd_preview_card(
            prd_content=long_content,
            requirements_count=7,
            generated_at=ts,
        )

        assert card["header"]["title"]["content"] == "📄 PRD 文档已生成"
        assert card["header"]["template"] == "green"

        # Find the plain_text element that holds the preview
        plain_divs = [
            el for el in card["elements"]
            if el.get("tag") == "div"
            and el.get("text", {}).get("tag") == "plain_text"
        ]
        assert len(plain_divs) == 1
        preview_text = plain_divs[0]["text"]["content"]
        # First 500 chars preserved, then truncation marker
        assert preview_text.startswith("A" * 500)
        assert "已截断" in preview_text
        assert len(preview_text) < 600  # shorter than original

        # Summary should include count and time
        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and el.get("text", {}).get("tag") == "lark_md"
        ]
        assert any("7" in c and "2026-01-20 08:00" in c for c in md_contents)

    # -- build_bot_help_card -------------------------------------------------

    def test_build_bot_help_card__static_structure(self):
        card = build_bot_help_card()

        assert card["header"]["title"]["content"] == "🤖 需求管理助手"
        assert card["header"]["template"] == "blue"
        assert len(card["elements"]) == 1

        md_el = card["elements"][0]
        assert md_el["tag"] == "div"
        content = md_el["text"]["content"]
        assert "/list" in content
        assert "/export" in content
        assert "/help" in content

    # -- build_calendar_reminder_card ----------------------------------------

    def test_build_calendar_reminder_card__more_than_5_attendees__truncated(self):
        attendees = [f"user{i}@example.com" for i in range(8)]
        card = build_calendar_reminder_card(
            event_title="需求评审会",
            start_time="2026-02-26 14:00",
            organizer="王五",
            attendees=attendees,
            keywords_found=["需求", "评审"],
        )

        assert card["header"]["title"]["content"] == "📅 需求相关会议即将开始"
        assert card["header"]["template"] == "orange"

        md_contents = [
            el["text"]["content"]
            for el in card["elements"]
            if el.get("tag") == "div" and "text" in el
        ]

        # Event title
        assert any("需求评审会" in c for c in md_contents)
        # Start time
        assert any("2026-02-26 14:00" in c for c in md_contents)
        # Organizer
        assert any("王五" in c for c in md_contents)
        # Attendees truncated: first 5 shown, then "等 8 人"
        attendees_line = [c for c in md_contents if "参与者" in c][0]
        assert "user0@example.com" in attendees_line
        assert "user4@example.com" in attendees_line
        assert "user5@example.com" not in attendees_line
        assert "等 8 人" in attendees_line
        # Keywords
        assert any("需求" in c and "评审" in c for c in md_contents)
