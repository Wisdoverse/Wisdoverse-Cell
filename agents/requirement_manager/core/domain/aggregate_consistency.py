"""Requirement aggregate consistency-boundary policy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

MEETING = "Meeting"
REQUIREMENT = "Requirement"
OPEN_QUESTION = "OpenQuestion"
FEEDBACK_RECORD = "FeedbackRecord"
REQUIREMENT_EVENT_OUTBOX = "RequirementEventOutbox"


class RequirementAggregateConsistencyError(ValueError):
    """Raised when a Requirement transaction crosses an undeclared boundary."""


@dataclass(frozen=True, slots=True)
class RequirementTransactionScope:
    """Declared aggregate write scope for one Requirement Manager use case."""

    use_case: str
    primary_aggregate: str
    same_transaction_aggregates: tuple[str, ...]
    post_commit_side_effects: tuple[str, ...]
    reason: str

    def assert_allows_same_transaction(self, aggregates: Iterable[str]) -> None:
        """Reject writes outside this use case's declared consistency boundary."""
        allowed = set(self.same_transaction_aggregates)
        requested = set(aggregates)
        unexpected = sorted(requested - allowed)
        if unexpected:
            raise RequirementAggregateConsistencyError(
                f"{self.use_case} transaction cannot write {unexpected}; "
                f"allowed aggregates are {sorted(allowed)}"
            )


class RequirementAggregateConsistencyPolicy:
    """Named immediate-consistency scopes for Requirement Manager workflows."""

    def meeting_ingest(
        self,
        *,
        requirements_count: int,
        open_questions_count: int,
    ) -> RequirementTransactionScope:
        """Return the declared write scope for one meeting-ingestion transaction."""
        aggregates = [MEETING]
        if requirements_count:
            aggregates.append(REQUIREMENT)
            aggregates.append(REQUIREMENT_EVENT_OUTBOX)
        if open_questions_count:
            aggregates.append(OPEN_QUESTION)

        return RequirementTransactionScope(
            use_case="meeting_ingest",
            primary_aggregate=MEETING,
            same_transaction_aggregates=tuple(aggregates),
            post_commit_side_effects=("vector_index", "notification"),
            reason=(
                "Extracted requirements and questions are materialized from one "
                "Meeting source and must become visible atomically with the "
                "processed Meeting marker and extraction outbox event."
            ),
        )

    def requirement_lifecycle_mutation(
        self,
        *,
        records_feedback: bool = False,
    ) -> RequirementTransactionScope:
        """Return the declared write scope for one Requirement lifecycle mutation."""
        aggregates = [REQUIREMENT, REQUIREMENT_EVENT_OUTBOX]
        if records_feedback:
            aggregates.append(FEEDBACK_RECORD)

        return RequirementTransactionScope(
            use_case="requirement_lifecycle_mutation",
            primary_aggregate=REQUIREMENT,
            same_transaction_aggregates=tuple(aggregates),
            post_commit_side_effects=("vector_index", "notification"),
            reason=(
                "Requirement lifecycle state is the consistency root; feedback "
                "records are learning evidence for the same operator decision, "
                "and integration events are staged in the same UoW."
            ),
        )

    def question_answer(self) -> RequirementTransactionScope:
        """Return the declared write scope for answering an OpenQuestion."""
        return RequirementTransactionScope(
            use_case="question_answer",
            primary_aggregate=OPEN_QUESTION,
            same_transaction_aggregates=(OPEN_QUESTION,),
            post_commit_side_effects=(),
            reason="Answering an OpenQuestion mutates only the question aggregate.",
        )


__all__ = [
    "FEEDBACK_RECORD",
    "MEETING",
    "OPEN_QUESTION",
    "REQUIREMENT",
    "REQUIREMENT_EVENT_OUTBOX",
    "RequirementAggregateConsistencyError",
    "RequirementAggregateConsistencyPolicy",
    "RequirementTransactionScope",
]
