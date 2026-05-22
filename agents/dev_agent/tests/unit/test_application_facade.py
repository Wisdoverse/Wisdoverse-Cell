"""Dev application facade tests."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.dev_agent.core.application_facade import DevApplicationFacade
from agents.dev_agent.models.schemas import (
    RiskLevel,
    SanitizedTask,
    WorkflowNode,
    WorkflowPlan,
)
from shared.schemas.event import Event, EventTypes


def _facade(**overrides) -> DevApplicationFacade:
    defaults = {
        "standard_request_handler": MagicMock(),
        "sanitizer": MagicMock(),
        "risk_assessor": MagicMock(),
        "has_db": MagicMock(return_value=True),
        "uow_factory": MagicMock(),
        "result_collector_factory": MagicMock(return_value=None),
        "event_factory": MagicMock(),
        "approval_gate_provider": MagicMock(return_value=MagicMock()),
        "planner": MagicMock(),
        "validator": MagicMock(),
        "router": MagicMock(),
        "forge_provider": MagicMock(return_value=MagicMock()),
        "outbox_store_getter": MagicMock(return_value=MagicMock()),
        "event_bus": MagicMock(),
        "event_publisher": MagicMock(),
        "workflow_executor": MagicMock(),
        "max_concurrent_workflows_provider": MagicMock(return_value=3),
        "agentforge_project_id_provider": MagicMock(return_value="cell"),
        "forge_failure_types": (RuntimeError,),
        "record_task_failure": MagicMock(),
        "record_workflow_created": MagicMock(),
    }
    defaults.update(overrides)
    return DevApplicationFacade(**defaults)


@pytest.mark.asyncio
async def test_dev_application_facade_dispatches_event_use_case() -> None:
    event = Event.create(
        event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
        source_agent="pjm-agent",
        payload={},
    )
    expected = [MagicMock()]
    facade = _facade()

    with patch(
        "agents.dev_agent.core.application_facade.DevEventUseCase",
    ) as use_case_class:
        use_case = MagicMock()
        use_case.handle = AsyncMock(return_value=expected)
        use_case_class.return_value = use_case

        result = await facade.handle_event(event)

    assert result is expected
    use_case.handle.assert_awaited_once_with(event)
    assert use_case_class.call_args.kwargs["task_processor"] == facade.process_single_task


@pytest.mark.asyncio
async def test_dev_application_facade_dispatches_request_boundary() -> None:
    request = {"action": "list_failed"}
    facade = _facade()

    with patch(
        "agents.dev_agent.core.application_facade.DevRequestBoundaryUseCase",
    ) as use_case_class:
        use_case = MagicMock()
        use_case.handle = AsyncMock(return_value={"workflows": []})
        use_case_class.return_value = use_case

        result = await facade.handle_request(request)

    assert result == {"workflows": []}
    use_case.handle.assert_awaited_once_with(request)
    assert use_case_class.call_args.kwargs["request_use_case_factory"] == (
        facade._request_use_case
    )


@pytest.mark.asyncio
async def test_dev_application_facade_delegates_outbox_delivery() -> None:
    event = Event.create(
        event_type=EventTypes.DEV_TASK_COMPLETED,
        source_agent="dev-agent",
        payload={"task_id": "dev_1"},
    )
    facade = _facade()

    with patch(
        "agents.dev_agent.core.application_facade.DevOutboxDeliveryUseCase",
    ) as use_case_class:
        use_case = MagicMock()
        use_case.publish_pending_events = AsyncMock(return_value={"total": 0})
        use_case.publish_staged_events = AsyncMock(return_value={"total": 1})
        use_case.publish_event_via_outbox = AsyncMock(return_value=True)
        use_case_class.return_value = use_case

        assert await facade.publish_pending_dev_events(limit=2) == {"total": 0}
        assert await facade.publish_staged_dev_events([event]) == {"total": 1}
        assert await facade.publish_event_via_outbox(event) is True

    use_case.publish_pending_events.assert_awaited_once_with(limit=2)
    use_case.publish_staged_events.assert_awaited_once_with([event])
    use_case.publish_event_via_outbox.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_dev_application_facade_delegates_workflow_execution() -> None:
    sanitized = SanitizedTask(
        title="Build feature",
        description="Implement work package",
        estimated_hours=2,
        wp_id=123,
        risk_level=RiskLevel.MEDIUM,
    )
    plan = WorkflowPlan(
        name="dev-task",
        description="Task",
        nodes=[WorkflowNode(name="plan", config={})],
    )
    task_record = MagicMock(id="dev_1")
    repo = MagicMock()
    log_repo = MagicMock()
    facade = _facade()

    with patch(
        "agents.dev_agent.core.application_facade.DevWorkflowExecutionUseCase",
    ) as use_case_class:
        use_case = MagicMock()
        use_case.process_single_task = AsyncMock(return_value=["processed"])
        use_case.plan_and_execute = AsyncMock(return_value=["planned"])
        use_case.request_workflow_approval = AsyncMock(return_value="approval_1")
        use_case.execute_workflow = AsyncMock(return_value=["executed"])
        use_case_class.return_value = use_case

        assert await facade.process_single_task(
            sanitized,
            RiskLevel.MEDIUM,
            repo,
            log_repo,
            trace_id="trace_1",
        ) == ["processed"]
        assert await facade.plan_and_execute(
            sanitized,
            task_record,
            repo,
            log_repo,
            RiskLevel.MEDIUM,
            trace_id="trace_1",
        ) == ["planned"]
        assert await facade.request_workflow_approval(
            sanitized=sanitized,
            task_id="dev_1",
            plan_json={},
        ) == "approval_1"
        assert await facade.execute_workflow(
            plan,
            task_record,
            repo,
            trace_id="trace_1",
        ) == ["executed"]

    use_case.process_single_task.assert_awaited_once()
    use_case.plan_and_execute.assert_awaited_once()
    use_case.request_workflow_approval.assert_awaited_once()
    use_case.execute_workflow.assert_awaited_once()
