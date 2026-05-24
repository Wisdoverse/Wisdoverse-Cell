"""Unit tests for Requirement meeting-source metadata value object."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agents.requirement_manager.core.domain.meeting_source import (
    MeetingSourceMetadata,
)


def test_meeting_source_metadata_normalizes_inbound_values() -> None:
    meeting_date = datetime(2026, 5, 23, 9, 30, tzinfo=UTC)

    metadata = MeetingSourceMetadata.from_values(
        source="feishu",
        source_id=123,
        title="Planning",
        meeting_date=meeting_date,
        participants=["Alice", 42],
        context="Sprint planning",
    )

    assert metadata.source == "feishu"
    assert metadata.source_id == "123"
    assert metadata.title == "Planning"
    assert metadata.meeting_date == meeting_date
    assert metadata.participants == ("Alice", "42")
    assert metadata.context == "Sprint planning"
    assert metadata.meeting_date_iso() == "2026-05-23T09:30:00+00:00"
    assert metadata.participants_for_extraction() == ["Alice", "42"]


def test_meeting_source_metadata_returns_boundary_copies() -> None:
    metadata = MeetingSourceMetadata.from_values(
        source="upload",
        participants=["Alice"],
    )

    participants = metadata.participants_list()
    participants.append("Bob")

    assert metadata.participants == ("Alice",)
    assert metadata.participants_list() == ["Alice"]
    assert metadata.meeting_kwargs(raw_content="notes") == {
        "source": "upload",
        "source_id": None,
        "title": None,
        "raw_content": "notes",
        "meeting_date": None,
        "participants": ["Alice"],
        "context": None,
    }


def test_meeting_source_metadata_preserves_missing_participants_signal() -> None:
    metadata = MeetingSourceMetadata.from_values(source="agent_request")

    assert metadata.participants == ()
    assert metadata.participants_list() == []
    assert metadata.participants_for_extraction() is None
    assert metadata.meeting_date_iso() is None


def test_meeting_source_metadata_is_immutable() -> None:
    metadata = MeetingSourceMetadata.from_values(source="upload")

    with pytest.raises(AttributeError):
        metadata.source = "feishu"  # type: ignore[misc]
