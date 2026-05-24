"""Tests for the AuditEvent aggregate."""

import pytest

from shared.control_plane.domain.audit_event import (
    AuditEvent,
    InvalidAuditEventError,
    clean_audit_detail,
)
from shared.control_plane.models import (
    AgentRunStatus,
)
from shared.control_plane.models import (
    AuditEvent as AuditEventRecord,
)


def test_audit_event_for_append_normalizes_record() -> None:
    aggregate = AuditEvent.for_append(
        AuditEventRecord(
            audit_event_id=" audit_test ",
            company_id=" cmp_test ",
            action=" agent_role.created ",
            target_type=" agent_role ",
            target_id=" cto ",
            actor_type=" ",
            actor_id=" human:operator ",
            trace_id=" trace_test ",
            run_id=" ",
            work_item_id=None,
            idempotency_key=" ",
            detail={
                "status": AgentRunStatus.SUCCEEDED,
                "metadata_keys": ("source", "result"),
                "nested": {"from_status": AgentRunStatus.RUNNING},
            },
        )
    )

    assert aggregate.audit_event_id == "audit_test"
    assert aggregate.idempotency_key is None
    assert aggregate.record.company_id == "cmp_test"
    assert aggregate.record.action == "agent_role.created"
    assert aggregate.record.target_type == "agent_role"
    assert aggregate.record.target_id == "cto"
    assert aggregate.record.actor_type == "system"
    assert aggregate.record.actor_id == "human:operator"
    assert aggregate.record.trace_id == "trace_test"
    assert aggregate.record.run_id is None
    assert aggregate.record.work_item_id is None
    assert aggregate.record.detail == {
        "status": "succeeded",
        "metadata_keys": ["source", "result"],
        "nested": {"from_status": "running"},
    }


def test_audit_event_requires_target_identity() -> None:
    with pytest.raises(InvalidAuditEventError, match="target_id_required"):
        AuditEvent.for_append(
            AuditEventRecord(
                company_id="cmp_test",
                action="agent_role.created",
                target_type="agent_role",
                target_id=" ",
            )
        )


def test_clean_audit_detail_normalizes_nested_json_values() -> None:
    assert clean_audit_detail(
        {
            "status": AgentRunStatus.FAILED,
            "history": (AgentRunStatus.RUNNING, AgentRunStatus.FAILED),
            "nested": {"states": [AgentRunStatus.PENDING]},
        }
    ) == {
        "status": "failed",
        "history": ["running", "failed"],
        "nested": {"states": ["pending"]},
    }
