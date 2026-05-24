"""Unit tests for Requirement aggregate consistency-boundary policy."""

from __future__ import annotations

import pytest

from agents.requirement_manager.core.domain.aggregate_consistency import (
    FEEDBACK_RECORD,
    MEETING,
    OPEN_QUESTION,
    REQUIREMENT,
    REQUIREMENT_EVENT_OUTBOX,
    RequirementAggregateConsistencyError,
    RequirementAggregateConsistencyPolicy,
)


def test_meeting_ingest_scope_declares_materialization_transaction() -> None:
    scope = RequirementAggregateConsistencyPolicy().meeting_ingest(
        requirements_count=2,
        open_questions_count=1,
    )

    assert scope.primary_aggregate == MEETING
    assert scope.same_transaction_aggregates == (
        MEETING,
        REQUIREMENT,
        REQUIREMENT_EVENT_OUTBOX,
        OPEN_QUESTION,
    )
    assert scope.post_commit_side_effects == ("vector_index", "notification")
    scope.assert_allows_same_transaction(
        (MEETING, REQUIREMENT, OPEN_QUESTION, REQUIREMENT_EVENT_OUTBOX)
    )


def test_lifecycle_scope_declares_feedback_evidence_when_needed() -> None:
    scope = RequirementAggregateConsistencyPolicy().requirement_lifecycle_mutation(
        records_feedback=True,
    )

    assert scope.primary_aggregate == REQUIREMENT
    assert scope.same_transaction_aggregates == (
        REQUIREMENT,
        REQUIREMENT_EVENT_OUTBOX,
        FEEDBACK_RECORD,
    )
    scope.assert_allows_same_transaction(
        (REQUIREMENT, FEEDBACK_RECORD, REQUIREMENT_EVENT_OUTBOX)
    )


def test_scope_rejects_undeclared_aggregate_writes() -> None:
    scope = RequirementAggregateConsistencyPolicy().question_answer()

    with pytest.raises(RequirementAggregateConsistencyError):
        scope.assert_allows_same_transaction((OPEN_QUESTION, REQUIREMENT))
