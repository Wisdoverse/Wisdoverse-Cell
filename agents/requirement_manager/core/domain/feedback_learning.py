"""Domain service for Requirement feedback-learning records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shared.core.identifiers import RequirementId

FEEDBACK_CORRECTION = "correction"
FEEDBACK_REJECTION = "rejection"
REJECTED_CORRECTION_TITLE = "[REJECTED]"
TRACKED_FEEDBACK_FIELDS = ("title", "description", "priority", "category")


@dataclass(frozen=True, slots=True)
class RequirementExtractionSnapshot:
    """Immutable extracted requirement fields used for learning examples."""

    title: str
    description: str | None = None
    priority: str | None = None
    category: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "RequirementExtractionSnapshot":
        """Build a normalized snapshot from extraction/correction values."""
        return cls(
            title=_string_or_none(values.get("title")) or "",
            description=_string_or_none(values.get("description")),
            priority=_string_or_none(values.get("priority")),
            category=_string_or_none(values.get("category")),
        )

    def changed_fields(self, corrected: "RequirementExtractionSnapshot") -> list[str]:
        """Return tracked fields whose extracted value changed."""
        return [
            field
            for field in TRACKED_FEEDBACK_FIELDS
            if getattr(self, field) != getattr(corrected, field)
        ]


@dataclass(frozen=True, slots=True)
class RequirementFeedbackDraft:
    """Persistence-agnostic feedback record produced by the domain policy."""

    requirement_id: RequirementId
    original: RequirementExtractionSnapshot
    corrected: RequirementExtractionSnapshot
    feedback_type: str
    corrected_by: str
    source_text: str | None = None
    correction_note: str | None = None

    def changed_fields(self) -> list[str]:
        """Return tracked fields changed between original and corrected values."""
        return self.original.changed_fields(self.corrected)


class RequirementFeedbackLearningPolicy:
    """Domain service for classifying user feedback into learning records."""

    def correction(
        self,
        *,
        requirement_id: RequirementId,
        original: Mapping[str, Any],
        corrected: Mapping[str, Any],
        corrected_by: str,
        source_text: str | None = None,
        note: str | None = None,
    ) -> RequirementFeedbackDraft:
        """Return the learning draft for a user correction."""
        return RequirementFeedbackDraft(
            requirement_id=requirement_id,
            original=RequirementExtractionSnapshot.from_mapping(original),
            corrected=RequirementExtractionSnapshot.from_mapping(corrected),
            source_text=source_text,
            feedback_type=FEEDBACK_CORRECTION,
            corrected_by=corrected_by,
            correction_note=note,
        )

    def rejection(
        self,
        *,
        requirement_id: RequirementId,
        original: Mapping[str, Any],
        rejected_by: str,
        reason: str,
        source_text: str | None = None,
    ) -> RequirementFeedbackDraft:
        """Return the learning draft for a rejected extraction."""
        return RequirementFeedbackDraft(
            requirement_id=requirement_id,
            original=RequirementExtractionSnapshot.from_mapping(original),
            corrected=RequirementExtractionSnapshot(
                title=REJECTED_CORRECTION_TITLE,
                description=reason,
            ),
            source_text=source_text,
            feedback_type=FEEDBACK_REJECTION,
            corrected_by=rejected_by,
            correction_note=reason,
        )

    def changed_fields(
        self,
        original: Mapping[str, Any],
        corrected: Mapping[str, Any],
    ) -> list[str]:
        """Return tracked fields changed between two requirement mappings."""
        return RequirementExtractionSnapshot.from_mapping(original).changed_fields(
            RequirementExtractionSnapshot.from_mapping(corrected)
        )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "FEEDBACK_CORRECTION",
    "FEEDBACK_REJECTION",
    "REJECTED_CORRECTION_TITLE",
    "RequirementExtractionSnapshot",
    "RequirementFeedbackDraft",
    "RequirementFeedbackLearningPolicy",
    "TRACKED_FEEDBACK_FIELDS",
]
