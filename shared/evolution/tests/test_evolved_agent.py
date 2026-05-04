"""
Tests for EvolvedAgent wrapper.

Tests cover:
- Passes through successful events (returns correct result)
- Passes through failures (re-raises exception)
- Bypasses evolution when kill switch disabled (still returns correct result)
- Delegates properties (agent_id, agent_name, subscribed_events)
- isinstance(evolved, BaseAgent) returns True
- Delegates handle_request, startup, shutdown
- Trace persistence failure does not crash main flow
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.evolution.evolved_agent import EvolvedAgent
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event

# ── Helpers ────────────────────────────────────────────────────────────────


class FakeAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="test-agent",
            agent_name="Test Agent",
            subscribed_events=["test.event"],
            published_events=["test.completed"],
            a2a_enabled=False,
            mcp_enabled=False,
        )

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("test.completed", payload={"ok": True})]

    async def handle_request(self, request: dict) -> dict:
        return {"status": "ok"}


class FailingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="fail-agent",
            agent_name="Failing Agent",
            subscribed_events=["test.event"],
        )

    async def handle_event(self, event: Event) -> list[Event]:
        raise ValueError("boom")

    async def handle_request(self, request: dict) -> dict:
        return {}


def make_event() -> Event:
    return Event.create(
        event_type="test.event",
        source_agent="test-source",
        payload={"key": "value"},
    )


def make_kill_switch(enabled: bool = True) -> AsyncMock:
    ks = AsyncMock()
    ks.is_enabled = AsyncMock(return_value=enabled)
    return ks


def make_db_manager() -> MagicMock:
    session_ctx = AsyncMock()
    session_ctx.__aenter__ = AsyncMock(return_value=AsyncMock())
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.session = MagicMock(return_value=session_ctx)
    return db


# ── Tests ──────────────────────────────────────────────────────────────────


class TestEvolvedAgentIsBaseAgent:
    def test_isinstance_base_agent(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        assert isinstance(evolved, BaseAgent)


class TestEvolvedAgentDelegation:
    def test_delegates_agent_id(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        assert evolved.agent_id == "test-agent"

    def test_delegates_agent_name(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        assert evolved.agent_name == "Test Agent"

    def test_delegates_subscribed_events(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        assert evolved.subscribed_events == ["test.event"]

    def test_delegates_published_events(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        assert evolved.published_events == ["test.completed"]

    @pytest.mark.asyncio
    async def test_delegates_handle_request(self):
        agent = FakeAgent()
        evolved = EvolvedAgent(agent)
        result = await evolved.handle_request({"q": "hello"})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_delegates_startup(self):
        agent = FakeAgent()
        agent.startup = AsyncMock()
        evolved = EvolvedAgent(agent)
        await evolved.startup()
        agent.startup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delegates_shutdown(self):
        agent = FakeAgent()
        agent.shutdown = AsyncMock()
        evolved = EvolvedAgent(agent)
        await evolved.shutdown()
        agent.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delegates_health_check(self):
        agent = FakeAgent()
        agent.health_check = AsyncMock(return_value={"database": True})
        evolved = EvolvedAgent(agent)
        result = await evolved.health_check()
        assert result == {"database": True}
        agent.health_check.assert_awaited_once()


class TestEvolvedAgentHandleEvent:
    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_passthrough_success(self, mock_settings):
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.enabled = True
        agent = FakeAgent()
        ks = make_kill_switch(enabled=True)
        db = make_db_manager()
        evolved = EvolvedAgent(agent, kill_switch=ks, db_manager=db)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"
        assert results[0].payload == {"ok": True}

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_passthrough_failure_reraises(self, mock_settings):
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.enabled = True
        agent = FailingAgent()
        ks = make_kill_switch(enabled=True)
        db = make_db_manager()
        evolved = EvolvedAgent(agent, kill_switch=ks, db_manager=db)

        event = make_event()
        with pytest.raises(ValueError, match="boom"):
            await evolved.handle_event(event)

    @pytest.mark.asyncio
    async def test_bypass_when_kill_switch_disabled(self):
        agent = FakeAgent()
        ks = make_kill_switch(enabled=False)
        evolved = EvolvedAgent(agent, kill_switch=ks)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"

    @pytest.mark.asyncio
    async def test_bypass_when_no_kill_switch(self):
        """When no kill_switch is provided, tracing still works."""
        agent = FakeAgent()
        db = make_db_manager()
        evolved = EvolvedAgent(agent, db_manager=db)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_sampling_bypass(self, mock_settings):
        """When sampling rate is 0, events pass through without tracing."""
        mock_settings.trace_sampling_rate = 0.0
        mock_settings.enabled = True
        agent = FakeAgent()
        ks = make_kill_switch(enabled=True)
        evolved = EvolvedAgent(agent, kill_switch=ks)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_trace_persist_failure_does_not_crash(self, mock_settings):
        """Trace persistence failure must not affect main flow."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.enabled = True

        agent = FakeAgent()
        ks = make_kill_switch(enabled=True)

        # db_manager.session() raises
        db = MagicMock()
        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        session_ctx.__aexit__ = AsyncMock(return_value=False)
        db.session = MagicMock(return_value=session_ctx)

        evolved = EvolvedAgent(agent, kill_switch=ks, db_manager=db)

        event = make_event()
        results = await evolved.handle_event(event)

        # Main flow still succeeds
        assert len(results) == 1
        assert results[0].event_type == "test.completed"

        # Give the background task time to complete
        await asyncio.sleep(0.05)


# ── Phase 2 Tests ─────────────────────────────────────────────────────────


def make_evaluator(score: float = 0.85) -> AsyncMock:
    evaluator = AsyncMock()
    evaluator.score_trace = AsyncMock(return_value=score)
    return evaluator


def make_canary_router() -> AsyncMock:
    router = AsyncMock()
    router.record_result = AsyncMock()
    return router


def make_skill_optimizer() -> MagicMock:
    optimizer = MagicMock()
    optimizer.increment_execution = MagicMock()
    optimizer.maybe_optimize = AsyncMock(return_value=False)
    return optimizer


class TestEvolvedAgentPhase2:
    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_evaluator_scores_trace(self, mock_settings):
        """When auto_optimize is True and evaluator is provided, score_trace is called."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.auto_optimize = True
        mock_settings.canary_enabled = False

        agent = FakeAgent()
        evaluator = make_evaluator(score=0.9)
        evolved = EvolvedAgent(agent, evaluator=evaluator)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        # Give the background task time to complete
        await asyncio.sleep(0.1)
        evaluator.score_trace.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_canary_records_result(self, mock_settings):
        """When canary_enabled is True and canary_router is provided, record_result is called."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.auto_optimize = True
        mock_settings.canary_enabled = True

        agent = FakeAgent()
        evaluator = make_evaluator(score=0.75)
        canary = make_canary_router()
        evolved = EvolvedAgent(agent, evaluator=evaluator, canary_router=canary)

        event = make_event()
        await evolved.handle_event(event)
        await asyncio.sleep(0.1)

        canary.record_result.assert_awaited_once()
        # Verify score from evaluator was passed
        call_args = canary.record_result.call_args
        assert call_args[0][3] == 0.75  # score arg

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_optimizer_triggered(self, mock_settings):
        """When auto_optimize is True and skill_optimizer is provided, increment + maybe_optimize called."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.auto_optimize = True
        mock_settings.canary_enabled = False

        agent = FakeAgent()
        optimizer = make_skill_optimizer()
        evolved = EvolvedAgent(agent, skill_optimizer=optimizer)

        event = make_event()
        await evolved.handle_event(event)
        await asyncio.sleep(0.1)

        optimizer.increment_execution.assert_called_once_with("test-agent", "")
        optimizer.maybe_optimize.assert_awaited_once_with("test-agent", "")

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_phase2_disabled_by_default(self, mock_settings):
        """When auto_optimize=False and canary_enabled=False, no Phase 2 hooks are called."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.auto_optimize = False
        mock_settings.canary_enabled = False

        agent = FakeAgent()
        evaluator = make_evaluator()
        canary = make_canary_router()
        optimizer = make_skill_optimizer()
        evolved = EvolvedAgent(
            agent,
            evaluator=evaluator,
            canary_router=canary,
            skill_optimizer=optimizer,
        )

        event = make_event()
        await evolved.handle_event(event)
        await asyncio.sleep(0.1)

        evaluator.score_trace.assert_not_awaited()
        canary.record_result.assert_not_awaited()
        optimizer.increment_execution.assert_not_called()
        optimizer.maybe_optimize.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_evaluator_error_doesnt_crash(self, mock_settings):
        """Evaluator raising an exception must not affect main flow."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.auto_optimize = True
        mock_settings.canary_enabled = False

        agent = FakeAgent()
        evaluator = AsyncMock()
        evaluator.score_trace = AsyncMock(side_effect=RuntimeError("LLM down"))
        evolved = EvolvedAgent(agent, evaluator=evaluator)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"
        await asyncio.sleep(0.1)
        # Evaluator was called but failed — main flow unaffected
        evaluator.score_trace.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("shared.evolution.evolved_agent.evolution_settings")
    async def test_all_phase1_tests_still_pass(self, mock_settings):
        """Verify Phase 1 behavior is preserved: success passthrough with db persistence."""
        mock_settings.trace_sampling_rate = 1.0
        mock_settings.enabled = True
        mock_settings.auto_optimize = False
        mock_settings.canary_enabled = False

        agent = FakeAgent()
        ks = make_kill_switch(enabled=True)
        db = make_db_manager()
        evolved = EvolvedAgent(agent, kill_switch=ks, db_manager=db)

        event = make_event()
        results = await evolved.handle_event(event)

        assert len(results) == 1
        assert results[0].event_type == "test.completed"
        assert results[0].payload == {"ok": True}
