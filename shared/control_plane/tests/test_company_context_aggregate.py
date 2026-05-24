"""Tests for the CompanyContext aggregate."""

import pytest

from shared.control_plane.domain.company_context import (
    CompanyContext,
    CompanyContextCreated,
    CompanyContextUpdated,
    InvalidCompanyContextError,
)
from shared.control_plane.models import (
    AgentRunStatus,
)
from shared.control_plane.models import (
    CompanyContext as CompanyContextRecord,
)


def test_company_context_for_creation_normalizes_record() -> None:
    aggregate = CompanyContext.for_creation(
        CompanyContextRecord(
            company_id="cmp_company_domain",
            name="  Wisdoverse Cell  ",
            mission="  AI-native operations  ",
            metadata={"stage": "domain"},
        )
    )

    assert aggregate.record.name == "Wisdoverse Cell"
    assert aggregate.record.mission == "AI-native operations"
    assert aggregate.record.metadata == {"stage": "domain"}


def test_company_context_requires_name() -> None:
    with pytest.raises(InvalidCompanyContextError, match="name_required"):
        CompanyContext.for_creation(
            CompanyContextRecord(company_id="cmp_company_domain", name=" ")
        )


def test_company_context_creation_raises_pii_safe_event() -> None:
    aggregate = CompanyContext.for_creation(
        CompanyContextRecord(
            company_id="cmp_company_domain",
            name="Wisdoverse Cell",
            mission="Operate with agents",
            metadata={"stage": "domain"},
        )
    )

    aggregate.mark_created()

    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, CompanyContextCreated)
    assert event.company_id == "cmp_company_domain"
    assert event.name_length == len("Wisdoverse Cell")
    assert event.mission_length == len("Operate with agents")
    assert event.metadata_keys == ("stage",)
    assert "Wisdoverse" not in str(event.to_payload())
    assert aggregate.pull_events() == []


def test_company_context_update_raises_pii_safe_event() -> None:
    aggregate = CompanyContext.for_creation(
        CompanyContextRecord(company_id="cmp_company_domain", name="Wisdoverse Cell")
    )

    aggregate.apply_update(
        name="  Wisdoverse Cell Public  ",
        mission="  Public-first operations  ",
        metadata={"stage": "public"},
    )

    assert aggregate.record.name == "Wisdoverse Cell Public"
    assert aggregate.record.mission == "Public-first operations"
    assert aggregate.record.metadata == {"stage": "public"}

    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, CompanyContextUpdated)
    assert event.name_changed
    assert event.mission_changed
    assert event.metadata_changed
    assert event.metadata_keys == ("stage",)
    assert "Public-first" not in str(event.to_payload())


def test_company_context_metadata_uses_control_plane_value_object() -> None:
    aggregate = CompanyContext.for_creation(
        CompanyContextRecord(
            company_id="cmp_company_domain",
            name="Wisdoverse Cell",
            metadata={" status ": AgentRunStatus.SUCCEEDED, "tags": {"b", "a"}},
        )
    )

    assert aggregate.record.metadata == {
        "status": "succeeded",
        "tags": ["a", "b"],
    }
