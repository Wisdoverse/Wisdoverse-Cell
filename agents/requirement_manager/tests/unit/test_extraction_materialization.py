"""Unit tests for Requirement extraction materialization domain service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.requirement_manager.core.domain.extraction_materialization import (
    RequirementExtractionMaterializer,
    RequirementExtractionPublicationPolicy,
)
from shared.core.identifiers import MeetingId, RequirementId


def _requirement(**overrides):
    values = {
        "title": "Offline capture",
        "description": "Capture notes without connectivity",
        "category": "feature",
        "priority": "high",
        "source_quote": "We need offline mode",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _question(**overrides):
    values = {
        "question": "Which platforms need offline mode?",
        "context": "Scope is unclear",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_materializer_builds_requirement_and_question_drafts() -> None:
    plan = RequirementExtractionMaterializer().materialize(
        extraction=SimpleNamespace(
            requirements=[_requirement(), _requirement(title="Sync")],
            open_questions=[_question(), _question(question="What SLA?")],
        ),
        meeting_id=MeetingId("mtg_1"),
    )

    assert plan.requirements_count == 2
    assert plan.open_questions_count == 2
    assert plan.requirements[0].source_meeting_ids == ("mtg_1",)
    assert plan.requirements[0].requirement_kwargs() == {
        "title": "Offline capture",
        "description": "Capture notes without connectivity",
        "category": "feature",
        "priority": "high",
        "source_quote": "We need offline mode",
        "source_meeting_ids": ["mtg_1"],
    }
    assert {question.requirement_index for question in plan.open_questions} == {0}


def test_materializer_binds_open_questions_to_first_persisted_requirement() -> None:
    plan = RequirementExtractionMaterializer().materialize(
        extraction=SimpleNamespace(
            requirements=[_requirement(), _requirement(title="Sync")],
            open_questions=[_question(), _question(question="What SLA?")],
        ),
        meeting_id=MeetingId("mtg_1"),
    )

    question_drafts = plan.materialize_open_questions(
        requirement_ids=[RequirementId("req_1"), RequirementId("req_2")],
    )

    assert [draft.requirement_id for draft in question_drafts] == ["req_1", "req_1"]
    assert question_drafts[0].open_question_kwargs() == {
        "requirement_id": "req_1",
        "question": "Which platforms need offline mode?",
        "context": "Scope is unclear",
    }


def test_publication_policy_builds_event_payload_and_search_documents() -> None:
    publication = RequirementExtractionPublicationPolicy().build(
        meeting_id=MeetingId("mtg_1"),
        requirements=[
            SimpleNamespace(
                id="req_1",
                title="Offline capture",
                description="Capture notes without connectivity",
                category="feature",
                priority="high",
            ),
            SimpleNamespace(
                id="req_2",
                title="Sync",
                description="Sync captured notes later",
                category="reliability",
                priority="medium",
            ),
        ],
    )

    assert publication.requirement_ids == ("req_1", "req_2")
    assert publication.event_payload() == {
        "meeting_id": "mtg_1",
        "requirement_ids": ["req_1", "req_2"],
        "count": 2,
        "requirements": [
            {
                "id": "req_1",
                "title": "Offline capture",
                "priority": "high",
                "category": "feature",
            },
            {
                "id": "req_2",
                "title": "Sync",
                "priority": "medium",
                "category": "reliability",
            },
        ],
    }
    assert publication.search_index_documents() == [
        {
            "id": "req_1",
            "title": "Offline capture",
            "description": "Capture notes without connectivity",
            "category": "feature",
            "metadata": {"meeting_id": "mtg_1", "priority": "high"},
        },
        {
            "id": "req_2",
            "title": "Sync",
            "description": "Sync captured notes later",
            "category": "reliability",
            "metadata": {"meeting_id": "mtg_1", "priority": "medium"},
        },
    ]


def test_materializer_drops_questions_when_no_requirement_exists() -> None:
    plan = RequirementExtractionMaterializer().materialize(
        extraction=SimpleNamespace(
            requirements=[],
            open_questions=[_question()],
        ),
        meeting_id=MeetingId("mtg_1"),
    )

    assert plan.requirements == ()
    assert plan.open_questions == ()
    assert plan.materialize_open_questions(requirement_ids=[]) == ()


def test_extraction_plan_drafts_are_immutable() -> None:
    plan = RequirementExtractionMaterializer().materialize(
        extraction=SimpleNamespace(
            requirements=[_requirement()],
            open_questions=[_question()],
        ),
        meeting_id=MeetingId("mtg_1"),
    )

    with pytest.raises(AttributeError):
        plan.requirements[0].title = "Changed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        plan.open_questions[0].question = "Changed"  # type: ignore[misc]
