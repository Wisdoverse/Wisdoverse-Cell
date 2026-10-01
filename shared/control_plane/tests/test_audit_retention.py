"""Tests for bounded, immutable audit export and redaction policy."""

from datetime import UTC, datetime, timedelta

import pytest

from shared.control_plane.domain.audit_retention import (
    MAX_DETAIL_DEPTH,
    MAX_DETAIL_ITEMS,
    MAX_DETAIL_STRING_LENGTH,
    AuditRetentionError,
    export_audit_events,
    sanitize_audit_detail,
)
from shared.control_plane.models import AuditEvent

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _event(
    *,
    audit_id: str,
    company: str = "cmp_one",
    actor_type: str = "operator",
    created_at: datetime | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        audit_event_id=audit_id,
        company_id=company,
        action="artifact.created",
        target_type="artifact",
        target_id="art_linked_1",
        actor_type=actor_type,
        actor_id="operator_123",
        trace_id="trace_link_1",
        run_id="run_link_1",
        work_item_id="work_link_1",
        idempotency_key="hash-link-abc",
        detail=detail or {},
        created_at=created_at or NOW,
    )


def test_redaction_removes_secret_keys_patterns_credentials_and_freeform_fields() -> None:
    original = {
        "api_token": "should never be exported",
        "request_body": {"customer_email": "person@example.test"},
        "authorization": "Basic private-value",
        "cookie": "session=private-value",
        "details": (
            "Bearer abcdefghijklmnop "
            "api_key=assignment-secret "
            "https://alice:password123@objects.example.test/path "
            "ghp_abcdefghijklmnopqrstuvwxyz123456"
        ),
        "artifact_id": "art_keep_123",
        "content_hash": "sha256:keep-this-linkage",
        "nested": {"access_token": "nested-secret", "status": "succeeded"},
    }

    safe = sanitize_audit_detail(original)
    serialized = str(safe)
    for secret in (
        "should never be exported",
        "person@example.test",
        "private-value",
        "session=",
        "abcdefghijklmnop",
        "assignment-secret",
        "alice",
        "password123",
        "ghp_abcdefghijklmnopqrstuvwxyz123456",
    ):
        assert secret not in serialized
    assert safe["artifact_id"] == "art_keep_123"
    assert safe["content_hash"] == "sha256:keep-this-linkage"
    assert safe["nested"]["status"] == "succeeded"
    assert "request_body" not in safe
    assert original["api_token"] == "should never be exported"
    with pytest.raises(TypeError):
        safe["nested"]["status"] = "changed"


def test_redaction_has_deterministic_depth_item_and_string_bounds() -> None:
    deep: dict = {"leaf": "safe"}
    for level in range(MAX_DETAIL_DEPTH + 3):
        deep = {f"level_{level:02d}": deep}
    safe = sanitize_audit_detail(
        {
            "deep": deep,
            "long": "x" * (MAX_DETAIL_STRING_LENGTH + 30),
            "many": list(range(MAX_DETAIL_ITEMS + 3)),
        }
    )

    assert len(safe["long"]) == MAX_DETAIL_STRING_LENGTH
    assert safe["many"][-1] == "[TRUNCATED_ITEMS]"
    assert len(safe["many"]) == MAX_DETAIL_ITEMS + 1
    node = safe["deep"]
    for _ in range(MAX_DETAIL_DEPTH + 3):
        if not isinstance(node, dict) and not hasattr(node, "keys"):
            break
        node = next(iter(node.values()))
    assert node == "[TRUNCATED]"


def test_export_filters_exact_company_sorts_and_exposes_retention_and_source_counts() -> None:
    events = [
        _event(audit_id="z_event", actor_type="agent", created_at=NOW - timedelta(hours=1)),
        _event(audit_id="other_company", company="cmp_two"),
        _event(audit_id="a_event", actor_type="operator", created_at=NOW - timedelta(hours=1)),
        _event(audit_id="outside_window", created_at=NOW - timedelta(days=2)),
    ]
    exported = export_audit_events(
        events,
        company_id="cmp_one",
        since=NOW - timedelta(days=1),
        until=NOW,
        retention_days=90,
        now=NOW,
    )

    assert [event.audit_event_id for event in exported.events] == ["a_event", "z_event"]
    assert all(event.company_id == "cmp_one" for event in exported.events)
    assert exported.source_counts == (("agent", 1), ("operator", 1))
    assert exported.retention_policy.to_dict() == {
        "retention_days": 90,
        "oldest_exportable_at": (NOW - timedelta(days=90)).isoformat().replace("+00:00", "Z"),
    }
    assert exported.to_dict()["total"] == 2
    assert exported.events[0].target_id == "art_linked_1"


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"until": NOW + timedelta(seconds=1)}, "invalid_export_window"),
        ({"since": NOW + timedelta(seconds=1)}, "invalid_export_window"),
        ({"since": NOW - timedelta(days=91)}, "export_window_outside_retention"),
        ({"since": NOW.replace(tzinfo=None)}, "since_must_include_timezone"),
        ({"retention_days": 0}, "invalid_retention_days"),
    ],
)
def test_export_rejects_future_invalid_and_out_of_retention_windows(
    overrides: dict, error: str
) -> None:
    arguments = {
        "records": [],
        "company_id": "cmp_one",
        "since": NOW - timedelta(days=1),
        "until": NOW,
        "retention_days": 90,
        "now": NOW,
    }
    arguments.update(overrides)
    with pytest.raises(AuditRetentionError, match=error):
        export_audit_events(**arguments)


def test_export_rejects_naive_until_and_reversed_range() -> None:
    with pytest.raises(AuditRetentionError, match="until_must_include_timezone"):
        export_audit_events(
            [],
            company_id="cmp_one",
            since=NOW - timedelta(days=1),
            until=NOW.replace(tzinfo=None),
            now=NOW,
        )
    with pytest.raises(AuditRetentionError, match="invalid_export_window"):
        export_audit_events(
            [], company_id="cmp_one", since=NOW, until=NOW - timedelta(seconds=1), now=NOW
        )
