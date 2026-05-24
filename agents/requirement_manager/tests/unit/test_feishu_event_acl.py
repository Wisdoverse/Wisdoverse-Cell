"""Unit tests for Requirement Manager inbound Feishu ACL value objects."""

from __future__ import annotations

import pytest

from agents.requirement_manager.integrations.feishu.acl import (
    DEFAULT_BATCH_REJECTION_REASON,
    DEFAULT_REQUIREMENT_REJECTION_REASON,
    UNKNOWN_TIME_LABEL,
    FeishuBotMessage,
    FeishuCardAction,
    FeishuCardActionResponse,
    FeishuMeetingEndedEvent,
    FeishuRequirementCalendarEvent,
)


def test_meeting_ended_acl_translates_feishu_payload_to_ingest_fields() -> None:
    event = FeishuMeetingEndedEvent.from_payload(
        {
            "event": {
                "meeting": {
                    "meeting_id": "mtg_001",
                    "topic": "Product review",
                    "chat_id": "oc_chat_001",
                    "summary": "Discussed offline recording",
                }
            }
        }
    )

    assert event.has_summary is True
    assert event.has_chat is True
    assert event.ingest_kwargs() == {
        "content": "Discussed offline recording",
        "source": "feishu_meeting",
        "title": "Product review",
        "source_id": "mtg_001",
    }


def test_bot_message_acl_translates_json_text_and_command() -> None:
    message = FeishuBotMessage.from_payload(
        {
            "message": {
                "message_id": "om_001",
                "chat_id": "oc_001",
                "message_type": "text",
                "content": '{"text": "/list pending"}',
            }
        }
    )

    assert message.is_text is True
    assert message.has_text is True
    assert message.is_command is True
    assert message.text == "/list pending"
    assert message.command is not None
    assert message.command.name == "list"
    assert message.command.args == "pending"


def test_bot_message_acl_parses_commands_without_regex_backtracking() -> None:
    message = FeishuBotMessage.from_payload(
        {
            "message": {
                "message_type": "text",
                "content": '{"text": "/0                                                     "}',
            }
        }
    )
    invalid = FeishuBotMessage.from_payload(
        {"message": {"message_type": "text", "content": '{"text": "/ list"}'}}
    )

    assert message.command is not None
    assert message.command.name == "0"
    assert message.command.args is None
    assert invalid.command is None


def test_bot_message_acl_translates_raw_text_to_ingest_fields() -> None:
    message = FeishuBotMessage.from_payload(
        {
            "message": {
                "message_id": "om_002",
                "chat_id": "oc_002",
                "message_type": "text",
                "content": "We need offline capture",
            }
        }
    )

    assert message.is_command is False
    assert message.ingest_kwargs() == {
        "content": "We need offline capture",
        "source": "feishu_bot",
    }


def test_bot_message_acl_handles_non_text_and_missing_payload() -> None:
    non_text = FeishuBotMessage.from_payload(
        {"message": {"message_type": "image", "content": '{"text": "ignored"}'}}
    )
    missing = FeishuBotMessage.from_payload({"message": None})

    assert non_text.is_text is False
    assert non_text.has_text is True
    assert missing.message_id == ""
    assert missing.text == ""
    assert missing.has_text is False


def test_card_action_acl_translates_callback_payload() -> None:
    action = FeishuCardAction.from_payload(
        {
            "action": {
                "value": {
                    "action": "list_reject_requirement",
                    "req_id": "req_1",
                    "page": "2",
                    "chat_id": "oc_chat_1",
                    "req_ids": ["req_1", "req_2"],
                    "reason": "fallback reason",
                    "wp_id": 123,
                },
                "form_value": {"reason": "form reason", "reject_reason": "PJM reason"},
            },
            "operator": {"open_id": "ou_operator"},
        }
    )

    assert action.action_type == "list_reject_requirement"
    assert action.operator_id == "ou_operator"
    assert action.requirement_id == "req_1"
    assert action.page == 2
    assert action.chat_id == "oc_chat_1"
    assert action.requirement_ids == ("req_1", "req_2")
    assert action.requirement_ids_list() == ["req_1", "req_2"]
    assert action.reason == "form reason"
    assert action.requirement_rejection_reason == "form reason"
    assert action.decomposition_rejection_reason == "PJM reason"
    assert action.work_package_id == 123


def test_card_action_acl_supplies_legacy_defaults() -> None:
    action = FeishuCardAction.from_payload(
        {
            "action": {
                "value": {
                    "action": "batch_reject_all",
                    "req_ids": [],
                    "page": "not-a-number",
                },
            },
            "operator": {},
        }
    )

    assert action.page == 1
    assert action.has_requirement_id is False
    assert action.has_requirement_ids is False
    assert action.has_work_package_id is False
    assert action.requirement_rejection_reason == DEFAULT_REQUIREMENT_REJECTION_REASON
    assert action.batch_rejection_reason == DEFAULT_BATCH_REJECTION_REASON


def test_card_action_response_builds_callback_payloads() -> None:
    card = {"elements": []}

    assert FeishuCardActionResponse.info("Unknown").to_payload() == {
        "toast": {"type": "info", "content": "Unknown"}
    }
    assert FeishuCardActionResponse.error("Failed").to_payload() == {
        "toast": {"type": "error", "content": "Failed"}
    }
    assert FeishuCardActionResponse.success("Done", card=card).to_payload() == {
        "toast": {"type": "success", "content": "Done"},
        "card": card,
    }
    assert FeishuCardActionResponse.card_only(card).to_payload() == {"card": card}


def test_meeting_ended_acl_handles_missing_nested_payloads() -> None:
    event = FeishuMeetingEndedEvent.from_payload({"event": None})

    assert event.meeting_id == ""
    assert event.summary == ""
    assert event.has_summary is False
    assert event.has_chat is False


def test_calendar_acl_detects_requirement_reminder_fields() -> None:
    event = FeishuRequirementCalendarEvent.from_payload(
        {
            "event": {
                "type": "created",
                "event": {
                    "event_id": "evt_001",
                    "summary": "PRD review and PRD planning",
                    "organizer": {
                        "user_id": "ou_1",
                        "display_name": "Alice",
                    },
                    "start_time": {"date": "2026-05-23"},
                    "attendees": [{"display_name": f"Person {index}"} for index in range(12)],
                },
            }
        }
    )

    assert event.should_notify is True
    assert event.has_organizer is True
    assert event.start_time_label == "2026-05-23"
    assert len(event.attendees) == 10
    assert event.matched_keywords == ("PRD", "review")
    assert event.reminder_card_kwargs() == {
        "event_title": "PRD review and PRD planning",
        "start_time": "2026-05-23",
        "organizer": "Alice",
        "attendees": [f"Person {index}" for index in range(10)],
        "keywords_found": ["PRD", "review"],
    }


def test_calendar_acl_skips_deleted_or_non_requirement_events() -> None:
    deleted = FeishuRequirementCalendarEvent.from_payload(
        {"event": {"type": "deleted", "event": {"summary": "PRD review"}}}
    )
    unrelated = FeishuRequirementCalendarEvent.from_payload(
        {"event": {"type": "updated", "event": {"summary": "Team lunch"}}}
    )

    assert deleted.is_created_or_updated is False
    assert deleted.has_requirement_keywords is True
    assert deleted.should_notify is False
    assert unrelated.is_created_or_updated is True
    assert unrelated.has_requirement_keywords is False
    assert unrelated.should_notify is False


def test_calendar_acl_uses_unknown_time_for_invalid_timestamp() -> None:
    event = FeishuRequirementCalendarEvent.from_payload(
        {
            "event": {
                "type": "updated",
                "event": {
                    "summary": "需求评审",
                    "start_time": {"timestamp": "not-a-timestamp"},
                },
            }
        }
    )

    assert event.start_time_label == UNKNOWN_TIME_LABEL


def test_feishu_event_acl_values_are_immutable() -> None:
    event = FeishuCardAction.from_payload({"action": {"value": {"req_id": "req_1"}}})

    with pytest.raises(AttributeError):
        event.requirement_id = "changed"  # type: ignore[misc]
