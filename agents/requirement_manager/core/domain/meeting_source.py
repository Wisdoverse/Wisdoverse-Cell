"""Meeting source value objects for Requirement ingestion."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class MeetingPersistenceDraft:
    """Immutable draft for creating one meeting record at the persistence boundary."""

    source: str
    raw_content: str
    source_id: str | None = None
    title: str | None = None
    meeting_date: datetime | None = None
    participants: tuple[str, ...] = ()
    context: str | None = None

    def meeting_kwargs(self) -> dict[str, Any]:
        """Return mutable constructor fields for the persistence adapter."""
        return {
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "raw_content": self.raw_content,
            "meeting_date": self.meeting_date,
            "participants": list(self.participants),
            "context": self.context,
        }


@dataclass(frozen=True, slots=True)
class MeetingSourceMetadata:
    """Immutable source metadata for one ingested meeting artifact."""

    source: str
    source_id: str | None = None
    title: str | None = None
    meeting_date: datetime | None = None
    participants: tuple[str, ...] = ()
    context: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        source: str,
        source_id: Any | None = None,
        title: Any | None = None,
        meeting_date: datetime | None = None,
        participants: Sequence[Any] | None = None,
        context: Any | None = None,
    ) -> "MeetingSourceMetadata":
        """Build normalized, immutable metadata from inbound source values."""
        return cls(
            source=str(source),
            source_id=_optional_str(source_id),
            title=_optional_str(title),
            meeting_date=meeting_date,
            participants=tuple(str(participant) for participant in participants or ()),
            context=_optional_str(context),
        )

    def participants_list(self) -> list[str]:
        """Return a mutable list copy for persistence boundaries."""
        return list(self.participants)

    def participants_for_extraction(self) -> list[str] | None:
        """Return extractor-ready participants while preserving the no-data signal."""
        if not self.participants:
            return None
        return self.participants_list()

    def meeting_date_iso(self) -> str | None:
        """Return the ISO timestamp expected by the extraction port."""
        if self.meeting_date is None:
            return None
        return self.meeting_date.isoformat()

    def meeting_kwargs(self, *, raw_content: str) -> dict[str, Any]:
        """Return persistence-ready Meeting creation fields."""
        return self.meeting_draft(raw_content=raw_content).meeting_kwargs()

    def meeting_draft(self, *, raw_content: str) -> MeetingPersistenceDraft:
        """Return an immutable persistence draft for the meeting record."""
        return MeetingPersistenceDraft(
            source=self.source,
            source_id=self.source_id,
            title=self.title,
            raw_content=raw_content,
            meeting_date=self.meeting_date,
            participants=self.participants,
            context=self.context,
        )


def _optional_str(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = ["MeetingPersistenceDraft", "MeetingSourceMetadata"]
