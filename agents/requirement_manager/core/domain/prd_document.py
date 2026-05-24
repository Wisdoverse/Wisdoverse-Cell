"""PRD composition value objects for Requirement exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PRDRequirementSnapshot:
    """Immutable requirement snapshot used for PRD composition."""

    requirement_id: str | None = None
    title: str = ""
    description: str | None = None
    category: str | None = None
    priority: str | None = None
    status: str | None = None
    source_quote: str | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "PRDRequirementSnapshot":
        """Build a normalized snapshot from export-ready requirement fields."""
        return cls(
            requirement_id=_optional_str(values.get("id")),
            title=_optional_str(values.get("title")) or "",
            description=_optional_str(values.get("description")),
            category=_optional_str(values.get("category")),
            priority=_optional_str(values.get("priority")),
            status=_optional_str(values.get("status")),
            source_quote=_optional_str(values.get("source_quote")),
            confirmed_by=_optional_str(values.get("confirmed_by")),
            confirmed_at=_optional_str(values.get("confirmed_at")),
        )

    def prompt_payload(self) -> dict[str, str | None]:
        """Return the JSON-safe Published Language payload for PRD prompts."""
        return {
            "id": self.requirement_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "source_quote": self.source_quote,
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
        }

    def fallback_sort_key(self) -> tuple[str, str, str]:
        """Return stable sort fields for deterministic fallback rendering."""
        return (
            self.category or "",
            self.priority or "",
            self.title,
        )


@dataclass(frozen=True, slots=True)
class PRDDocumentDraft:
    """Immutable PRD composition before LLM formatting or fallback rendering."""

    project_name: str
    version: str
    generated_date: str
    requirements: tuple[PRDRequirementSnapshot, ...]

    @classmethod
    def from_requirements(
        cls,
        *,
        requirements: Iterable[Mapping[str, Any]],
        project_name: str,
        version: str,
        generated_date: str,
    ) -> "PRDDocumentDraft":
        """Build a PRD draft from requirement export mappings."""
        return cls(
            project_name=str(project_name),
            version=str(version),
            generated_date=str(generated_date),
            requirements=tuple(
                PRDRequirementSnapshot.from_mapping(requirement)
                for requirement in requirements
            ),
        )

    @property
    def requirements_count(self) -> int:
        """Return the number of requirements in this draft."""
        return len(self.requirements)

    def metadata_payload(self) -> dict[str, str | int]:
        """Return prompt metadata as a JSON-safe payload."""
        return {
            "project_name": self.project_name,
            "version": self.version,
            "generated_date": self.generated_date,
            "total_requirements": self.requirements_count,
        }

    def requirements_payload(self) -> list[dict[str, str | None]]:
        """Return requirement snapshots for prompt JSON."""
        return [requirement.prompt_payload() for requirement in self.requirements]

    def sorted_requirements(self) -> tuple[PRDRequirementSnapshot, ...]:
        """Return requirements in deterministic fallback order."""
        return tuple(sorted(self.requirements, key=lambda item: item.fallback_sort_key()))


def _optional_str(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "PRDDocumentDraft",
    "PRDRequirementSnapshot",
]
