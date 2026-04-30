"""
Integration test for the full L3 collaboration lifecycle.

Tests the complete flow: proposed -> shadow -> shadow runs -> approval -> active -> execution.
Uses in-memory SQLite and FakeAgent stubs — no external dependencies.
"""

import pytest
import pytest_asyncio

aiosqlite = pytest.importorskip("aiosqlite", reason="aiosqlite not installed")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.evolution.collaboration.approval_gateway import ApprovalGateway
from shared.evolution.collaboration.condition_evaluator import ConditionEvaluator
from shared.evolution.collaboration.models import (
    PatternStatus,
)
from shared.evolution.collaboration.orchestrator import CollaborationOrchestrator
from shared.evolution.collaboration.pattern_store import PatternStore
from shared.evolution.collaboration.seeds import COLLABORATION_SEEDS, RISK_REVIEW_V2
from shared.evolution.collaboration.shadow_runner import ShadowRunner
from shared.evolution.db.tables import evolution_metadata
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event

# ---------------------------------------------------------------------------
# Fake agents for testing
# ---------------------------------------------------------------------------


class FakeAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="analysis-agent", agent_name="Analysis")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("analysis.done", payload={"risk": "low"})]

    async def handle_request(self, request: dict) -> dict:
        return {}


class FakePMAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="pjm-agent", agent_name="PM")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("pm.review-done", payload={"approved": True})]

    async def handle_request(self, request: dict) -> dict:
        return {}


class FakeEvolutionAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="evolution-agent", agent_name="Evolution")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("evolution.decided", payload={"consensus": True})]

    async def handle_request(self, request: dict) -> dict:
        return {}


class FakeChatAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="chat-agent", agent_name="Chat")

    async def handle_event(self, event: Event) -> list[Event]:
        return [self.create_event("chat.escalated", payload={"notified": True})]

    async def handle_request(self, request: dict) -> dict:
        return {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(evolution_metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.run_sync(evolution_metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def agent_registry():
    return {
        "analysis-agent": FakeAnalysisAgent(),
        "pjm-agent": FakePMAgent(),
        "evolution-agent": FakeEvolutionAgent(),
        "chat-agent": FakeChatAgent(),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCollaborationLifecycle:
    async def test_full_lifecycle(self, db_session: AsyncSession, agent_registry):
        """Test: proposed -> shadow -> shadow runs -> approval -> active -> execution."""
        store = PatternStore(db_session)

        # 1. Save seed pattern as "proposed"
        seed = RISK_REVIEW_V2.model_copy()
        assert seed.status == PatternStatus.PROPOSED
        await store.save_pattern(seed)
        await db_session.commit()

        row = await store.get_pattern(seed.pattern_id)
        assert row is not None
        assert row.status == PatternStatus.PROPOSED.value

        # 2. Update to "shadow"
        await store.update_status(seed.pattern_id, PatternStatus.SHADOW)
        await db_session.commit()

        row = await store.get_pattern(seed.pattern_id)
        assert row.status == PatternStatus.SHADOW.value

        # 3. Create ShadowRunner and run shadow 20+ times
        shadow_runner = ShadowRunner(agent_registry)

        trigger_event = Event.create(
            event_type="sync.completed",
            source_agent="sync-agent",
            payload={"task_count": 5},
        )

        for _ in range(20):
            result = await shadow_runner.run_shadow(seed, trigger_event)
            await store.add_shadow_result(
                seed.pattern_id, result.model_dump(mode="json")
            )
            await db_session.commit()

        # 4. Verify shadow results accumulated
        row = await store.get_pattern(seed.pattern_id)
        assert len(row.shadow_results) == 20

        # 5. ApprovalGateway.maybe_request_approval -> True
        admin_user = "admin-001"
        gateway = ApprovalGateway(
            pattern_store=store,
            feishu_service=None,
            admin_chat_id="",
            admin_user_ids=[admin_user],
        )
        ready = await gateway.maybe_request_approval(seed.pattern_id)
        assert ready is True

        # 6. ApprovalGateway.process_approval -> pattern "active"
        processed = await gateway.process_approval(
            pattern_id=seed.pattern_id,
            user_id=admin_user,
            approved=True,
        )
        assert processed is True
        await db_session.commit()

        row = await store.get_pattern(seed.pattern_id)
        assert row.status == PatternStatus.ACTIVE.value
        assert row.human_approval is True
        assert row.approved_by == admin_user

        # 7. Orchestrator.on_event with matching event -> executes pattern
        condition_eval = ConditionEvaluator()
        orchestrator = CollaborationOrchestrator(
            pattern_store=store,
            condition_evaluator=condition_eval,
            shadow_runner=shadow_runner,
            agent_registry=agent_registry,
        )

        output_events = await orchestrator.on_event(trigger_event)

        # 8. Verify step chain produces output events
        assert len(output_events) > 0
        event_types = [e.event_type for e in output_events]
        assert "analysis.done" in event_types
        assert "pm.review-done" in event_types
        assert "evolution.decided" in event_types
        # escalate step also runs because on_failure="fallback_to:escalate" != "abort"
        assert "chat.escalated" in event_types

    async def test_approval_rejected_unauthorized_user(self, db_session: AsyncSession):
        """Unauthorized user cannot approve patterns."""
        store = PatternStore(db_session)
        seed = RISK_REVIEW_V2.model_copy()
        await store.save_pattern(seed)
        await db_session.commit()

        gateway = ApprovalGateway(
            pattern_store=store,
            admin_user_ids=["admin-001"],
        )
        result = await gateway.process_approval(
            pattern_id=seed.pattern_id,
            user_id="hacker-999",
            approved=True,
        )
        assert result is False

        row = await store.get_pattern(seed.pattern_id)
        assert row.status == PatternStatus.PROPOSED.value

    async def test_not_enough_shadow_runs(self, db_session: AsyncSession):
        """Approval not ready when insufficient shadow runs."""
        store = PatternStore(db_session)
        seed = RISK_REVIEW_V2.model_copy()
        await store.save_pattern(seed)
        await db_session.commit()

        gateway = ApprovalGateway(pattern_store=store)
        ready = await gateway.maybe_request_approval(seed.pattern_id)
        assert ready is False

    async def test_seed_patterns_exist(self):
        """Verify seed patterns are importable and well-formed."""
        assert len(COLLABORATION_SEEDS) >= 1
        seed = COLLABORATION_SEEDS[0]
        assert seed.pattern_id == "risk-review-v2"
        assert seed.status == PatternStatus.PROPOSED
        assert len(seed.steps) == 4
        step_ids = [s.step_id for s in seed.steps]
        assert step_ids == ["analyze", "review", "decide", "escalate"]
