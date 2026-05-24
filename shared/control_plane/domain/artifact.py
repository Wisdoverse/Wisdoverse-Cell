"""Artifact aggregate root and evidence-recording policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Artifact as ArtifactRecord
from ..models import ArtifactType
from .events import ControlPlaneDomainEvent
from .metadata import ControlPlaneMetadata


class InvalidArtifactError(ValueError):
    """Raised when an artifact record violates evidence invariants."""


def artifact_type_value(value: ArtifactType | str | None) -> str | None:
    """Return a persistence-ready artifact-type value."""
    if value is None:
        return None
    if isinstance(value, ArtifactType):
        return value.value
    return str(value)


def _required_text(value: Any, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise InvalidArtifactError(f"{field_name}_required")
    return cleaned


@dataclass(frozen=True, slots=True)
class ArtifactCreated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when an Artifact is recorded."""

    artifact_id: str
    company_id: str
    artifact_type: str
    goal_id: str | None
    work_item_id: str | None
    run_id: str | None
    created_by_agent_id: str | None
    has_content_hash: bool


@dataclass
class Artifact:
    """Artifact aggregate root for durable evidence records."""

    record: ArtifactRecord
    _events: list[ArtifactCreated] = field(default_factory=list)

    @classmethod
    def for_creation(cls, record: ArtifactRecord) -> Artifact:
        aggregate = cls(record=record)
        aggregate._normalize_creation_record()
        return aggregate

    @classmethod
    def from_record(cls, record: ArtifactRecord) -> Artifact:
        return cls(record=record)

    @property
    def artifact_id(self) -> str:
        return self.record.artifact_id

    @property
    def artifact_type(self) -> str:
        return artifact_type_value(self.record.artifact_type) or ArtifactType.OTHER.value

    def with_execution_links(
        self,
        *,
        goal_id: str | None,
        work_item_id: str | None,
    ) -> None:
        """Apply execution-link resolution before persistence."""
        self.record = self.record.model_copy(
            update={
                "goal_id": goal_id,
                "work_item_id": work_item_id,
            }
        )
        self._normalize_creation_record()

    def mark_created(self) -> None:
        """Raise the creation event after persistence has accepted the record."""
        self._events.append(
            ArtifactCreated(
                artifact_id=self.record.artifact_id,
                company_id=self.record.company_id,
                artifact_type=self.artifact_type,
                goal_id=self.record.goal_id,
                work_item_id=self.record.work_item_id,
                run_id=self.record.run_id,
                created_by_agent_id=self.record.created_by_agent_id,
                has_content_hash=bool(self.record.content_hash),
            )
        )

    def pull_events(self) -> list[ArtifactCreated]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained

    def _normalize_creation_record(self) -> None:
        self.record = self.record.model_copy(
            update={
                "title": _required_text(self.record.title, "title"),
                "uri": _required_text(self.record.uri, "uri"),
                "artifact_type": self.artifact_type,
                "metadata": ControlPlaneMetadata.from_mapping(
                    self.record.metadata
                ).as_dict(),
            }
        )


__all__ = [
    "Artifact",
    "ArtifactCreated",
    "InvalidArtifactError",
    "artifact_type_value",
]
