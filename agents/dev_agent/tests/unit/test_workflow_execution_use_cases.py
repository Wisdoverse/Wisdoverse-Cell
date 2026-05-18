from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.dev_agent.core.workflow_execution_use_cases import (
    DevWorkflowExecutionUseCase,
)
from agents.dev_agent.models.schemas import (
    RiskLevel,
    SanitizedTask,
    WorkflowNode,
    WorkflowPlan,
)
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
            source_agent="dev-agent",
            payload=payload,
            trace_id=trace_id,
        )


def _sanitized(risk: RiskLevel = RiskLevel.MEDIUM) -> SanitizedTask:
    return SanitizedTask(
        title="Implement endpoint",
        description="Add the requested backend route",
        estimated_hours=3,
        wp_id=123,
        related_files=["agents/dev_agent/core/workflow_execution_use_cases.py"],
        risk_level=risk,
    )


def _task_record(**overrides):
    defaults = {
        "id": "dev-123",
        "wp_id": 123,
        "status": "pending",
        "retry_count": 0,
        "workflow_id": None,
        "mr_url": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _plan() -> WorkflowPlan:
    return WorkflowPlan(
        name="dev-task-wp-123",
        description="Implement endpoint",
        nodes=[
            WorkflowNode(
                name="implementation",
                config={"prompt": "Edit backend files", "tags": ["implementation"]},
            )
        ],
    )


def _use_case(
    *,
    plan: WorkflowPlan | None = None,
    approval_gate=None,
    forge=None,
    workflow_executor=None,
    task_failures=None,
    workflow_created=None,
    forge_failure_types: tuple[type[BaseException], ...] = (Exception,),
) -> DevWorkflowExecutionUseCase:
    planner = SimpleNamespace(plan=AsyncMock(return_value=plan or _plan()))
    validator = SimpleNamespace(
        validate=MagicMock(return_value=SimpleNamespace(is_valid=True, violations=[]))
    )
    router = SimpleNamespace(route=MagicMock(return_value="codex"))
    approval_gate = approval_gate or SimpleNamespace(
        enforced=False,
        request_approval=AsyncMock(return_value=SimpleNamespace(approval_id="appr_dev")),
    )
    return DevWorkflowExecutionUseCase(
        planner=planner,
        validator=validator,
        router=router,
        approval_gate=approval_gate,
        event_factory=_Factory(),
        forge=forge,
        max_concurrent_workflows=2,
        agentforge_project_id="wisdoverse-cell",
        workflow_executor=workflow_executor,
        forge_failure_types=forge_failure_types,
        record_task_failure=(
            task_failures.append if task_failures is not None else lambda _reason: None
        ),
        record_workflow_created=(
            (lambda: workflow_created.append(None))
            if workflow_created is not None
            else lambda: None
        ),
    )


@pytest.mark.asyncio
async def test_process_single_task_persists_input_and_delegates_to_executor() -> None:
    repo = AsyncMock()
    repo.create_task = AsyncMock(return_value=_task_record())
    repo.count_active_workflows = AsyncMock(return_value=0)
    log_repo = AsyncMock()
    expected_event = Event.create(
        event_type=EventTypes.DEV_WORKFLOW_CREATED,
        source_agent="dev-agent",
        payload={"task_id": "dev-123"},
        trace_id="trace-dev",
    )
    executor = AsyncMock()
    executor.execute_workflow = AsyncMock(return_value=[expected_event])
    use_case = _use_case(workflow_executor=executor)

    result = await use_case.process_single_task(
        _sanitized(),
        RiskLevel.MEDIUM,
        repo,
        log_repo,
        trace_id="trace-dev",
    )

    assert result == [expected_event]
    repo.create_task.assert_awaited_once_with(
        wp_id=123,
        task_title="Implement endpoint",
        risk_level="MEDIUM",
    )
    first_log = log_repo.create_log.await_args_list[0].kwargs
    assert first_log["workflow_json"]["task_input"]["wp_id"] == 123
    executor.execute_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_plan_and_execute_injects_project_routes_tools_and_preserves_trace() -> None:
    repo = AsyncMock()
    log_repo = AsyncMock()
    task_record = _task_record()
    executor = AsyncMock()
    executor.execute_workflow = AsyncMock(return_value=[])
    use_case = _use_case(workflow_executor=executor)

    await use_case.plan_and_execute(
        _sanitized(),
        task_record,
        repo,
        log_repo,
        RiskLevel.MEDIUM,
        trace_id="trace-dev",
    )

    submitted_plan = executor.execute_workflow.await_args.args[0]
    assert submitted_plan.nodes[0].config["projectId"] == "wisdoverse-cell"
    assert submitted_plan.nodes[0].config["cliTool"] == "codex"
    assert executor.execute_workflow.await_args.kwargs["trace_id"] == "trace-dev"
    stored_workflow = log_repo.create_log.await_args.kwargs["workflow_json"]
    assert stored_workflow["nodes"][0]["config"]["projectId"] == "wisdoverse-cell"
    assert stored_workflow["nodes"][0]["config"]["cliTool"] == "codex"


@pytest.mark.asyncio
async def test_high_risk_plan_records_approval_and_does_not_execute() -> None:
    repo = AsyncMock()
    log_repo = AsyncMock()
    task_record = _task_record()
    executor = AsyncMock()
    executor.execute_workflow = AsyncMock()
    approval_gate = SimpleNamespace(
        enforced=False,
        request_approval=AsyncMock(return_value=SimpleNamespace(approval_id="appr_high")),
    )
    use_case = _use_case(approval_gate=approval_gate, workflow_executor=executor)

    result = await use_case.plan_and_execute(
        _sanitized(RiskLevel.HIGH),
        task_record,
        repo,
        log_repo,
        RiskLevel.HIGH,
    )

    assert result == []
    stored_workflow = log_repo.create_log.await_args.kwargs["workflow_json"]
    assert stored_workflow["control_plane_approval_id"] == "appr_high"
    repo.update_status.assert_any_await("dev-123", "awaiting_approval")
    executor.execute_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_workflow_updates_status_and_emits_traced_event() -> None:
    repo = AsyncMock()
    forge = AsyncMock()
    forge.create_workflow = AsyncMock(return_value="wf-123")
    forge.run_workflow = AsyncMock()
    created: list[None] = []
    use_case = _use_case(forge=forge, workflow_created=created)

    result = await use_case.execute_workflow(
        _plan(),
        _task_record(),
        repo,
        trace_id="trace-dev",
    )

    assert len(result) == 1
    assert result[0].event_type == EventTypes.DEV_WORKFLOW_CREATED
    assert result[0].metadata.trace_id == "trace-dev"
    assert result[0].payload == {
        "task_id": "dev-123",
        "workflow_id": "wf-123",
        "node_count": 1,
    }
    forge.create_workflow.assert_awaited_once()
    forge.run_workflow.assert_awaited_once_with("wf-123")
    assert repo.update_status.await_args.kwargs["workflow_id"] == "wf-123"
    assert len(created) == 1


@pytest.mark.asyncio
async def test_execute_workflow_records_forge_failures() -> None:
    class ForgeFailure(Exception):
        pass

    repo = AsyncMock()
    forge = AsyncMock()
    forge.create_workflow = AsyncMock(side_effect=ForgeFailure("forge down"))
    failures: list[str] = []
    use_case = _use_case(
        forge=forge,
        task_failures=failures,
        forge_failure_types=(ForgeFailure,),
    )

    result = await use_case.execute_workflow(_plan(), _task_record(), repo)

    assert result == []
    repo.update_status.assert_awaited_once_with(
        "dev-123",
        "failed",
        error_message="forge down",
    )
    assert failures == ["forge_error"]
