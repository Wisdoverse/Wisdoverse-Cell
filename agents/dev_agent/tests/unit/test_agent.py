from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.dev_agent.core.workflow_validator import ValidationResult
from agents.dev_agent.models.schemas import RiskLevel, SanitizedTask, WorkflowNode, WorkflowPlan
from agents.dev_agent.service import agent as agent_module
from agents.dev_agent.service.agent import DevAgent
from shared.schemas.event import Event, EventTypes


def test_agent_id():
    agent = DevAgent()
    assert agent.agent_id == "dev-agent"


def test_subscribed_events():
    agent = DevAgent()
    assert EventTypes.PM_TASKS_READY_FOR_DEV in agent.subscribed_events
    assert EventTypes.QA_ACCEPTANCE_COMPLETED in agent.subscribed_events


def test_published_events():
    agent = DevAgent()
    assert EventTypes.DEV_WORKFLOW_CREATED in agent.published_events
    assert EventTypes.DEV_TASK_COMPLETED in agent.published_events
    assert EventTypes.DEV_TASK_FAILED in agent.published_events


@pytest.mark.asyncio
async def test_handle_event_unknown_type():
    agent = DevAgent()
    event = Event.create(event_type="unknown.event", source_agent="test", payload={})
    result = await agent.handle_event(event)
    assert result == []


@pytest.mark.asyncio
async def test_handle_request_unknown_action():
    agent = DevAgent()
    result = await agent.handle_request({"action": "nonexistent"})
    assert "error" in result


@pytest.mark.asyncio
async def test_critical_task_rejected():
    agent = DevAgent()
    event = Event.create(
        event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
        source_agent="pjm-agent",
        payload={
            "wp_id": 1,
            "tasks": [
                {
                    "id": 1,
                    "title": "Database migration",
                    "description": "Run alembic migration",
                    "estimated_hours": 2,
                }
            ],
        },
    )
    result = await agent.handle_event(event)
    assert len(result) == 1
    assert result[0].event_type == EventTypes.DEV_TASK_FAILED


@pytest.mark.asyncio
async def test_plan_and_execute_injects_project_id_before_submit():
    agent = DevAgent()
    sanitized = SanitizedTask(
        title="Add projectId",
        description="Inject AgentForge projectId into node config",
        estimated_hours=2,
        wp_id=321,
        related_files=["agents/dev_agent/service/agent.py"],
        risk_level=RiskLevel.MEDIUM,
    )
    task_record = MagicMock(id="dev-321", wp_id=321)
    repo = AsyncMock()
    repo.update_status = AsyncMock(return_value=True)
    log_repo = AsyncMock()

    plan = WorkflowPlan(
        name="dev-task-wp-321",
        description="Inject runtime config",
        nodes=[
            WorkflowNode(
                name="plan",
                config={
                    "prompt": "Edit agents/dev_agent/service/agent.py",
                    "tags": ["plan"],
                },
            ),
            WorkflowNode(
                name="acceptance",
                dependsOn=["plan"],
                config={
                    "prompt": "Verify agents/dev_agent/service/agent.py",
                    "tags": ["acceptance"],
                },
            ),
        ],
    )

    agent._planner.plan = AsyncMock(return_value=plan)
    agent._validator.validate = MagicMock(return_value=ValidationResult())
    agent._router.route = MagicMock(return_value="codex")
    agent._execute_workflow = AsyncMock(return_value=[])

    with patch.object(
        agent_module.settings,
        "dev_agentforge_project_id",
        "project-cell",
        create=True,
    ):
        await agent._plan_and_execute(
            sanitized,
            task_record,
            repo,
            log_repo,
            RiskLevel.MEDIUM,
        )

    submitted_plan = agent._execute_workflow.await_args.args[0]
    assert all(
        node.config["projectId"] == "project-cell" for node in submitted_plan.nodes
    )
    assert all(node.config["cliTool"] == "codex" for node in submitted_plan.nodes)

    stored_workflow = log_repo.create_log.await_args.kwargs["workflow_json"]
    assert all(
        node["config"]["projectId"] == "project-cell"
        for node in stored_workflow["nodes"]
    )
