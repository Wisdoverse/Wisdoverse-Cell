"""
Tests for collaboration models, DB table, and PatternStore.
"""

from datetime import datetime

import pytest

from shared.evolution.collaboration.models import (
    CollaborationPattern,
    CollaborationStep,
    PatternStatus,
    ShadowRunResult,
)
from shared.evolution.collaboration.pattern_store import PatternStore

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_steps() -> list[CollaborationStep]:
    return [
        CollaborationStep(
            step_id="s1",
            agent_id="analysis-agent",
            action="analyze",
            output_to="s2",
        ),
        CollaborationStep(
            step_id="s2",
            agent_id="pjm-agent",
            action="review",
            input_from="s1",
            on_failure="skip",
        ),
    ]


def _make_pattern(**overrides) -> CollaborationPattern:
    defaults = {
        "name": "Risk Escalation",
        "trigger_event": "risk.detected",
        "steps": _make_steps(),
    }
    defaults.update(overrides)
    return CollaborationPattern(**defaults)


# ── Model Validation Tests ───────────────────────────────────────────────


class TestCollaborationModels:
    def test_pattern_defaults(self):
        pattern = _make_pattern()
        assert pattern.pattern_id.startswith("pat_")
        assert pattern.status == PatternStatus.PROPOSED
        assert pattern.human_approval is False
        assert pattern.approved_by is None
        assert pattern.approved_at is None
        assert isinstance(pattern.created_at, datetime)
        assert pattern.shadow_results == []
        assert pattern.production_results == []

    def test_pattern_serialization_roundtrip(self):
        pattern = _make_pattern()
        json_str = pattern.model_dump_json()
        restored = CollaborationPattern.model_validate_json(json_str)
        assert restored.pattern_id == pattern.pattern_id
        assert restored.name == pattern.name
        assert len(restored.steps) == 2
        assert restored.steps[0].agent_id == "analysis-agent"

    def test_step_defaults(self):
        step = CollaborationStep(
            step_id="s1", agent_id="chat-agent", action="decide"
        )
        assert step.on_failure == "abort"
        assert step.skill_id == ""
        assert step.timeout_seconds == 30
        assert step.input_from is None
        assert step.output_to is None

    def test_shadow_run_result(self):
        result = ShadowRunResult(
            pattern_id="pat_abc",
            trigger_event_id="evt_123",
            total_duration_ms=450,
            steps=[{"step_id": "s1", "output": "ok"}],
        )
        assert result.pattern_id == "pat_abc"
        assert isinstance(result.timestamp, datetime)
        assert result.total_duration_ms == 450

    def test_pattern_status_enum_values(self):
        assert PatternStatus.PROPOSED.value == "proposed"
        assert PatternStatus.SHADOW.value == "shadow"
        assert PatternStatus.ACTIVE.value == "active"
        assert PatternStatus.RETIRED.value == "retired"


# ── PatternStore Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPatternStore:
    async def test_save_and_retrieve(self, db_session):
        store = PatternStore(db_session)
        pattern = _make_pattern()

        row = await store.save_pattern(pattern)
        assert row.pattern_id == pattern.pattern_id
        assert row.name == "Risk Escalation"

        fetched = await store.get_pattern(pattern.pattern_id)
        assert fetched is not None
        assert fetched.pattern_id == pattern.pattern_id
        assert fetched.status == "proposed"
        assert len(fetched.steps) == 2

    async def test_get_nonexistent_returns_none(self, db_session):
        store = PatternStore(db_session)
        result = await store.get_pattern("pat_nonexistent")
        assert result is None

    async def test_find_matching_by_event_and_status(self, db_session):
        store = PatternStore(db_session)
        p1 = _make_pattern(trigger_event="risk.detected", status=PatternStatus.ACTIVE)
        p2 = _make_pattern(
            trigger_event="risk.detected", status=PatternStatus.PROPOSED
        )
        p3 = _make_pattern(trigger_event="task.created", status=PatternStatus.ACTIVE)
        await store.save_pattern(p1)
        await store.save_pattern(p2)
        await store.save_pattern(p3)

        matches = await store.find_matching("risk.detected", "active")
        assert len(matches) == 1
        assert matches[0].pattern_id == p1.pattern_id

    async def test_update_status(self, db_session):
        store = PatternStore(db_session)
        pattern = _make_pattern()
        await store.save_pattern(pattern)

        await store.update_status(pattern.pattern_id, PatternStatus.SHADOW)

        fetched = await store.get_pattern(pattern.pattern_id)
        assert fetched is not None
        assert fetched.status == "shadow"

    async def test_add_shadow_result(self, db_session):
        store = PatternStore(db_session)
        pattern = _make_pattern()
        await store.save_pattern(pattern)

        result1 = {"duration_ms": 100, "success": True}
        result2 = {"duration_ms": 200, "success": False}
        await store.add_shadow_result(pattern.pattern_id, result1)
        await store.add_shadow_result(pattern.pattern_id, result2)

        # Refresh to see the updated value
        db_session.expire_all()
        fetched = await store.get_pattern(pattern.pattern_id)
        assert fetched is not None
        assert len(fetched.shadow_results) == 2
        assert fetched.shadow_results[0]["duration_ms"] == 100
        assert fetched.shadow_results[1]["success"] is False

    async def test_approve_pattern(self, db_session):
        store = PatternStore(db_session)
        pattern = _make_pattern(status=PatternStatus.SHADOW)
        await store.save_pattern(pattern)

        await store.approve_pattern(pattern.pattern_id, approved_by="user-alice")

        db_session.expire_all()
        fetched = await store.get_pattern(pattern.pattern_id)
        assert fetched is not None
        assert fetched.status == "active"
        assert fetched.human_approval is True
        assert fetched.approved_by == "user-alice"
        assert fetched.approved_at is not None

    async def test_get_all_patterns(self, db_session):
        store = PatternStore(db_session)
        await store.save_pattern(
            _make_pattern(status=PatternStatus.ACTIVE, trigger_event="a.b")
        )
        await store.save_pattern(
            _make_pattern(status=PatternStatus.PROPOSED, trigger_event="c.d")
        )
        await store.save_pattern(
            _make_pattern(status=PatternStatus.ACTIVE, trigger_event="e.f")
        )

        all_rows = await store.get_all_patterns()
        assert len(all_rows) == 3

        active_rows = await store.get_all_patterns(status="active")
        assert len(active_rows) == 2

    async def test_add_shadow_result_nonexistent_raises(self, db_session):
        store = PatternStore(db_session)
        with pytest.raises(ValueError, match="not found"):
            await store.add_shadow_result("pat_missing", {"x": 1})
