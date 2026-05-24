"""Unit tests for the Artifact aggregate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.artifact import (
    Artifact,
    ArtifactCreated,
    InvalidArtifactError,
    artifact_type_value,
)
from shared.control_plane.models import AgentRunStatus, ArtifactType
from shared.control_plane.models import Artifact as ArtifactRecord


def _make_record(**overrides) -> ArtifactRecord:
    values = {
        "company_id": "cmp_test",
        "artifact_type": ArtifactType.REPORT,
        "title": "  Evidence report  ",
        "uri": "  urn:wisdoverse-cell:artifact:evidence  ",
        "content_hash": "sha256:test",
        "created_by_agent_id": "dev-agent",
    }
    values.update(overrides)
    return ArtifactRecord(**values)


def test_artifact_creation_normalizes_evidence_record() -> None:
    aggregate = Artifact.for_creation(_make_record(metadata={"source": "operator"}))

    assert aggregate.record.title == "Evidence report"
    assert aggregate.record.uri == "urn:wisdoverse-cell:artifact:evidence"
    assert aggregate.record.artifact_type == ArtifactType.REPORT.value
    assert aggregate.record.metadata == {"source": "operator"}


def test_artifact_requires_title_and_uri() -> None:
    with pytest.raises(InvalidArtifactError, match="title_required"):
        Artifact.for_creation(_make_record(title=" "))
    with pytest.raises(InvalidArtifactError, match="uri_required"):
        Artifact.for_creation(_make_record(uri=" "))


def test_artifact_applies_execution_links_before_persistence() -> None:
    aggregate = Artifact.for_creation(_make_record())

    aggregate.with_execution_links(goal_id="goal_1", work_item_id="work_1")

    assert aggregate.record.goal_id == "goal_1"
    assert aggregate.record.work_item_id == "work_1"


def test_artifact_creation_raises_pii_safe_domain_event() -> None:
    aggregate = Artifact.for_creation(_make_record())
    aggregate.mark_created()
    events = aggregate.pull_events()

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, ArtifactCreated)
    assert event.artifact_type == ArtifactType.REPORT.value
    assert event.has_content_hash is True
    assert event.created_by_agent_id == "dev-agent"
    assert "Evidence report" not in str(event.to_payload())
    assert "artifact:evidence" not in str(event.to_payload())


def test_pull_events_clears_buffer() -> None:
    aggregate = Artifact.for_creation(_make_record())
    aggregate.mark_created()
    aggregate.pull_events()
    assert aggregate.pull_events() == []


def test_artifact_event_is_frozen_value_object() -> None:
    event = ArtifactCreated(
        artifact_id="artifact_1",
        company_id="cmp_test",
        artifact_type=ArtifactType.REPORT.value,
        goal_id=None,
        work_item_id=None,
        run_id=None,
        created_by_agent_id=None,
        has_content_hash=False,
    )

    with pytest.raises(FrozenInstanceError):
        event.has_content_hash = True  # type: ignore[misc]


def test_artifact_type_value_accepts_enum_string_and_none() -> None:
    assert artifact_type_value(ArtifactType.REPORT) == ArtifactType.REPORT.value
    assert artifact_type_value("code_patch") == "code_patch"
    assert artifact_type_value(None) is None


def test_artifact_metadata_uses_control_plane_value_object() -> None:
    aggregate = Artifact.for_creation(
        _make_record(
            metadata={
                " status ": AgentRunStatus.SUCCEEDED,
                "nested": {"states": (AgentRunStatus.RUNNING,)},
            }
        )
    )

    assert aggregate.record.metadata == {
        "status": "succeeded",
        "nested": {"states": ["running"]},
    }
