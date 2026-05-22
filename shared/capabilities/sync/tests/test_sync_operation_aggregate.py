"""Unit tests for the SyncOperation aggregate seed (DDD-003)."""

from __future__ import annotations

import pytest

from shared.capabilities.sync.core.domain.sync_operation import (
    InvalidSyncOperationTransitionError,
    SyncOperation,
    SyncOperationStatus,
    SyncOperationStatusChanged,
    SyncSide,
    VALID_TRANSITIONS,
    combine_side_statuses,
)


def _make(side: SyncSide = SyncSide.OPENPROJECT) -> SyncOperation:
    return SyncOperation(operation_id="sync_test", side=side)


def test_pending_can_transition_to_running() -> None:
    op = _make()
    op.transition_to(SyncOperationStatus.RUNNING)
    assert op.status == SyncOperationStatus.RUNNING


def test_pending_cannot_jump_to_succeeded() -> None:
    op = _make()
    with pytest.raises(InvalidSyncOperationTransitionError):
        op.transition_to(SyncOperationStatus.SUCCEEDED)


def test_running_can_reach_each_terminal_state() -> None:
    for terminal in (
        SyncOperationStatus.SUCCEEDED,
        SyncOperationStatus.PARTIAL_FAILURE,
        SyncOperationStatus.FAILED,
    ):
        op = _make()
        op.transition_to(SyncOperationStatus.RUNNING)
        op.transition_to(terminal)
        assert op.status == terminal
        assert op.is_terminal


def test_processed_count_accumulates_on_transition() -> None:
    op = _make()
    op.transition_to(SyncOperationStatus.RUNNING, processed_delta=5)
    op.transition_to(SyncOperationStatus.SUCCEEDED, processed_delta=10)
    assert op.processed_count == 15


def test_transition_raises_typed_domain_event() -> None:
    op = _make(side=SyncSide.FEISHU_BITABLE)
    op.transition_to(SyncOperationStatus.RUNNING, processed_delta=3)
    events = op.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], SyncOperationStatusChanged)
    assert events[0].side == SyncSide.FEISHU_BITABLE
    assert events[0].from_status == SyncOperationStatus.PENDING
    assert events[0].to_status == SyncOperationStatus.RUNNING
    assert events[0].processed_count == 3


def test_pull_events_clears_the_buffer() -> None:
    op = _make()
    op.transition_to(SyncOperationStatus.RUNNING)
    op.pull_events()
    assert op.pull_events() == []


def test_valid_transitions_table_covers_every_status() -> None:
    for status in SyncOperationStatus:
        assert status in VALID_TRANSITIONS, f"missing FSM row for {status}"


def test_combine_side_statuses_typed_replacement_for_engine_strings() -> None:
    """`combine_side_statuses` typed-enum equivalent of engine.py:74-87."""
    # Both failed → FAILED
    assert (
        combine_side_statuses(SyncOperationStatus.FAILED, SyncOperationStatus.FAILED)
        == SyncOperationStatus.FAILED
    )
    # One failed → PARTIAL_FAILURE
    assert (
        combine_side_statuses(SyncOperationStatus.FAILED, SyncOperationStatus.SUCCEEDED)
        == SyncOperationStatus.PARTIAL_FAILURE
    )
    assert (
        combine_side_statuses(SyncOperationStatus.SUCCEEDED, SyncOperationStatus.FAILED)
        == SyncOperationStatus.PARTIAL_FAILURE
    )
    # Both succeeded → SUCCEEDED
    assert (
        combine_side_statuses(SyncOperationStatus.SUCCEEDED, SyncOperationStatus.SUCCEEDED)
        == SyncOperationStatus.SUCCEEDED
    )
    # Mixed non-failure → PARTIAL_FAILURE (running, skipped, etc.)
    assert (
        combine_side_statuses(SyncOperationStatus.RUNNING, SyncOperationStatus.SKIPPED)
        == SyncOperationStatus.PARTIAL_FAILURE
    )
