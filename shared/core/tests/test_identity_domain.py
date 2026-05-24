"""Tests for Identity / User domain value objects and aggregate methods."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from shared.core.identifiers import UserId
from shared.core.identity_domain import (
    EmailAddress,
    IdentityState,
    InvalidIdentityTransitionError,
    InvalidIdentityValueError,
    PhoneNumber,
    PlatformUserRef,
)
from shared.core.identity_event_outbox import identity_event_from_domain_event
from shared.models.platform import Platform
from shared.models.user import User
from shared.schemas.event import EventTypes


def test_identity_value_objects_normalize_and_validate() -> None:
    """Identity value objects normalize values before persistence."""
    assert str(EmailAddress(" Owner@Example.COM ")) == "owner@example.com"
    assert str(PhoneNumber(" +1 555-0100 ")) == "+15550100"

    with pytest.raises(InvalidIdentityValueError):
        EmailAddress("not-an-email")

    with pytest.raises(InvalidIdentityValueError):
        PhoneNumber("phone-abc")

    openclaw_ref = PlatformUserRef(Platform.OPENCLAW, " openclaw_user ")
    assert openclaw_ref.platform_user_id == "openclaw_user"


def test_user_aggregate_creates_and_links_platform_identity() -> None:
    """User aggregate owns creation and platform-link invariants."""
    occurred_at = datetime(2026, 5, 23, tzinfo=UTC)
    user = User.create_identity(
        user_id=UserId("usr_01identity"),
        name=" Operator ",
        email=" Operator@Example.COM ",
        phone=" +1 555-0100 ",
        platform_ref=PlatformUserRef(Platform.FEISHU, " ou_operator "),
        occurred_at=occurred_at,
    )

    assert user.id == "usr_01identity"
    assert user.name == "Operator"
    assert user.email == "operator@example.com"
    assert user.phone == "+15550100"
    assert user.feishu_open_id == "ou_operator"
    assert user.identity_state == IdentityState.LINKED

    events = user.pull_domain_events()
    assert [event.event_name for event in events] == ["UserCreated", "PlatformLinked"]
    assert events[0].to_payload()["user_id"] == "usr_01identity"
    assert events[1].to_payload()["platform"] == "feishu"

    integration_event = identity_event_from_domain_event(events[0])
    assert integration_event.event_type == EventTypes.IDENTITY_USER_CREATED
    assert integration_event.source_agent == "identity-user"
    assert integration_event.payload["user_id"] == "usr_01identity"
    assert integration_event.payload["email_present"] is True
    assert "email" not in integration_event.payload
    assert "name" not in integration_event.payload


def test_user_aggregate_records_activity_as_state_transition() -> None:
    """Activity can only be recorded after the platform account is linked."""
    user = User.create_identity(
        user_id=UserId("usr_01active"),
        name="Active User",
        email=None,
        platform_ref=PlatformUserRef(Platform.WECOM, "wecom_active"),
    )
    user.pull_domain_events()

    user.record_activity(Platform.WECOM)

    assert user.identity_state == IdentityState.ACTIVE
    assert user.last_active_platform == "wecom"
    assert [event.event_name for event in user.pull_domain_events()] == ["UserActivated"]


def test_user_aggregate_rejects_conflicting_platform_link() -> None:
    """A user cannot be relinked to a different id for the same platform."""
    user = User.create_identity(
        user_id=UserId("usr_01conflict"),
        name="Linked User",
        email=None,
        platform_ref=PlatformUserRef(Platform.WEB, "web_1"),
    )

    user.link_platform_account(PlatformUserRef(Platform.WEB, "web_1"))
    with pytest.raises(InvalidIdentityTransitionError):
        user.link_platform_account(PlatformUserRef(Platform.WEB, "web_2"))

    unlinked = User(id="usr_01unlinked", name="Unlinked")
    with pytest.raises(InvalidIdentityTransitionError):
        unlinked.record_activity(Platform.FEISHU)


def test_user_aggregate_allows_openclaw_activity_without_persisted_mapping() -> None:
    """OpenClaw is translated but has no dedicated users-table mapping column yet."""
    user = User.create_identity(
        user_id=UserId("usr_01openclaw"),
        name="OpenClaw User",
        email=None,
        platform_ref=PlatformUserRef(Platform.OPENCLAW, "openclaw_user"),
    )

    assert user.feishu_open_id is None
    assert user.wecom_user_id is None
    assert user.web_user_id is None

    user.record_activity(Platform.OPENCLAW)

    assert user.identity_state == IdentityState.ACTIVE
    assert user.last_active_platform == "openclaw"
