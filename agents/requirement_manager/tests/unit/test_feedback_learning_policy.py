"""Unit tests for Requirement feedback-learning domain policy."""

from __future__ import annotations

from agents.requirement_manager.core.domain.feedback_learning import (
    FEEDBACK_CORRECTION,
    FEEDBACK_REJECTION,
    REJECTED_CORRECTION_TITLE,
    RequirementFeedbackLearningPolicy,
)
from shared.core.identifiers import RequirementId


def test_correction_policy_builds_feedback_draft() -> None:
    draft = RequirementFeedbackLearningPolicy().correction(
        requirement_id=RequirementId("req_1"),
        original={
            "title": "Offline mode",
            "description": "Allow local use",
            "priority": "low",
            "category": "bug",
        },
        corrected={
            "title": "Offline mode",
            "description": "Allow local use with later sync",
            "priority": "high",
            "category": "feature",
        },
        corrected_by="pm",
        source_text="customer interview",
        note="PM correction",
    )

    assert draft.requirement_id == RequirementId("req_1")
    assert draft.feedback_type == FEEDBACK_CORRECTION
    assert draft.corrected_by == "pm"
    assert draft.source_text == "customer interview"
    assert draft.correction_note == "PM correction"
    assert draft.original.title == "Offline mode"
    assert draft.corrected.priority == "high"
    assert draft.changed_fields() == ["description", "priority", "category"]


def test_rejection_policy_builds_rejection_draft() -> None:
    draft = RequirementFeedbackLearningPolicy().rejection(
        requirement_id=RequirementId("req_2"),
        original={"title": "Discussion note", "priority": "medium"},
        rejected_by="qa",
        reason="Not an actionable requirement",
    )

    assert draft.requirement_id == RequirementId("req_2")
    assert draft.feedback_type == FEEDBACK_REJECTION
    assert draft.corrected.title == REJECTED_CORRECTION_TITLE
    assert draft.corrected.description == "Not an actionable requirement"
    assert draft.corrected.priority is None
    assert draft.corrected.category is None
    assert draft.corrected_by == "qa"
    assert draft.correction_note == "Not an actionable requirement"


def test_changed_fields_uses_normalized_snapshots() -> None:
    changed = RequirementFeedbackLearningPolicy().changed_fields(
        {"title": None, "description": "old", "priority": 1, "category": "bug"},
        {"description": "new", "priority": "1", "category": "bug"},
    )

    assert changed == ["description"]
