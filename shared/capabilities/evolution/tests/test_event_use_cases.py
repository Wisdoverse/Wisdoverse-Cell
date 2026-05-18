from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared.capabilities.evolution.core.event_use_cases import EvolutionEventUseCase
from shared.schemas.event import Event, EventTypes


class _Factory:
    def create_event(
        self,
        event_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> Event:
        return Event.create(
            event_type=event_type,
            source_agent="evolution-module",
            payload=payload,
            trace_id=trace_id,
        )


class _Step:
    def model_dump(self):
        return {"agent": "pjm-agent", "action": "decompose"}


def _use_case(
    *,
    analyzer=None,
    attach=None,
    approval_service=None,
    approval_gateway=None,
    collaboration_enabled=False,
    collaboration_seeds=None,
) -> EvolutionEventUseCase:
    if analyzer is None:
        analyzer = AsyncMock()
        analyzer.analyze = AsyncMock(return_value=[])
    if attach is None:
        attach = AsyncMock(side_effect=lambda proposal, **_: proposal)
    if approval_service is None:
        approval_service = AsyncMock()
        approval_service.approve_for_sensitive_action = AsyncMock()
        approval_service.reject_for_sensitive_action = AsyncMock()
    return EvolutionEventUseCase(
        analyzer=analyzer,
        attach_proposal_approval=attach,
        event_factory=_Factory(),
        approval_service=approval_service,
        approval_gateway=approval_gateway,
        collaboration_enabled=collaboration_enabled,
        collaboration_seeds=collaboration_seeds,
    )


@pytest.mark.asyncio
async def test_cycle_triggered_emits_skill_proposal_events_with_trace() -> None:
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(
        return_value=[{"operation": "add_skill", "target_agent": "pjm-agent"}]
    )
    attach = AsyncMock(
        side_effect=lambda proposal, **_: {
            **proposal,
            "control_plane_approval_id": "appr_evo_1",
        }
    )

    result = await _use_case(analyzer=analyzer, attach=attach).handle(
        Event.create(
            event_type=EventTypes.EVOLUTION_CYCLE_TRIGGERED,
            source_agent="scheduler",
            payload={"days": 3},
            trace_id="trace-evo",
        )
    )

    analyzer.analyze.assert_awaited_once_with(3)
    attach.assert_awaited_once()
    assert len(result) == 1
    assert result[0].event_type == EventTypes.EVOLUTION_SKILL_PROPOSED
    assert result[0].source_agent == "evolution-module"
    assert result[0].metadata.trace_id == "trace-evo"
    assert result[0].payload["control_plane_approval_id"] == "appr_evo_1"


@pytest.mark.asyncio
async def test_cycle_triggered_can_emit_collaboration_pattern_events() -> None:
    seed = SimpleNamespace(
        pattern_id="pat_1",
        name="Daily handoff",
        trigger_event="sync.completed",
        steps=[_Step()],
    )
    attach = AsyncMock(side_effect=lambda proposal, **_: proposal)

    result = await _use_case(
        attach=attach,
        collaboration_enabled=True,
        collaboration_seeds=[seed],
    ).handle(
        Event.create(
            event_type=EventTypes.EVOLUTION_CYCLE_TRIGGERED,
            source_agent="scheduler",
            payload={"days": 7},
            trace_id="trace-pattern",
        )
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.EVOLUTION_PATTERN_PROPOSED
    assert result[0].metadata.trace_id == "trace-pattern"
    assert result[0].payload["pattern_id"] == "pat_1"
    assert result[0].payload["steps"] == [{"agent": "pjm-agent", "action": "decompose"}]


@pytest.mark.asyncio
async def test_feedback_requires_resolver_for_control_plane_approval() -> None:
    approval_service = AsyncMock()
    approval_service.approve_for_sensitive_action = AsyncMock()

    result = await _use_case(approval_service=approval_service).handle(
        Event.create(
            event_type=EventTypes.EVOLUTION_HUMAN_FEEDBACK,
            source_agent="user",
            payload={"approved": True, "control_plane_approval_id": "appr_evo_1"},
        )
    )

    assert result == []
    approval_service.approve_for_sensitive_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_records_human_resolver_for_control_plane_approval() -> None:
    approval_service = AsyncMock()
    approval_service.approve_for_sensitive_action = AsyncMock()
    approval_service.reject_for_sensitive_action = AsyncMock()

    result = await _use_case(approval_service=approval_service).handle(
        Event.create(
            event_type=EventTypes.EVOLUTION_HUMAN_FEEDBACK,
            source_agent="user",
            payload={
                "approved": True,
                "control_plane_approval_id": "appr_evo_1",
                "user_id": "human:cto",
            },
        )
    )

    assert result == []
    approval_service.approve_for_sensitive_action.assert_awaited_once_with(
        "appr_evo_1",
        resolved_by="human:cto",
    )


@pytest.mark.asyncio
async def test_pattern_approval_processes_gateway_after_control_plane_approval() -> None:
    approval_service = AsyncMock()
    approval_service.approve_for_sensitive_action = AsyncMock()
    approval_gateway = AsyncMock()
    approval_gateway.process_approval = AsyncMock(return_value=True)

    result = await _use_case(
        approval_service=approval_service,
        approval_gateway=approval_gateway,
    ).handle(
        Event.create(
            event_type=EventTypes.EVOLUTION_PATTERN_APPROVED,
            source_agent="user",
            payload={
                "pattern_id": "pat_1",
                "approved": True,
                "control_plane_approval_id": "appr_evo_1",
                "user_id": "human:cto",
            },
        )
    )

    assert result == []
    approval_service.approve_for_sensitive_action.assert_awaited_once_with(
        "appr_evo_1",
        resolved_by="human:cto",
    )
    approval_gateway.process_approval.assert_awaited_once_with(
        pattern_id="pat_1",
        user_id="human:cto",
        approved=True,
    )


@pytest.mark.asyncio
async def test_unknown_event_returns_no_events() -> None:
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock()

    result = await _use_case(analyzer=analyzer).handle(
        Event.create(event_type="unknown.event", source_agent="test", payload={})
    )

    assert result == []
    analyzer.analyze.assert_not_awaited()
