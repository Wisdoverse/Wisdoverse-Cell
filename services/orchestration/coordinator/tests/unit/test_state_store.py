"""Tests for CoordinatorStateStore in-memory operations."""
from datetime import UTC, datetime

import pytest


def test_workflow_state_creation():
    from services.orchestration.coordinator.db.models import WorkflowState
    wf = WorkflowState(
        workflow_id="wf_001",
        type="requirement_to_deploy",
        status="active",
        current_phase="development",
        agents_involved=["dev-agent", "qa-agent"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        context={"prd_id": "prd_001"},
    )
    assert wf.workflow_id == "wf_001"
    assert wf.status == "active"


def test_agent_state_defaults():
    from services.orchestration.coordinator.db.models import AgentStateRecord
    state = AgentStateRecord(agent_id="dev-agent", status="idle")
    assert state.current_task is None
    assert state.last_output_at is None
    assert state.error is None


def test_decision_record_creation():
    from services.orchestration.coordinator.db.models import DecisionRecord
    rec = DecisionRecord(
        decision_id="dec_001",
        workflow_id="wf_001",
        reasoning="PRD ready, dispatch to dev",
        action="dispatch_task",
        target_agent="dev-agent",
        created_at=datetime.now(UTC),
    )
    assert rec.outcome is None


@pytest.mark.asyncio
async def test_state_store_get_agent_states_empty():
    from services.orchestration.coordinator.db.state_store import CoordinatorStateStore
    store = CoordinatorStateStore()
    states = await store.get_agent_states()
    assert states == {}


@pytest.mark.asyncio
async def test_state_store_update_and_get_agent_state():
    from services.orchestration.coordinator.db.state_store import CoordinatorStateStore
    store = CoordinatorStateStore()
    await store.update_agent_state("dev-agent", status="working", current_task="task_001")
    states = await store.get_agent_states()
    assert "dev-agent" in states
    assert states["dev-agent"].status == "working"
    assert states["dev-agent"].current_task == "task_001"


@pytest.mark.asyncio
async def test_state_store_get_pending_decisions_empty():
    from services.orchestration.coordinator.db.state_store import CoordinatorStateStore
    store = CoordinatorStateStore()
    pending = await store.get_pending_decisions()
    assert pending == []


@pytest.mark.asyncio
async def test_state_store_persists_decisions_and_agent_state():
    from services.orchestration.coordinator.core.models import Decision
    from services.orchestration.coordinator.db.state_store import CoordinatorStateStore

    store = CoordinatorStateStore()
    decision = Decision(
        target_agent="dev-agent",
        action="dispatch_task",
        task_id="task_001",
        workflow_id="wf_001",
        instruction="Implement the approved requirement",
        reasoning="PRD approved",
    )

    await store.persist([decision])

    pending = await store.get_pending_decisions()
    assert len(pending) == 1
    assert pending[0].decision_id.startswith("dec_")
    assert pending[0].workflow_id == "wf_001"
    assert pending[0].target_agent == "dev-agent"
    assert pending[0].action == "dispatch_task"
    assert pending[0].reasoning == "PRD approved"

    states = await store.get_agent_states()
    assert states["dev-agent"].status == "working"
    assert states["dev-agent"].current_task == "task_001"


@pytest.mark.asyncio
async def test_state_store_caps_pending_decisions():
    from services.orchestration.coordinator.core.models import Decision
    from services.orchestration.coordinator.db.state_store import CoordinatorStateStore

    store = CoordinatorStateStore()
    decisions = [
        Decision(
            target_agent="dev-agent",
            action="dispatch_task",
            task_id=f"task_{index:03d}",
            instruction="Run task",
        )
        for index in range(105)
    ]

    await store.persist(decisions)

    pending = await store.get_pending_decisions()
    assert len(pending) == 100
    assert pending[0].target_agent == "dev-agent"
