"""Unit tests for the chat-agent CardOperationLogEntry aggregate."""

from __future__ import annotations

import json

import pytest

from agents.chat_agent.core.domain.card_operation import (
    CardOperationLogEntry,
    CardOperationLogged,
    CardOperationResult,
    InvalidCardOperationError,
    coerce_card_operation_result,
)


def test_recorded_entry_extracts_assignee_and_snapshot() -> None:
    entry = CardOperationLogEntry.recorded(
        user_id="ou_1",
        user_name="Alice",
        action="confirm_create",
        result="success",
        table_id="tbl_1",
        record_id="rec_1",
        fields={
            "DRI (负责人)": [{"name": "Bob"}],
            "任务(动宾短语)": "Build report",
        },
    )

    assert entry.result == CardOperationResult.SUCCESS
    assert entry.assignee_name == "Bob"
    assert json.loads(entry.fields_snapshot)["任务(动宾短语)"] == "Build report"
    events = entry.pull_events()
    assert events == [
        CardOperationLogged(
            user_id="ou_1",
            action="confirm_create",
            result=CardOperationResult.SUCCESS,
            table_id="tbl_1",
            record_id="rec_1",
        )
    ]
    assert entry.pull_events() == []


def test_recorded_entry_accepts_text_assignee() -> None:
    entry = CardOperationLogEntry.recorded(
        user_id="ou_1",
        user_name="Alice",
        action="confirm_update",
        result=CardOperationResult.REJECTED,
        fields={"DRI (负责人)": [{"text": "Carol"}]},
    )

    assert entry.assignee_name == "Carol"
    assert entry.result == CardOperationResult.REJECTED


def test_requires_action() -> None:
    with pytest.raises(InvalidCardOperationError):
        CardOperationLogEntry.recorded(
            user_id="ou_1",
            user_name="Alice",
            action="",
            result="success",
        )


def test_rejects_unknown_result() -> None:
    with pytest.raises(ValueError):
        CardOperationLogEntry.recorded(
            user_id="ou_1",
            user_name="Alice",
            action="confirm_create",
            result="unknown",
        )


def test_failed_result_requires_error_message() -> None:
    with pytest.raises(InvalidCardOperationError):
        CardOperationLogEntry.recorded(
            user_id="ou_1",
            user_name="Alice",
            action="confirm_create",
            result="failed",
        )


def test_failed_result_accepts_error_message() -> None:
    entry = CardOperationLogEntry.recorded(
        user_id="ou_1",
        user_name="Alice",
        action="confirm_create",
        result="failed",
        error_message="API timeout",
    )

    assert entry.result == CardOperationResult.FAILED
    assert entry.error_message == "API timeout"


def test_coerce_card_operation_result_accepts_enum_and_string() -> None:
    assert (
        coerce_card_operation_result(CardOperationResult.PENDING)
        == CardOperationResult.PENDING
    )
    assert coerce_card_operation_result("success") == CardOperationResult.SUCCESS
