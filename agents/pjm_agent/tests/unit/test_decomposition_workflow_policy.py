"""Tests for PJM decomposition workflow domain policies."""

from __future__ import annotations

from agents.pjm_agent.core.domain.decomposition_policy import DecompositionWorkflowPolicy
from agents.pjm_agent.core.domain.lifecycle.decomposition_lifecycle import (
    APPROVED,
    FAILED,
    PENDING,
    REJECTED,
    WRITE_FAILED,
    WRITING,
)


def test_intake_policy_starts_without_existing_record() -> None:
    decision = DecompositionWorkflowPolicy().intake_decision(None)

    assert decision.action == "start"
    assert decision.existing_status is None
    assert decision.should_skip is False
    assert decision.should_replace_existing is False


def test_intake_policy_skips_active_or_write_in_progress_records() -> None:
    policy = DecompositionWorkflowPolicy()

    for status in (PENDING, WRITING, APPROVED, WRITE_FAILED):
        decision = policy.intake_decision(status)

        assert decision.action == "skip"
        assert decision.existing_status == status
        assert decision.should_skip is True


def test_intake_policy_replaces_failed_rejected_or_unknown_records() -> None:
    policy = DecompositionWorkflowPolicy()

    for status in (FAILED, REJECTED, "unknown"):
        decision = policy.intake_decision(status)

        assert decision.action == "replace"
        assert decision.existing_status == status
        assert decision.should_replace_existing is True


def test_retry_policy_allows_only_recoverable_terminal_statuses() -> None:
    policy = DecompositionWorkflowPolicy()

    for status in (FAILED, REJECTED, WRITE_FAILED):
        decision = policy.retry_decision(status)

        assert decision.allowed is True
        assert decision.status == status
        assert decision.error_code is None


def test_retry_policy_rejects_missing_record() -> None:
    decision = DecompositionWorkflowPolicy().retry_decision(None)

    assert decision.allowed is False
    assert decision.error_message == "record not found"
    assert decision.error_code == "pm.decomposition_not_found"
    assert decision.status is None


def test_retry_policy_rejects_nonrecoverable_status() -> None:
    decision = DecompositionWorkflowPolicy().retry_decision(PENDING)

    assert decision.allowed is False
    assert decision.error_code == "pm.decomposition_retry_not_allowed"
    assert decision.status == PENDING
    assert (
        decision.error_message == "cannot retry status 'pending', only failed/rejected/write_failed"
    )
