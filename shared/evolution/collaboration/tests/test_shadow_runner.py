"""
Tests for ShadowRunner — semaphore-limited parallel execution of collaboration patterns.

Covers:
- Multi-step success
- Timeout with abort
- Timeout with skip
- Agent not found with abort
- Agent not found with skip
- Error agent with abort
- Output chaining
- Semaphore limits concurrency to MAX_CONCURRENT_SHADOWS
- Returns valid ShadowRunResult
"""

import asyncio

import pytest

from shared.evolution.collaboration.models import (
    CollaborationPattern,
    CollaborationStep,
    ShadowRunResult,
)
from shared.evolution.collaboration.shadow_runner import ShadowRunner
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event

# ---------------------------------------------------------------------------
# Fake agents
# ---------------------------------------------------------------------------


class SuccessAgent(BaseAgent):
    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Test {agent_id}")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("test.done", payload={"from": self.agent_id})]

    async def handle_request(self, request: dict) -> dict:
        return {}


class SlowAgent(BaseAgent):
    """Always times out."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Slow {agent_id}")

    async def handle_event(self, event: Event) -> list[Event]:
        await asyncio.sleep(10)  # Will timeout
        return []

    async def handle_request(self, request: dict) -> dict:
        return {}


class ErrorAgent(BaseAgent):
    """Always raises an exception."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Error {agent_id}")

    async def handle_event(self, event: Event) -> list[Event]:
        raise RuntimeError("agent crashed")

    async def handle_request(self, request: dict) -> dict:
        return {}


class EchoAgent(BaseAgent):
    """Records the event it received for chaining verification."""

    def __init__(self, agent_id: str):
        super().__init__(agent_id=agent_id, agent_name=f"Echo {agent_id}")
        self.received_events: list[Event] = []

    async def handle_event(self, event: Event) -> list[Event]:
        self.received_events.append(event)
        return [self.create_event("test.echo", payload={"echoed": event.event_type})]

    async def handle_request(self, request: dict) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trigger() -> Event:
    return Event.create(event_type="trigger.test", source_agent="test", payload={})


def make_step(
    step_id: str,
    agent_id: str,
    *,
    on_failure: str = "abort",
    timeout_seconds: int = 30,
    output_to: str | None = None,
) -> CollaborationStep:
    return CollaborationStep(
        step_id=step_id,
        agent_id=agent_id,
        action="analyze",
        on_failure=on_failure,
        timeout_seconds=timeout_seconds,
        output_to=output_to,
    )


def make_pattern(steps: list[CollaborationStep]) -> CollaborationPattern:
    return CollaborationPattern(
        name="test-pattern",
        trigger_event="trigger.test",
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestShadowRunner:
    # 1. Multi-step success — all steps return success
    async def test_multi_step_success(self):
        agents = {
            "agent-a": SuccessAgent("agent-a"),
            "agent-b": SuccessAgent("agent-b"),
            "agent-c": SuccessAgent("agent-c"),
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "agent-a"),
                make_step("s2", "agent-b"),
                make_step("s3", "agent-c"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 3
        assert all(s["success"] for s in result.steps)
        assert result.steps[0]["step_id"] == "s1"
        assert result.steps[1]["step_id"] == "s2"
        assert result.steps[2]["step_id"] == "s3"

    # 2. Timeout on step with on_failure="abort" — stops execution
    async def test_timeout_abort_stops_execution(self):
        agents = {
            "slow": SlowAgent("slow"),
            "after": SuccessAgent("after"),
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "slow", on_failure="abort", timeout_seconds=1),
                make_step("s2", "after"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 1
        assert result.steps[0]["success"] is False
        assert result.steps[0]["error"] == "timeout"

    # 3. Timeout on step with on_failure="skip" — continues to next step
    async def test_timeout_skip_continues(self):
        agents = {
            "slow": SlowAgent("slow"),
            "after": SuccessAgent("after"),
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "slow", on_failure="skip", timeout_seconds=1),
                make_step("s2", "after"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 2
        assert result.steps[0]["success"] is False
        assert result.steps[0]["error"] == "timeout"
        assert result.steps[1]["success"] is True

    # 4. Agent not found with abort — stops
    async def test_agent_not_found_abort(self):
        agents: dict[str, BaseAgent] = {}
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "missing", on_failure="abort"),
                make_step("s2", "also-missing", on_failure="abort"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 1
        assert result.steps[0]["success"] is False
        assert "not found" in result.steps[0]["error"]

    # 5. Agent not found with skip — continues
    async def test_agent_not_found_skip(self):
        agents = {"agent-b": SuccessAgent("agent-b")}
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "missing", on_failure="skip"),
                make_step("s2", "agent-b"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 2
        assert result.steps[0]["success"] is False
        assert result.steps[1]["success"] is True

    # 6. Error agent with abort — stops
    async def test_error_agent_abort(self):
        agents = {
            "err": ErrorAgent("err"),
            "ok": SuccessAgent("ok"),
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "err", on_failure="abort"),
                make_step("s2", "ok"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 1
        assert result.steps[0]["success"] is False
        assert result.steps[0]["error"] == "agent crashed"

    # 7. Output chaining — step N output becomes step N+1 input
    async def test_output_chaining(self):
        echo_b = EchoAgent("agent-b")
        agents = {
            "agent-a": SuccessAgent("agent-a"),
            "agent-b": echo_b,
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "agent-a", output_to="agent-b"),
                make_step("s2", "agent-b"),
            ]
        )
        trigger = make_trigger()
        result = await runner.run_shadow(pattern, trigger)

        assert len(result.steps) == 2
        assert all(s["success"] for s in result.steps)
        # Step 2 received the output from step 1, not the original trigger
        assert len(echo_b.received_events) == 1
        assert echo_b.received_events[0].event_type == "test.done"

    # 8. Semaphore limits concurrency to MAX_CONCURRENT_SHADOWS
    async def test_semaphore_limits_concurrency(self):
        max_concurrent = ShadowRunner.MAX_CONCURRENT_SHADOWS
        concurrent_count = 0
        peak_concurrent = 0

        class CountingAgent(BaseAgent):
            def __init__(self_inner):
                super().__init__(agent_id="counting", agent_name="Counting")

            async def handle_event(self_inner, event: Event) -> list[Event]:
                nonlocal concurrent_count, peak_concurrent
                concurrent_count += 1
                peak_concurrent = max(peak_concurrent, concurrent_count)
                await asyncio.sleep(0.1)
                concurrent_count -= 1
                return []

            async def handle_request(self_inner, request: dict) -> dict:
                return {}

        agents = {"counting": CountingAgent()}
        runner = ShadowRunner(agents)
        pattern = make_pattern([make_step("s1", "counting")])

        # Launch more concurrent runs than the semaphore allows
        total_runs = max_concurrent + 2
        tasks = [
            asyncio.create_task(runner.run_shadow(pattern, make_trigger()))
            for _ in range(total_runs)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == total_runs
        assert peak_concurrent <= max_concurrent

    # 9. Returns valid ShadowRunResult
    async def test_returns_valid_shadow_run_result(self):
        agents = {"agent-a": SuccessAgent("agent-a")}
        runner = ShadowRunner(agents)
        pattern = make_pattern([make_step("s1", "agent-a")])
        trigger = make_trigger()

        result = await runner.run_shadow(pattern, trigger)

        assert isinstance(result, ShadowRunResult)
        assert result.pattern_id == pattern.pattern_id
        assert result.trigger_event_id == trigger.event_id
        assert result.total_duration_ms >= 0
        assert result.timestamp is not None

    # 10. Error agent with skip — continues to next step
    async def test_error_agent_skip_continues(self):
        agents = {
            "err": ErrorAgent("err"),
            "ok": SuccessAgent("ok"),
        }
        runner = ShadowRunner(agents)
        pattern = make_pattern(
            [
                make_step("s1", "err", on_failure="skip"),
                make_step("s2", "ok"),
            ]
        )
        result = await runner.run_shadow(pattern, make_trigger())

        assert len(result.steps) == 2
        assert result.steps[0]["success"] is False
        assert result.steps[1]["success"] is True

    # 11. Empty pattern — returns result with no steps
    async def test_empty_pattern(self):
        runner = ShadowRunner({})
        pattern = make_pattern([])
        result = await runner.run_shadow(pattern, make_trigger())

        assert isinstance(result, ShadowRunResult)
        assert result.steps == []
        assert result.total_duration_ms >= 0

    # 12. Output chaining — without output_to, trigger is preserved for next step
    async def test_no_output_to_preserves_trigger_input(self):
        """If output_to is None, the next step still uses the last current_input."""
        echo_b = EchoAgent("agent-b")
        agents = {
            "agent-a": SuccessAgent("agent-a"),
            "agent-b": echo_b,
        }
        runner = ShadowRunner(agents)
        # No output_to on step 1
        pattern = make_pattern(
            [
                make_step("s1", "agent-a"),
                make_step("s2", "agent-b"),
            ]
        )
        trigger = make_trigger()
        await runner.run_shadow(pattern, trigger)

        # agent-b should have received the original trigger (current_input not updated)
        assert echo_b.received_events[0].event_id == trigger.event_id
