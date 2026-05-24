"""Tests for Control Plane domain-event outbox mapping."""

from shared.control_plane.domain_event_outbox import (
    CONTROL_PLANE_EVENT_SOURCE_AGENT,
    audit_event_carries_domain_event,
    outbox_event_from_audit_event,
)
from shared.control_plane.models import AuditEvent


def test_outbox_event_from_domain_event_audit_preserves_contract() -> None:
    audit = AuditEvent(
        audit_event_id="aud_domain_event",
        company_id="cmp_test",
        action="goal.updated",
        target_type="goal",
        target_id="goal_test",
        actor_type="user",
        actor_id="operator_1",
        trace_id="trace_test",
        run_id="run_test",
        work_item_id="work_test",
        detail={
            "domain_event": "GoalStatusChanged",
            "company_id": "cmp_test",
            "goal_id": "goal_test",
            "from_status": "active",
            "to_status": "completed",
        },
    )

    event = outbox_event_from_audit_event(audit)

    assert audit_event_carries_domain_event(audit)
    assert event.event_type == "goal.updated"
    assert event.source_agent == CONTROL_PLANE_EVENT_SOURCE_AGENT
    assert event.metadata.trace_id == "trace_test"
    assert event.metadata.correlation_id == "aud_domain_event"
    assert event.payload["audit_event_id"] == "aud_domain_event"
    assert event.payload["company_id"] == "cmp_test"
    assert event.payload["target_type"] == "goal"
    assert event.payload["target_id"] == "goal_test"
    assert event.payload["domain_event"] == "GoalStatusChanged"
    assert event.payload["run_id"] == "run_test"
    assert event.payload["work_item_id"] == "work_test"
    assert event.payload["detail"]["to_status"] == "completed"


def test_plain_audit_event_is_not_a_domain_event_outbox_candidate() -> None:
    audit = AuditEvent(
        company_id="cmp_test",
        action="operator.viewed",
        target_type="dashboard",
        target_id="dash_test",
        detail={"source": "operator"},
    )

    assert not audit_event_carries_domain_event(audit)
