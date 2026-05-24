"""Domain service for materializing Requirement extraction results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from shared.core.identifiers import MeetingId, RequirementId


@dataclass(frozen=True, slots=True)
class ExtractedRequirementDraft:
    """Immutable draft for one requirement extracted from a meeting."""

    title: str
    description: str
    category: str
    priority: str
    source_quote: str | None
    source_meeting_ids: tuple[str, ...]

    @classmethod
    def from_extracted(
        cls,
        requirement: Any,
        *,
        meeting_id: MeetingId,
    ) -> "ExtractedRequirementDraft":
        """Build a normalized draft from an extractor-owned requirement object."""
        return cls(
            title=_required_str(requirement, "title"),
            description=_required_str(requirement, "description"),
            category=_required_str(requirement, "category"),
            priority=_required_str(requirement, "priority"),
            source_quote=_optional_str(getattr(requirement, "source_quote", None)),
            source_meeting_ids=(str(meeting_id),),
        )

    def requirement_kwargs(self) -> dict[str, Any]:
        """Return mutable constructor fields for the persistence boundary."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "source_quote": self.source_quote,
            "source_meeting_ids": list(self.source_meeting_ids),
        }


@dataclass(frozen=True, slots=True)
class ExtractedOpenQuestionDraft:
    """Immutable draft for an extracted open question before persistence IDs exist."""

    question: str
    context: str | None
    requirement_index: int

    @classmethod
    def for_first_requirement(cls, question: Any) -> "ExtractedOpenQuestionDraft":
        """Build a question draft using the current first-requirement rule."""
        return cls(
            question=_required_str(question, "question"),
            context=_optional_str(getattr(question, "context", None)),
            requirement_index=0,
        )

    def bind_requirement(
        self,
        requirement_ids: Sequence[RequirementId],
    ) -> "MaterializedOpenQuestionDraft | None":
        """Bind this question to a persisted requirement ID if the target exists."""
        if self.requirement_index >= len(requirement_ids):
            return None
        return MaterializedOpenQuestionDraft(
            requirement_id=str(requirement_ids[self.requirement_index]),
            question=self.question,
            context=self.context,
        )


@dataclass(frozen=True, slots=True)
class MaterializedOpenQuestionDraft:
    """Immutable draft for an open question after its requirement ID is known."""

    requirement_id: str
    question: str
    context: str | None

    def open_question_kwargs(self) -> dict[str, Any]:
        """Return mutable constructor fields for the persistence boundary."""
        return {
            "requirement_id": self.requirement_id,
            "question": self.question,
            "context": self.context,
        }


class MaterializedRequirementRecord(Protocol):
    """Persisted requirement fields needed for extraction publication."""

    id: str
    title: str
    description: str
    category: str
    priority: str


@dataclass(frozen=True, slots=True)
class MaterializedRequirementSummary:
    """Immutable summary of one persisted requirement extraction."""

    requirement_id: RequirementId
    title: str
    description: str
    category: str
    priority: str

    @classmethod
    def from_record(
        cls,
        requirement: MaterializedRequirementRecord,
    ) -> "MaterializedRequirementSummary":
        """Build a publication summary from a persisted requirement record."""
        return cls(
            requirement_id=RequirementId(str(requirement.id)),
            title=str(requirement.title),
            description=str(requirement.description),
            category=str(requirement.category),
            priority=str(requirement.priority),
        )

    def event_requirement_payload(self) -> dict[str, str]:
        """Return the requirement fragment for the extracted event payload."""
        return {
            "id": str(self.requirement_id),
            "title": self.title,
            "priority": self.priority,
            "category": self.category,
        }

    def search_index_document(self, *, meeting_id: MeetingId) -> dict[str, Any]:
        """Return the search-index document for this extracted requirement."""
        return {
            "id": str(self.requirement_id),
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "metadata": {
                "meeting_id": str(meeting_id),
                "priority": self.priority,
            },
        }


@dataclass(frozen=True, slots=True)
class RequirementExtractionPublication:
    """Published-language projection for a completed extraction."""

    meeting_id: MeetingId
    requirements: tuple[MaterializedRequirementSummary, ...]

    @property
    def count(self) -> int:
        """Return the number of published requirements."""
        return len(self.requirements)

    @property
    def requirement_ids(self) -> tuple[str, ...]:
        """Return persisted requirement IDs in publication order."""
        return tuple(
            str(requirement.requirement_id) for requirement in self.requirements
        )

    def event_payload(self) -> dict[str, Any]:
        """Return the Requirement extracted integration-event payload."""
        return {
            "meeting_id": str(self.meeting_id),
            "requirement_ids": list(self.requirement_ids),
            "count": self.count,
            "requirements": [
                requirement.event_requirement_payload()
                for requirement in self.requirements
            ],
        }

    def search_index_documents(self) -> list[dict[str, Any]]:
        """Return search-index documents for best-effort indexing."""
        return [
            requirement.search_index_document(meeting_id=self.meeting_id)
            for requirement in self.requirements
        ]


class RequirementExtractionPublicationPolicy:
    """Build published extraction evidence after requirements are persisted."""

    def build(
        self,
        *,
        meeting_id: MeetingId,
        requirements: Sequence[MaterializedRequirementRecord],
    ) -> RequirementExtractionPublication:
        """Build the immutable publication projection for extracted requirements."""
        return RequirementExtractionPublication(
            meeting_id=meeting_id,
            requirements=tuple(
                MaterializedRequirementSummary.from_record(requirement)
                for requirement in requirements
            ),
        )


@dataclass(frozen=True, slots=True)
class RequirementExtractionPlan:
    """Immutable materialization plan for one meeting extraction result."""

    requirements: tuple[ExtractedRequirementDraft, ...]
    open_questions: tuple[ExtractedOpenQuestionDraft, ...]

    @property
    def requirements_count(self) -> int:
        """Return the number of requirement drafts."""
        return len(self.requirements)

    @property
    def open_questions_count(self) -> int:
        """Return the number of open-question drafts."""
        return len(self.open_questions)

    def materialize_open_questions(
        self,
        *,
        requirement_ids: Sequence[RequirementId],
    ) -> tuple[MaterializedOpenQuestionDraft, ...]:
        """Return open-question drafts bound to persisted requirement IDs."""
        return tuple(
            draft
            for draft in (
                question.bind_requirement(requirement_ids)
                for question in self.open_questions
            )
            if draft is not None
        )


class RequirementExtractionMaterializer:
    """Build Requirement-domain drafts from extractor-owned result objects."""

    def materialize(
        self,
        *,
        extraction: Any,
        meeting_id: MeetingId,
    ) -> RequirementExtractionPlan:
        """Build the immutable domain plan for extracted requirements/questions."""
        requirements = tuple(
            ExtractedRequirementDraft.from_extracted(
                requirement,
                meeting_id=meeting_id,
            )
            for requirement in extraction.requirements
        )
        open_questions: tuple[ExtractedOpenQuestionDraft, ...] = ()
        if requirements:
            open_questions = tuple(
                ExtractedOpenQuestionDraft.for_first_requirement(question)
                for question in extraction.open_questions
            )
        return RequirementExtractionPlan(
            requirements=requirements,
            open_questions=open_questions,
        )


def _required_str(source: Any, field_name: str) -> str:
    return str(getattr(source, field_name))


def _optional_str(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "ExtractedOpenQuestionDraft",
    "ExtractedRequirementDraft",
    "MaterializedRequirementRecord",
    "MaterializedRequirementSummary",
    "MaterializedOpenQuestionDraft",
    "RequirementExtractionMaterializer",
    "RequirementExtractionPublication",
    "RequirementExtractionPublicationPolicy",
    "RequirementExtractionPlan",
]
