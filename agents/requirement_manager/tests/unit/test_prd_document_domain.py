"""Unit tests for PRD composition value objects."""

from __future__ import annotations

from agents.requirement_manager.core.domain.prd_document import (
    PRDDocumentDraft,
    PRDRequirementSnapshot,
)


def test_prd_requirement_snapshot_normalizes_mapping_values() -> None:
    snapshot = PRDRequirementSnapshot.from_mapping(
        {
            "id": 1,
            "title": "Launch sequencing",
            "description": None,
            "category": "Feature",
            "priority": "high",
            "status": "confirmed",
            "source_quote": "Need a launch market",
            "confirmed_by": "pm",
            "confirmed_at": "2026-05-23T10:00:00+00:00",
        }
    )

    assert snapshot.requirement_id == "1"
    assert snapshot.title == "Launch sequencing"
    assert snapshot.description is None
    assert snapshot.prompt_payload()["id"] == "1"
    assert snapshot.prompt_payload()["source_quote"] == "Need a launch market"


def test_prd_document_draft_builds_metadata_and_requirement_payloads() -> None:
    draft = PRDDocumentDraft.from_requirements(
        requirements=[
            {"id": "req_2", "title": "B", "category": "Ops", "priority": "low"},
            {"id": "req_1", "title": "A", "category": "Core", "priority": "high"},
        ],
        project_name="Wisdoverse Cell",
        version="2.0",
        generated_date="2026-05-23",
    )

    assert draft.requirements_count == 2
    assert draft.metadata_payload() == {
        "project_name": "Wisdoverse Cell",
        "version": "2.0",
        "generated_date": "2026-05-23",
        "total_requirements": 2,
    }
    assert [item["id"] for item in draft.requirements_payload()] == ["req_2", "req_1"]
    assert [item.title for item in draft.sorted_requirements()] == ["A", "B"]


def test_prd_document_draft_is_immutable() -> None:
    draft = PRDDocumentDraft.from_requirements(
        requirements=[],
        project_name="Wisdoverse Cell",
        version="1.0",
        generated_date="2026-05-23",
    )

    try:
        draft.project_name = "Other"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("PRDDocumentDraft should be immutable")
