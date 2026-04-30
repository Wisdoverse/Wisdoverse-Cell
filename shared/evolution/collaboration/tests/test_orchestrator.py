"""
Tests for CollaborationOrchestrator — event routing to active + shadow patterns.

Covers:
1. Routes event to matching active pattern, returns output events
2. Ignores events that don't match any pattern
3. Condition evaluation filters patterns (condition False = skip)
4. Shadow patterns run in background (verify shadow_runner.run_shadow called)
5. Multiple active patterns can match same event (results combined)
6. No patterns → returns empty list
7. Pattern execution error doesn't crash (logged, continues to next)
8. Active + shadow patterns both match same event (both processed)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.evolution.collaboration.models import (
    CollaborationPattern,
    CollaborationStep,
    PatternStatus,
    ShadowRunResult,
)
from shared.evolution.collaboration.orchestrator import CollaborationOrchestrator
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event

# ---------------------------------------------------------------------------
# Fake agents
# ---------------------------------------------------------------------------


class SuccessAgent(BaseAgent):
    """Returns one output event per invocation."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Success {agent_id}")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("test.done", payload={"from": self.agent_id})]

    async def handle_request(self, request: dict) -> dict:
        return {}


class ErrorAgent(BaseAgent):
    """Always raises an exception."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Error {agent_id}")

    async def handle_event(self, event: Event) -> list[Event]:
        raise RuntimeError("agent exploded")

    async def handle_request(self, request: dict) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(event_type: str = "order.created") -> Event:
    return Event.create(event_type=event_type, source_agent="test", payload={"x": 1})


def make_step(
    step_id: str,
    agent_id: str,
    *,
    on_failure: str = "abort",
    output_to: str | None = None,
) -> CollaborationStep:
    return CollaborationStep(
        step_id=step_id,
        agent_id=agent_id,
        action="analyze",
        on_failure=on_failure,
        output_to=output_to,
        timeout_seconds=5,
    )


def make_db_row(
    pattern_id: str,
    trigger_event: str,
    status: str,
    steps: list[CollaborationStep] | None = None,
    trigger_condition: str | None = None,
) -> MagicMock:
    """Simulate a SQLAlchemy ORM row (non-Pydantic object)."""
    row = MagicMock()
    row.pattern_id = pattern_id
    row.name = f"Pattern {pattern_id}"
    row.status = status
    row.trigger_event = trigger_event
    row.trigger_condition = trigger_condition
    row.steps = [s.model_dump() for s in (steps or [])]
    return row


def make_pattern(
    pattern_id: str,
    trigger_event: str,
    status: PatternStatus,
    steps: list[CollaborationStep] | None = None,
    trigger_condition: str | None = None,
) -> CollaborationPattern:
    return CollaborationPattern(
        pattern_id=pattern_id,
        name=f"Pattern {pattern_id}",
        status=status,
        trigger_event=trigger_event,
        trigger_condition=trigger_condition,
        steps=steps or [],
    )


def make_shadow_result(pattern_id: str, event_id: str) -> ShadowRunResult:
    return ShadowRunResult(
        pattern_id=pattern_id,
        trigger_event_id=event_id,
        steps=[],
        total_duration_ms=10,
    )


def build_orchestrator(
    active_rows: list | None = None,
    shadow_rows: list | None = None,
    condition_result: bool = True,
    agents: dict | None = None,
) -> tuple[CollaborationOrchestrator, AsyncMock, MagicMock, AsyncMock]:
    """
    Build an orchestrator with mocked dependencies.

    Returns (orchestrator, mock_store, mock_condition, mock_shadow_runner).
    """
    mock_store = AsyncMock()

    # find_matching returns active_rows or shadow_rows depending on status argument
    active_rows = active_rows or []
    shadow_rows = shadow_rows or []

    async def find_matching_side_effect(event_type: str, status: str):
        if status == PatternStatus.ACTIVE.value:
            return active_rows
        if status == PatternStatus.SHADOW.value:
            return shadow_rows
        return []

    mock_store.find_matching.side_effect = find_matching_side_effect
    mock_store.add_shadow_result = AsyncMock()

    mock_condition = MagicMock()
    mock_condition.evaluate.return_value = condition_result

    mock_shadow_runner = AsyncMock()

    orchestrator = CollaborationOrchestrator(
        pattern_store=mock_store,
        condition_evaluator=mock_condition,
        shadow_runner=mock_shadow_runner,
        agent_registry=agents or {},
    )
    return orchestrator, mock_store, mock_condition, mock_shadow_runner


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCollaborationOrchestrator:

    # 1. Routes event to matching active pattern, returns output events
    async def test_active_pattern_returns_output_events(self):
        agent = SuccessAgent("agent-a")
        step = make_step("s1", "agent-a")
        row = make_db_row("pat-1", "order.created", "active", [step])

        orchestrator, _, _, _ = build_orchestrator(
            active_rows=[row],
            agents={"agent-a": agent},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.done"
        assert results[0].payload["from"] == "agent-a"

    # 2. Ignores events that don't match any pattern
    async def test_no_matching_patterns_returns_empty(self):
        orchestrator, mock_store, _, _ = build_orchestrator(
            active_rows=[],
            shadow_rows=[],
        )

        event = make_event("unknown.event")
        results = await orchestrator.on_event(event)

        assert results == []
        mock_store.find_matching.assert_called()

    # 3. Condition evaluation filters patterns (condition False = skip)
    async def test_false_condition_skips_pattern(self):
        agent = SuccessAgent("agent-a")
        step = make_step("s1", "agent-a")
        row = make_db_row("pat-1", "order.created", "active", [step], "payload.x > 100")

        orchestrator, _, mock_condition, _ = build_orchestrator(
            active_rows=[row],
            condition_result=False,
            agents={"agent-a": agent},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        # Condition returned False → pattern should be skipped
        assert results == []
        mock_condition.evaluate.assert_called_once()

    # 4. Shadow patterns run in background via ShadowRunner
    async def test_shadow_patterns_trigger_shadow_runner(self):
        step = make_step("s1", "agent-a")
        shadow_row = make_db_row("pat-shadow", "order.created", "shadow", [step])
        shadow_result = make_shadow_result("pat-shadow", "evt-1")

        mock_store = AsyncMock()

        async def find_matching_side_effect(event_type: str, status: str):
            if status == PatternStatus.ACTIVE.value:
                return []
            if status == PatternStatus.SHADOW.value:
                return [shadow_row]
            return []

        mock_store.find_matching.side_effect = find_matching_side_effect
        mock_store.add_shadow_result = AsyncMock()

        mock_condition = MagicMock()
        mock_condition.evaluate.return_value = True

        mock_shadow_runner = AsyncMock()
        mock_shadow_runner.run_shadow.return_value = shadow_result

        orchestrator = CollaborationOrchestrator(
            pattern_store=mock_store,
            condition_evaluator=mock_condition,
            shadow_runner=mock_shadow_runner,
            agent_registry={},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        # Active path returns no results
        assert results == []

        # Give background tasks a chance to complete
        await asyncio.sleep(0)
        # Drain remaining tasks
        pending = list(orchestrator._background_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        mock_shadow_runner.run_shadow.assert_called_once()
        mock_store.add_shadow_result.assert_called_once_with(
            "pat-shadow", shadow_result.model_dump(mode="json")
        )

    # 5. Multiple active patterns can match same event (results combined)
    async def test_multiple_active_patterns_results_combined(self):
        agent_a = SuccessAgent("agent-a")
        agent_b = SuccessAgent("agent-b")

        step_a = make_step("s1", "agent-a")
        step_b = make_step("s1", "agent-b")

        row_a = make_db_row("pat-1", "order.created", "active", [step_a])
        row_b = make_db_row("pat-2", "order.created", "active", [step_b])

        orchestrator, _, _, _ = build_orchestrator(
            active_rows=[row_a, row_b],
            agents={"agent-a": agent_a, "agent-b": agent_b},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        # Both patterns run → 2 output events
        assert len(results) == 2
        from_agents = {r.payload["from"] for r in results}
        assert from_agents == {"agent-a", "agent-b"}

    # 6. No patterns → returns empty list
    async def test_no_patterns_returns_empty_list(self):
        orchestrator, _, _, _ = build_orchestrator(
            active_rows=[],
            shadow_rows=[],
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        assert results == []

    # 7. Pattern execution error doesn't crash (logged, continues to next)
    async def test_active_pattern_error_does_not_crash_continues_to_next(self):
        error_agent = ErrorAgent("error-agent")
        success_agent = SuccessAgent("success-agent")

        step_err = make_step("s1", "error-agent")
        step_ok = make_step("s1", "success-agent")

        row_err = make_db_row("pat-err", "order.created", "active", [step_err])
        row_ok = make_db_row("pat-ok", "order.created", "active", [step_ok])

        orchestrator, _, _, _ = build_orchestrator(
            active_rows=[row_err, row_ok],
            agents={
                "error-agent": error_agent,
                "success-agent": success_agent,
            },
        )

        event = make_event("order.created")
        # Should not raise
        results = await orchestrator.on_event(event)

        # Error pattern fails but success pattern still runs
        assert len(results) == 1
        assert results[0].payload["from"] == "success-agent"

    # 8. Active + shadow patterns both match same event (both processed)
    async def test_active_and_shadow_both_processed(self):
        agent_a = SuccessAgent("agent-a")
        step_a = make_step("s1", "agent-a")
        active_row = make_db_row("pat-active", "order.created", "active", [step_a])
        shadow_row = make_db_row("pat-shadow", "order.created", "shadow", [])
        shadow_result = make_shadow_result("pat-shadow", "evt-x")

        mock_store = AsyncMock()

        async def find_matching_side_effect(event_type: str, status: str):
            if status == PatternStatus.ACTIVE.value:
                return [active_row]
            if status == PatternStatus.SHADOW.value:
                return [shadow_row]
            return []

        mock_store.find_matching.side_effect = find_matching_side_effect
        mock_store.add_shadow_result = AsyncMock()

        mock_condition = MagicMock()
        mock_condition.evaluate.return_value = True

        mock_shadow_runner = AsyncMock()
        mock_shadow_runner.run_shadow.return_value = shadow_result

        orchestrator = CollaborationOrchestrator(
            pattern_store=mock_store,
            condition_evaluator=mock_condition,
            shadow_runner=mock_shadow_runner,
            agent_registry={"agent-a": agent_a},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        # Active path returned output
        assert len(results) == 1
        assert results[0].event_type == "test.done"

        # Drain background tasks
        pending = list(orchestrator._background_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # Shadow path was also triggered
        mock_shadow_runner.run_shadow.assert_called_once()

    # 9. Condition True → pattern is executed
    async def test_true_condition_allows_pattern(self):
        agent = SuccessAgent("agent-a")
        step = make_step("s1", "agent-a")
        row = make_db_row("pat-1", "order.created", "active", [step], "payload.x == 1")

        orchestrator, _, mock_condition, _ = build_orchestrator(
            active_rows=[row],
            condition_result=True,
            agents={"agent-a": agent},
        )

        event = make_event("order.created")
        results = await orchestrator.on_event(event)

        assert len(results) == 1
        mock_condition.evaluate.assert_called_once_with(
            "payload.x == 1", {"payload": event.payload}
        )

    # 10. Shadow condition False → shadow runner NOT called
    async def test_false_condition_skips_shadow_pattern(self):
        step = make_step("s1", "agent-a")
        shadow_row = make_db_row("pat-shadow", "order.created", "shadow", [step])

        mock_store = AsyncMock()

        async def find_matching_side_effect(event_type: str, status: str):
            if status == PatternStatus.ACTIVE.value:
                return []
            return [shadow_row]

        mock_store.find_matching.side_effect = find_matching_side_effect
        mock_store.add_shadow_result = AsyncMock()

        mock_condition = MagicMock()
        mock_condition.evaluate.return_value = False  # condition fails

        mock_shadow_runner = AsyncMock()

        orchestrator = CollaborationOrchestrator(
            pattern_store=mock_store,
            condition_evaluator=mock_condition,
            shadow_runner=mock_shadow_runner,
            agent_registry={},
        )

        event = make_event("order.created")
        await orchestrator.on_event(event)

        # Shadow runner must not be called because condition was False
        mock_shadow_runner.run_shadow.assert_not_called()
