"""Tests for Feishu card, bot, and event handlers.

Uses shared fixtures from conftest: mock_feishu_client, mock_requirement_agent,
MockIngestResult, make_card_action.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.integrations.feishu.bot import BotHandler
from agents.requirement_manager.integrations.feishu.card import CardHandler
from agents.requirement_manager.integrations.feishu.event import EventHandler

from .conftest import MockIngestResult, MockPRDResult, make_card_action, make_feishu_event

# ──────────────────────────────────────────────
# CardHandler
# ──────────────────────────────────────────────


class TestCardHandler:
    """Tests for CardHandler.handle_action and internal helpers."""

    @pytest.fixture
    def handler(self, mock_feishu_client, mock_requirement_agent):
        return CardHandler(mock_feishu_client, mock_requirement_agent)

    # ── action dispatch: parametrized confirm / reject / view_detail / list_confirm / list_reject ──

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "action_type, toast_type",
        [
            pytest.param("confirm_requirement", "success", id="confirm"),
            pytest.param("reject_requirement", "success", id="reject"),
            pytest.param("view_detail", "success", id="view_detail"),
            pytest.param("list_confirm_requirement", "success", id="list_confirm"),
            pytest.param("list_reject_requirement", "success", id="list_reject"),
        ],
    )
    async def test_handle_action__dispatch_action__returns_correct_toast(
        self, handler, action_type, toast_type
    ):
        data = make_card_action(
            action_type=action_type,
            req_id="req_123",
            extra={"page": 1, "chat_id": "oc_chat"},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == toast_type

    # ── batch operations ──

    @pytest.mark.asyncio
    async def test_handle_action__batch_confirm_all__returns_success_toast(
        self, handler, mock_requirement_agent
    ):
        data = make_card_action(
            action_type="batch_confirm_all",
            req_id="",
            extra={"req_ids": ["req_1", "req_2", "req_3"]},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "success"
        assert "3" in result["toast"]["content"]
        assert "card" in result
        mock_requirement_agent.batch_confirm_requirements.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_action__batch_reject_all__returns_success_toast(
        self, handler, mock_requirement_agent
    ):
        data = make_card_action(
            action_type="batch_reject_all",
            req_id="",
            extra={"req_ids": ["req_1", "req_2"], "reason": "out of scope"},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "success"
        assert "2" in result["toast"]["content"]
        assert "card" in result
        mock_requirement_agent.batch_reject_requirements.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_action__batch_confirm_empty_ids__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        data = make_card_action(
            action_type="batch_confirm_all",
            req_id="",
            extra={"req_ids": []},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "没有需要确认的需求" in result["toast"]["content"]
        mock_requirement_agent.batch_confirm_requirements.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_action__batch_reject_empty_ids__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        data = make_card_action(
            action_type="batch_reject_all",
            req_id="",
            extra={"req_ids": []},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "没有需要拒绝的需求" in result["toast"]["content"]
        mock_requirement_agent.batch_reject_requirements.assert_not_awaited()

    # ── pagination ──

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "action_type, page",
        [
            pytest.param("list_prev_page", 1, id="prev_page"),
            pytest.param("list_next_page", 3, id="next_page"),
        ],
    )
    async def test_handle_action__pagination__returns_card_only(
        self, handler, mock_requirement_agent, action_type, page
    ):
        data = make_card_action(
            action_type=action_type,
            req_id="",
            extra={"page": page, "chat_id": "oc_chat"},
        )
        result = await handler.handle_action(data)

        assert "card" in result
        assert "toast" not in result
        mock_requirement_agent.list_pending_requirements.assert_awaited_once_with(
            page=page, page_size=5
        )

    # ── unknown action ──

    @pytest.mark.asyncio
    async def test_handle_action__unknown_action__returns_info_toast(self, handler):
        data = make_card_action(action_type="do_something_weird", req_id="req_123")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "info"
        assert "未知操作" in result["toast"]["content"]

    # ── exception handling ──

    @pytest.mark.asyncio
    async def test_handle_action__handler_raises__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        mock_requirement_agent.confirm_requirement.side_effect = RuntimeError("db down")

        data = make_card_action(action_type="confirm_requirement", req_id="req_123")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert result["toast"]["content"] == "操作失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_handle_action__approve_decomposition_error_is_sanitized(
        self, mock_feishu_client, mock_requirement_agent
    ):
        pm_client = MagicMock()
        pm_client.approve_decomposition = AsyncMock(
            side_effect=RuntimeError("Traceback: database password leaked")
        )
        handler = CardHandler(mock_feishu_client, mock_requirement_agent, pm_client=pm_client)

        data = make_card_action(
            action_type="approve_decomposition",
            req_id="",
            extra={"wp_id": 123},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert result["toast"]["content"] == "审批请求失败，请稍后重试"
        assert "Traceback" not in result["toast"]["content"]
        assert "database password" not in result["toast"]["content"]

    @pytest.mark.asyncio
    async def test_handle_action__reject_decomposition_error_is_sanitized(
        self, mock_feishu_client, mock_requirement_agent
    ):
        pm_client = MagicMock()
        pm_client.reject_decomposition = AsyncMock(
            side_effect=RuntimeError("Traceback: database password leaked")
        )
        handler = CardHandler(mock_feishu_client, mock_requirement_agent, pm_client=pm_client)

        data = make_card_action(
            action_type="reject_decomposition",
            req_id="",
            extra={"wp_id": 123},
        )
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert result["toast"]["content"] == "拒绝请求失败，请稍后重试"
        assert "Traceback" not in result["toast"]["content"]
        assert "database password" not in result["toast"]["content"]

    # ── missing req_id ──

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "action_type",
        [
            pytest.param("confirm_requirement", id="confirm_missing_id"),
            pytest.param("reject_requirement", id="reject_missing_id"),
            pytest.param("view_detail", id="view_detail_missing_id"),
            pytest.param("list_confirm_requirement", id="list_confirm_missing_id"),
            pytest.param("list_reject_requirement", id="list_reject_missing_id"),
        ],
    )
    async def test_handle_action__missing_req_id__returns_error_toast(self, handler, action_type):
        data = {
            "action": {"tag": "button", "value": {"action": action_type}},
            "operator": {"open_id": "ou_operator_001"},
        }
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "缺少需求 ID" in result["toast"]["content"]

    # ── agent returns None ──

    @pytest.mark.asyncio
    async def test_handle_action__confirm_agent_returns_none__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        mock_requirement_agent.confirm_requirement.return_value = None

        data = make_card_action(action_type="confirm_requirement", req_id="req_123")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "需求不存在" in result["toast"]["content"]

    @pytest.mark.asyncio
    async def test_handle_action__reject_agent_returns_none__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        mock_requirement_agent.reject_requirement.return_value = None

        data = make_card_action(action_type="reject_requirement", req_id="req_123")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "需求不存在" in result["toast"]["content"]

    @pytest.mark.asyncio
    async def test_handle_action__view_detail_agent_returns_none__returns_error_toast(
        self, handler, mock_requirement_agent
    ):
        mock_requirement_agent.get_requirement.return_value = None

        data = make_card_action(action_type="view_detail", req_id="req_123")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "error"
        assert "需求不存在" in result["toast"]["content"]

    # ── reject with form_value reason ──

    @pytest.mark.asyncio
    async def test_handle_action__reject_with_form_value_reason__uses_form_reason(
        self, handler, mock_requirement_agent
    ):
        """When form_value.reason is provided, it takes priority over action_value.reason."""
        data = make_card_action(
            action_type="reject_requirement",
            req_id="req_123",
            extra={"reason": "fallback reason"},
        )
        # Add form_value with reason
        data["action"]["form_value"] = {"reason": "form provided reason"}

        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "success"
        call_kwargs = mock_requirement_agent.reject_requirement.call_args[1]
        assert call_kwargs["reason"] == "form provided reason"

    # ── view_detail with meeting data ──

    @pytest.mark.asyncio
    async def test_handle_action__view_detail_with_meeting__includes_meeting_data(
        self, handler, mock_requirement_agent
    ):
        """When requirement has source_meeting_ids, meeting data should be fetched."""
        req_mock = MagicMock()
        req_mock.id = "req_with_meeting"
        req_mock.title = "Meeting Req"
        req_mock.description = "Desc"
        req_mock.priority = "HIGH"
        req_mock.category = "Feature"
        req_mock.status = "pending"
        req_mock.source_quote = "quote"
        req_mock.source_meeting_ids = ["mtg_001"]
        mock_requirement_agent.get_requirement.return_value = req_mock

        meeting_mock = MagicMock()
        meeting_mock.id = "mtg_001"
        meeting_mock.title = "Design Review"
        meeting_mock.meeting_date = None
        meeting_mock.participants = ["Alice", "Bob"]
        mock_requirement_agent.get_meeting.return_value = meeting_mock

        data = make_card_action(action_type="view_detail", req_id="req_with_meeting")
        result = await handler.handle_action(data)

        assert result["toast"]["type"] == "success"
        assert "card" in result
        mock_requirement_agent.get_meeting.assert_awaited_once_with("mtg_001")

    # ── _get_user_name cache ──

    @pytest.mark.asyncio
    async def test_get_user_name__cache_miss__calls_api(self, handler, mock_feishu_client):
        name = await handler._get_user_name("ou_new_user")

        assert name == "TestUser"
        mock_feishu_client.get_user_info.assert_awaited_once_with("ou_new_user")

    @pytest.mark.asyncio
    async def test_get_user_name__cache_hit__skips_api(self, handler, mock_feishu_client):
        # First call populates cache
        await handler._get_user_name("ou_cached")
        mock_feishu_client.get_user_info.reset_mock()

        # Second call should use cache
        name = await handler._get_user_name("ou_cached")

        assert name == "TestUser"
        mock_feishu_client.get_user_info.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_user_name__api_raises__returns_unknown(self, handler, mock_feishu_client):
        mock_feishu_client.get_user_info.side_effect = RuntimeError("network error")

        name = await handler._get_user_name("ou_error_user")

        assert name == "Unknown"


# ──────────────────────────────────────────────
# BotHandler
# ──────────────────────────────────────────────


class TestBotHandler:
    """Tests for BotHandler.handle_message."""

    @pytest.fixture
    def handler(self, mock_feishu_client, mock_requirement_agent):
        return BotHandler(mock_feishu_client, mock_requirement_agent)

    # ── commands: parametrized /help, /list, /export ──

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command",
        [
            pytest.param("/help", id="help"),
            pytest.param("/list", id="list"),
        ],
    )
    async def test_handle_message__known_command__sends_card(
        self, handler, mock_feishu_client, command
    ):
        data = make_feishu_event(content=f'{{"text": "{command}"}}')
        await handler.handle_message(data)

        mock_feishu_client.send_card.assert_awaited_once()

    # ── /unknown command ──

    @pytest.mark.asyncio
    async def test_handle_message__unknown_command__replies_error(
        self, handler, mock_feishu_client
    ):
        data = make_feishu_event(content='{"text": "/foobar"}')
        await handler.handle_message(data)

        mock_feishu_client.reply_message.assert_awaited_once()
        reply_text = mock_feishu_client.reply_message.call_args[0][1]
        assert "未知命令" in reply_text
        assert "/foobar" in reply_text

    # ── text extraction + requirement extraction ──

    @pytest.mark.asyncio
    async def test_handle_message__text_with_requirements__sends_card(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        data = make_feishu_event(content='{"text": "我们需要一个离线录音功能"}')
        await handler.handle_message(data)

        mock_requirement_agent.ingest_meeting.assert_awaited_once()
        call_kwargs = mock_requirement_agent.ingest_meeting.call_args[1]
        assert call_kwargs["content"] == "我们需要一个离线录音功能"
        assert call_kwargs["source"] == "feishu_bot"
        mock_feishu_client.send_card.assert_awaited_once()

    # ── extraction returns 0 requirements ──

    @pytest.mark.asyncio
    async def test_handle_message__zero_requirements__replies_no_req(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        mock_requirement_agent.ingest_meeting.return_value = MockIngestResult(
            requirements_extracted=0,
            questions_generated=0,
            requirement_ids=[],
            requirements=[],
        )

        data = make_feishu_event(content='{"text": "今天天气不错"}')
        await handler.handle_message(data)

        mock_feishu_client.reply_message.assert_awaited_once()
        reply_text = mock_feishu_client.reply_message.call_args[0][1]
        assert "未从内容中识别出需求" in reply_text

    # ── non-text message ──

    @pytest.mark.asyncio
    async def test_handle_message__non_text_message__skips(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        data = make_feishu_event(msg_type="image", content="")
        await handler.handle_message(data)

        mock_requirement_agent.ingest_meeting.assert_not_awaited()
        mock_feishu_client.send_card.assert_not_awaited()
        mock_feishu_client.reply_message.assert_not_awaited()

    # ── empty content ──

    @pytest.mark.asyncio
    async def test_handle_message__empty_content__skips(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        data = make_feishu_event(content='{"text": ""}')
        await handler.handle_message(data)

        mock_requirement_agent.ingest_meeting.assert_not_awaited()

    # ── extraction exception ──

    @pytest.mark.asyncio
    async def test_handle_message__extract_raises__replies_error(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        mock_requirement_agent.ingest_meeting.side_effect = RuntimeError("LLM down")

        data = make_feishu_event(content='{"text": "some requirement text here"}')
        await handler.handle_message(data)

        mock_feishu_client.reply_message.assert_awaited_once()
        reply_text = mock_feishu_client.reply_message.call_args[0][1]
        assert "处理失败" in reply_text
        assert "LLM down" in reply_text

    # ── /export success ──

    @pytest.mark.asyncio
    async def test_handle_message__export_command__sends_prd_card(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        mock_generator = MagicMock()
        mock_generator.generate_prd = AsyncMock(return_value=MockPRDResult())

        data = make_feishu_event(content='{"text": "/export"}')

        with patch(
            "agents.requirement_manager.core.generator.generator",
            mock_generator,
            create=True,
        ):
            await handler.handle_message(data)

        mock_requirement_agent.get_confirmed_requirements.assert_awaited_once()
        mock_feishu_client.send_card.assert_awaited_once()

    # ── /export no confirmed requirements ──

    @pytest.mark.asyncio
    async def test_handle_message__export_no_confirmed__replies_empty(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        mock_requirement_agent.get_confirmed_requirements.return_value = []

        data = make_feishu_event(content='{"text": "/export"}')
        await handler.handle_message(data)

        mock_requirement_agent.get_confirmed_requirements.assert_awaited_once()
        mock_feishu_client.reply_message.assert_awaited_once()
        reply_text = mock_feishu_client.reply_message.call_args[0][1]
        assert "暂无已确认需求" in reply_text


# ──────────────────────────────────────────────
# EventHandler
# ──────────────────────────────────────────────


class TestEventHandler:
    """Tests for EventHandler.dispatch."""

    @pytest.fixture
    def handler(self, mock_feishu_client, mock_requirement_agent):
        return EventHandler(mock_feishu_client, mock_requirement_agent)

    # ── meeting ended: extraction + card send ──

    @pytest.mark.asyncio
    async def test_dispatch__meeting_ended_with_summary__extracts_and_sends_card(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        data = {
            "event": {
                "meeting": {
                    "meeting_id": "mtg_001",
                    "topic": "产品需求讨论",
                    "chat_id": "oc_chat_001",
                    "summary": "讨论了离线录音功能需求",
                }
            }
        }
        result = await handler.dispatch("vc.meeting.meeting_ended_v1", data)

        assert result == {"code": 0}
        mock_requirement_agent.ingest_meeting.assert_awaited_once_with(
            content="讨论了离线录音功能需求",
            source="feishu_meeting",
            title="产品需求讨论",
            source_id="mtg_001",
        )
        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args[1]
        assert call_kwargs["receive_id"] == "oc_chat_001"
        assert call_kwargs["receive_id_type"] == "chat_id"

    # ── meeting ended: empty summary ──

    @pytest.mark.asyncio
    async def test_dispatch__meeting_ended_empty_summary__skips(
        self, handler, mock_feishu_client, mock_requirement_agent
    ):
        data = {
            "event": {
                "meeting": {
                    "meeting_id": "mtg_002",
                    "topic": "Standup",
                    "chat_id": "oc_chat_002",
                    "summary": "",
                }
            }
        }
        result = await handler.dispatch("vc.meeting.meeting_ended_v1", data)

        assert result == {"code": 0}
        mock_requirement_agent.ingest_meeting.assert_not_awaited()
        mock_feishu_client.send_card.assert_not_awaited()

    # ── calendar changed: created with keyword ──

    @pytest.mark.asyncio
    async def test_dispatch__calendar_created_with_keyword__sends_card_to_organizer(
        self, handler, mock_feishu_client
    ):
        data = {
            "event": {
                "type": "created",
                "event": {
                    "event_id": "evt_cal_001",
                    "summary": "产品需求评审会议",
                    "organizer": {
                        "user_id": "ou_organizer",
                        "display_name": "张三",
                    },
                    "start_time": {"timestamp": "1706169600"},
                    "attendees": [
                        {"display_name": "李四"},
                        {"display_name": "王五"},
                    ],
                },
            }
        }
        result = await handler.dispatch("calendar.calendar.event_changed_v4", data)

        assert result == {"code": 0}
        mock_feishu_client.send_card.assert_awaited_once()
        call_kwargs = mock_feishu_client.send_card.call_args[1]
        assert call_kwargs["receive_id"] == "ou_organizer"
        assert call_kwargs["receive_id_type"] == "user_id"

    # ── calendar changed: updated with keyword ──

    @pytest.mark.asyncio
    async def test_dispatch__calendar_updated_with_keyword__sends_card(
        self, handler, mock_feishu_client
    ):
        data = {
            "event": {
                "type": "updated",
                "event": {
                    "event_id": "evt_cal_002",
                    "summary": "PRD评审更新",
                    "organizer": {
                        "user_id": "ou_organizer_2",
                        "display_name": "李四",
                    },
                    "start_time": {"date": "2024-01-25"},
                    "attendees": [],
                },
            }
        }
        result = await handler.dispatch("calendar.calendar.event_changed_v4", data)

        assert result == {"code": 0}
        mock_feishu_client.send_card.assert_awaited_once()

    # ── calendar changed: no keyword ──

    @pytest.mark.asyncio
    async def test_dispatch__calendar_no_keyword__skips(self, handler, mock_feishu_client):
        data = {
            "event": {
                "type": "created",
                "event": {
                    "event_id": "evt_cal_003",
                    "summary": "团建活动安排",
                    "organizer": {
                        "user_id": "ou_organizer",
                        "display_name": "张三",
                    },
                    "start_time": {"timestamp": "1706169600"},
                    "attendees": [],
                },
            }
        }
        result = await handler.dispatch("calendar.calendar.event_changed_v4", data)

        assert result == {"code": 0}
        mock_feishu_client.send_card.assert_not_awaited()

    # ── calendar changed: deleted ──

    @pytest.mark.asyncio
    async def test_dispatch__calendar_deleted__skips(self, handler, mock_feishu_client):
        data = {
            "event": {
                "type": "deleted",
                "event": {
                    "event_id": "evt_cal_004",
                    "summary": "需求讨论",
                },
            }
        }
        result = await handler.dispatch("calendar.calendar.event_changed_v4", data)

        assert result == {"code": 0}
        mock_feishu_client.send_card.assert_not_awaited()

    # ── calendar changed: no organizer ──

    @pytest.mark.asyncio
    async def test_dispatch__calendar_no_organizer__skips_card_send(
        self, handler, mock_feishu_client
    ):
        data = {
            "event": {
                "type": "created",
                "event": {
                    "event_id": "evt_cal_005",
                    "summary": "需求讨论会",
                    "organizer": {},
                    "start_time": {"timestamp": "1706169600"},
                    "attendees": [],
                },
            }
        }
        result = await handler.dispatch("calendar.calendar.event_changed_v4", data)

        assert result == {"code": 0}
        mock_feishu_client.send_card.assert_not_awaited()

    # ── unknown event ──

    @pytest.mark.asyncio
    async def test_dispatch__unknown_event__returns_code_zero(self, handler):
        result = await handler.dispatch("some.unknown.event_v1", {})

        assert result == {"code": 0}

    # ── handler exception ──

    @pytest.mark.asyncio
    async def test_dispatch__handler_raises__returns_code_zero(
        self, handler, mock_requirement_agent
    ):
        mock_requirement_agent.ingest_meeting.side_effect = RuntimeError("extraction failed")

        data = {
            "event": {
                "meeting": {
                    "meeting_id": "mtg_err",
                    "topic": "Crash meeting",
                    "chat_id": "oc_chat_err",
                    "summary": "this will fail",
                }
            }
        }
        result = await handler.dispatch("vc.meeting.meeting_ended_v1", data)

        assert result == {"code": 0}
