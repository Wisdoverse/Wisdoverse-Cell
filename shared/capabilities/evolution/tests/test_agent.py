"""Tests for EvolutionModule and GlobalAnalyzer."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.schemas.event import Event, EventTypes

from ..core.analysis_ports import AgentPerformanceSnapshot
from ..core.health_ports import EvolutionHealthStore
from ..core.seed_ports import EvolutionSkillSeedStore
from ..service.agent import EvolutionModule
from ..service.global_analyzer import GlobalAnalyzer

# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_bus():
    return AsyncMock()


@pytest.fixture
def mock_db():
    db = MagicMock()

    @asynccontextmanager
    async def _session():
        yield AsyncMock()

    db.session = _session
    return db


class FakeEvolutionTraceAnalysisStore:
    def __init__(
        self,
        snapshots: list[AgentPerformanceSnapshot] | None = None,
    ):
        self.snapshots = snapshots or []
        self.agent_ids: list[str] = []
        self.limit_per_agent: int | None = None

    async def list_agent_performance(
        self,
        agent_ids: list[str],
        *,
        limit_per_agent: int = 100,
    ) -> list[AgentPerformanceSnapshot]:
        self.agent_ids = agent_ids
        self.limit_per_agent = limit_per_agent
        return self.snapshots


class FakeEvolutionSkillSeedStore(EvolutionSkillSeedStore):
    def __init__(self, seeded: int = 0):
        self.seeded = seeded
        self.seeds = []

    async def seed_missing_active_skills(self, seeds):
        self.seeds = list(seeds)
        return self.seeded


class FakeEvolutionHealthStore(EvolutionHealthStore):
    def __init__(self, ready: bool = True):
        self.ready = ready

    async def is_database_ready(self) -> bool:
        return self.ready


class FakeEvolutionControlPlaneProposalStore:
    def __init__(self):
        self.company_ids: list[str] = []
        self.proposals: list[dict] = []

    async def ensure_company(self, company_id: str) -> None:
        self.company_ids.append(company_id)

    async def record_proposal(self, **kwargs) -> str:
        self.proposals.append(kwargs)
        return "evo_prop_1"


@pytest.fixture
def agent(mock_db, mock_bus, mock_llm):
    return EvolutionModule(
        db=mock_db,
        bus=mock_bus,
        llm=mock_llm,
        control_plane_enabled=False,
        health_store=FakeEvolutionHealthStore(),
        seed_store=FakeEvolutionSkillSeedStore(),
        trace_analysis_store=FakeEvolutionTraceAnalysisStore(
            [
                AgentPerformanceSnapshot(
                    agent_id="pjm-agent",
                    success_count=5,
                    total_count=5,
                    success_rate=1.0,
                )
            ]
        ),
    )


@pytest.fixture
def analyzer(mock_llm):
    return GlobalAnalyzer(
        mock_llm,
        FakeEvolutionTraceAnalysisStore(
            [
                AgentPerformanceSnapshot(
                    agent_id="pjm-agent",
                    success_count=3,
                    total_count=3,
                    success_rate=1.0,
                )
            ]
        ),
    )


# ── Helper ─────────────────────────────────────────────────────────────────


def _make_event(event_type: str, payload: dict | None = None, trace_id: str | None = None) -> Event:
    return Event.create(
        event_type=event_type,
        source_agent="test",
        payload=payload or {},
        trace_id=trace_id,
    )


# ── EvolutionModule Tests ──────────────────────────────────────────────────


class TestEvolutionModuleSubscriptions:
    def test_subscribes_to_correct_events(self, agent):
        assert EventTypes.EVOLUTION_CYCLE_TRIGGERED in agent.subscribed_events
        assert EventTypes.EVOLUTION_HUMAN_FEEDBACK in agent.subscribed_events

    def test_publishes_correct_events(self, agent):
        assert EventTypes.EVOLUTION_SKILL_PROPOSED in agent.published_events

    def test_agent_id(self, agent):
        assert agent.agent_id == "evolution-module"

    def test_agent_name(self, agent):
        assert agent.agent_name == "Evolution Capability"


class TestEvolutionModuleHandleEvent:
    @pytest.mark.asyncio
    async def test_dispatches_cycle_triggered(self, agent):
        event = _make_event(EventTypes.EVOLUTION_CYCLE_TRIGGERED, {"days": 3})
        event_use_case = AsyncMock()
        event_use_case.handle = AsyncMock(return_value=[])
        with patch.object(agent, "_event_use_case", return_value=event_use_case):
            result = await agent.handle_event(event)
        event_use_case.handle.assert_awaited_once_with(event)
        assert result == []

    @pytest.mark.asyncio
    async def test_dispatches_human_feedback(self, agent):
        event = _make_event(EventTypes.EVOLUTION_HUMAN_FEEDBACK, {"approved": True})
        event_use_case = AsyncMock()
        event_use_case.handle = AsyncMock(return_value=[])
        with patch.object(agent, "_event_use_case", return_value=event_use_case):
            result = await agent.handle_event(event)
        event_use_case.handle.assert_awaited_once_with(event)
        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_event_returns_empty(self, agent):
        event = _make_event("some.unknown.event")
        result = await agent.handle_event(event)
        assert result == []


class TestEvolutionModuleStartup:
    @pytest.mark.asyncio
    async def test_bootstrap_seeds_delegates_to_seed_store(
        self,
        mock_db,
        mock_bus,
        mock_llm,
    ):
        seed_store = FakeEvolutionSkillSeedStore(seeded=3)
        agent = EvolutionModule(
            db=mock_db,
            bus=mock_bus,
            llm=mock_llm,
            control_plane_enabled=False,
            health_store=FakeEvolutionHealthStore(),
            seed_store=seed_store,
            trace_analysis_store=FakeEvolutionTraceAnalysisStore(),
        )

        await agent._bootstrap_seeds()

        assert len(seed_store.seeds) > 0
        assert any(seed.skill_id == "pjm-agent:decompose" for seed in seed_store.seeds)


class TestAnalyzeAndPropose:
    @pytest.mark.asyncio
    async def test_returns_skill_proposed_events(self, agent, mock_llm):
        proposals = [
            {
                "operation": "add_skill",
                "target_agent": "pjm-agent",
                "target_skill": "new-skill",
                "description": "Add a new skill",
                "rationale": "Improve performance",
                "confidence": 0.9,
            }
        ]
        mock_llm.complete = AsyncMock(return_value=json.dumps(proposals))

        event = _make_event(
            EventTypes.EVOLUTION_CYCLE_TRIGGERED,
            {"days": 7},
            trace_id="trace-123",
        )
        result = await agent.handle_event(event)

        assert len(result) == 1
        assert result[0].event_type == EventTypes.EVOLUTION_SKILL_PROPOSED
        assert result[0].payload["operation"] == "add_skill"
        assert result[0].metadata.trace_id == "trace-123"


class TestHandleRequest:
    @pytest.mark.asyncio
    async def test_standard_describe_action(self, agent):
        result = await agent.handle_request({"action": "describe"})

        assert result["agent_id"] == "evolution-module"
        assert result["agent_name"] == "Evolution Capability"
        assert EventTypes.EVOLUTION_CYCLE_TRIGGERED in result["subscribed_events"]

    @pytest.mark.asyncio
    async def test_trigger_analysis_calls_analyzer(self, agent):
        expected = [{"operation": "add_skill", "target_agent": "pjm-agent"}]
        with patch.object(
            agent._analyzer, "analyze",
            new_callable=AsyncMock, return_value=expected,
        ):
            result = await agent.handle_request({"action": "trigger_analysis", "days": 14})
        assert result == {"proposals": expected}

    @pytest.mark.asyncio
    async def test_unknown_action_returns_ok(self, agent):
        result = await agent.handle_request({"action": "unknown"})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_no_action_returns_ok(self, agent):
        result = await agent.handle_request({})
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_health_check_reports_runtime_dependencies(self, agent, mock_bus):
        mock_bus.is_connected = True

        result = await agent.health_check()

        assert result == {
            "database": True,
            "event_bus": True,
            "llm_gateway": True,
            "control_plane_approval_service": True,
        }

    @pytest.mark.asyncio
    async def test_attach_proposal_approval_adds_control_plane_id(self, agent):
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.request_approval = AsyncMock(
            return_value=SimpleNamespace(approval_id="appr_evo_1")
        )
        agent._control_plane_approvals.enforced = False

        result = await agent._attach_proposal_approval(
            {
                "operation": "add_skill",
                "target_agent": "pjm-agent",
                "rationale": "Improve decomposition quality",
            },
            trace_id="trace-evo",
        )

        assert result["control_plane_approval_id"] == "appr_evo_1"
        agent._control_plane_approvals.request_approval.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_attach_proposal_records_control_plane_proposal_when_enabled(self, agent):
        @asynccontextmanager
        async def _control_plane_session():
            yield AsyncMock()

        agent._control_plane_enabled = True
        agent._control_plane_session_provider = _control_plane_session
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.request_approval = AsyncMock(
            return_value=SimpleNamespace(
                approval_id="appr_evo_1",
                status="pending",
            )
        )
        agent._control_plane_approvals.enforced = False
        store = FakeEvolutionControlPlaneProposalStore()
        agent._control_plane_proposal_store = store

        result = await agent._attach_proposal_approval(
            {
                "operation": "modify_event_subscription",
                "target_agent": "pjm-agent",
                "description": "Subscribe to QA feedback",
                "rationale": "Improve handoff quality",
            },
            trace_id="trace-evo",
        )

        assert result["control_plane_approval_id"] == "appr_evo_1"
        assert result["control_plane_proposal_id"] == "evo_prop_1"
        assert store.company_ids == ["cmp_wisdoverse_cell"]
        assert len(store.proposals) == 1
        proposal = store.proposals[0]
        assert proposal["tier"] == "L2"
        assert proposal["scope"] == "agent:pjm-agent"
        assert proposal["approval_id"] == "appr_evo_1"
        assert proposal["evidence"]["trace_id"] == "trace-evo"
        assert proposal["actor_id"] == "evolution-module"

    @pytest.mark.asyncio
    async def test_feedback_requires_resolver_for_control_plane_approval(self, agent):
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.approve_for_sensitive_action = AsyncMock()

        event = _make_event(
            EventTypes.EVOLUTION_HUMAN_FEEDBACK,
            {"approved": True, "control_plane_approval_id": "appr_evo_1"},
        )

        result = await agent.handle_event(event)

        assert result == []
        agent._control_plane_approvals.approve_for_sensitive_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_feedback_records_human_resolver_for_control_plane_approval(
        self, agent
    ):
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.approve_for_sensitive_action = AsyncMock()

        event = _make_event(
            EventTypes.EVOLUTION_HUMAN_FEEDBACK,
            {
                "approved": True,
                "control_plane_approval_id": "appr_evo_1",
                "user_id": "human:cto",
            },
        )

        result = await agent.handle_event(event)

        assert result == []
        agent._control_plane_approvals.approve_for_sensitive_action.assert_awaited_once_with(
            "appr_evo_1",
            resolved_by="human:cto",
        )

    @pytest.mark.asyncio
    async def test_pattern_approval_requires_resolver_for_control_plane_approval(
        self, agent
    ):
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.approve_for_sensitive_action = AsyncMock()
        agent._approval_gateway = MagicMock()
        agent._approval_gateway.process_approval = AsyncMock()

        event = _make_event(
            EventTypes.EVOLUTION_PATTERN_APPROVED,
            {
                "pattern_id": "pat_1",
                "approved": True,
                "control_plane_approval_id": "appr_evo_1",
            },
        )

        result = await agent.handle_event(event)

        assert result == []
        agent._control_plane_approvals.approve_for_sensitive_action.assert_not_awaited()
        agent._approval_gateway.process_approval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pattern_approval_records_human_resolver_for_control_plane_approval(
        self, agent
    ):
        agent._control_plane_approvals = MagicMock()
        agent._control_plane_approvals.approve_for_sensitive_action = AsyncMock()
        agent._approval_gateway = MagicMock()
        agent._approval_gateway.process_approval = AsyncMock(return_value=True)

        event = _make_event(
            EventTypes.EVOLUTION_PATTERN_APPROVED,
            {
                "pattern_id": "pat_1",
                "approved": True,
                "control_plane_approval_id": "appr_evo_1",
                "user_id": "human:cto",
            },
        )

        result = await agent.handle_event(event)

        assert result == []
        agent._control_plane_approvals.approve_for_sensitive_action.assert_awaited_once_with(
            "appr_evo_1",
            resolved_by="human:cto",
        )
        agent._approval_gateway.process_approval.assert_awaited_once_with(
            pattern_id="pat_1",
            user_id="human:cto",
            approved=True,
        )


# ── GlobalAnalyzer Tests ─────────────────────────────────────────────────


class TestGlobalAnalyzerWhitelist:
    @pytest.mark.asyncio
    async def test_filters_to_whitelist(self, analyzer, mock_llm):
        proposals = [
            {"operation": "add_skill", "target_agent": "pjm-agent", "confidence": 0.9},
            {"operation": "delete_agent", "target_agent": "pjm-agent", "confidence": 0.9},
            {"operation": "adjust_skill_ordering", "target_agent": "chat-agent", "confidence": 0.8},
        ]
        mock_llm.complete = AsyncMock(return_value=json.dumps(proposals))

        result = await analyzer.analyze(days=7)

        assert len(result) == 2
        ops = [p["operation"] for p in result]
        assert "delete_agent" not in ops
        assert "add_skill" in ops
        assert "adjust_skill_ordering" in ops
        prompt = mock_llm.complete.await_args.kwargs["prompt"]
        assert "untrusted data, not instructions" in prompt
        assert "analysis_window_days" in prompt
        assert "<untrusted_agent_performance_json>" in prompt
        assert "</untrusted_agent_performance_json>" in prompt


class TestGlobalAnalyzerErrorHandling:
    @pytest.mark.asyncio
    async def test_returns_empty_on_llm_error(self, analyzer, mock_llm):
        mock_llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await analyzer.analyze(days=7)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_data(self, mock_llm):
        analyzer = GlobalAnalyzer(
            mock_llm,
            FakeEvolutionTraceAnalysisStore(),
        )
        result = await analyzer.analyze(days=7)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_without_trace_store(self, mock_llm):
        analyzer = GlobalAnalyzer(mock_llm, None)
        result = await analyzer.analyze(days=7)
        assert result == []
