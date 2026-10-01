"""Tests for control-plane approval wiring in PJM decomposition."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from agents.pjm_agent.core.config import PJMCoreConfig
from agents.pjm_agent.core.decompose import DecomposeError
from agents.pjm_agent.core.decomposition_approval_workflow import (
    DecompositionApprovalWorkflow,
)
from agents.pjm_agent.core.decomposition_orchestrator import (
    DecompositionOrchestrator,
)
from agents.pjm_agent.core.decomposition_request_workflow import (
    DecompositionRequestWorkflow,
)
from agents.pjm_agent.models.schemas import WBSResult
from shared.api import ApiErrorCode
from shared.schemas.event import Event, EventTypes


@pytest.mark.asyncio
async def test_decomposition_approval_request_returns_control_plane_id():
    approval_gate = MagicMock()
    approval_gate.request_approval = AsyncMock(
        return_value=SimpleNamespace(
            approval_id="appr_pjm_1",
            created_at=SimpleNamespace(isoformat=lambda: "2026-05-01T00:00:00+00:00"),
        )
    )
    approval_gate.enforced = False
    workflow = DecompositionRequestWorkflow(
        decomposition_store=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        approval_gate=approval_gate,
        create_event_fn=MagicMock(),
        config=MagicMock(),
    )
    result_dict = {"summary": "Split feature"}

    approval_id = await workflow.request_decomposition_approval(
        wp_id=123,
        project_id=456,
        subject="Split feature",
        result_dict=result_dict,
        trace_id="trace-pjm",
    )

    assert approval_id == "appr_pjm_1"
    assert result_dict["approval_requested_at"] == "2026-05-01T00:00:00+00:00"
    approval_gate.request_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_decomposition_router_forwards_operator_identity():
    from agents.pjm_agent.api import decomposition as api
    from agents.pjm_agent.core.api_use_cases import PMApiUseCase

    agent = MagicMock()
    agent.approve_decomposition = AsyncMock(
        return_value={"subject": "Split feature", "story_count": 1, "task_count": 2}
    )

    result = await api.approve_decomposition(
        123,
        api.ApproveRequest(operator="human:pm"),
        pm_api=PMApiUseCase(agent),
    )

    assert result.success is True
    agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="human:pm",
    )


@pytest.mark.asyncio
async def test_decomposition_router_surfaces_approval_errors():
    from agents.pjm_agent.api import decomposition as api
    from agents.pjm_agent.core.api_use_cases import PMApiUseCase

    agent = MagicMock()
    agent.approve_decomposition = AsyncMock(
        return_value={"error": "approved_by required for control-plane approval"}
    )

    with pytest.raises(HTTPException) as exc_info:
        await api.approve_decomposition(
            123,
            api.ApproveRequest(),
            pm_api=PMApiUseCase(agent),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "approved_by required for control-plane approval"
    assert (
        exc_info.value.headers["X-Error-Code"]
        == ApiErrorCode.PM_DECOMPOSITION_FORBIDDEN.value
    )
    agent.approve_decomposition.assert_awaited_once_with(123, approved_by="")


def _db_manager_with_session():
    db_manager = MagicMock()
    session = MagicMock()

    @asynccontextmanager
    async def _session():
        yield session

    db_manager.session = _session
    return db_manager


def _outbox_store():
    store = MagicMock()
    store.add = AsyncMock()
    store.stage = AsyncMock()
    store.list_pending = AsyncMock(return_value=[])
    store.mark_published = AsyncMock()
    store.mark_failed = AsyncMock()
    return store


class _TransactionContext:
    def __init__(self, transaction):
        self._transaction = transaction

    async def __aenter__(self):
        return self._transaction

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _decomposition_store(transaction):
    transaction.stage_event = AsyncMock()
    transaction.commit = AsyncMock()
    transaction.rollback = AsyncMock()
    transaction.completed = False
    store = MagicMock()
    store.transaction.return_value = _TransactionContext(transaction)
    return store


class _MutableDecompositionTransaction:
    def __init__(self, *, fail_create: bool = False):
        self.record = None
        self.fail_create = fail_create
        self.staged_events = []
        self.completed = False

    async def get_by_wp_id(self, _wp_id):
        return self.record

    async def create(self, *, wp_id, project_id, decompose_result, assignee_id=None):
        if self.fail_create:
            raise RuntimeError("synthetic decomposition persistence failure")
        self.record = SimpleNamespace(
            wp_id=wp_id,
            project_id=project_id,
            decompose_result=decompose_result,
            assignee_id=assignee_id,
            status="pending",
        )
        return self.record

    async def update_status(self, _wp_id, status, approved_by=None):
        self.record.status = status
        if approved_by is not None:
            self.record.approved_by = approved_by
        return True

    async def delete_by_wp_id(self, _wp_id):
        self.record = None
        return True

    async def stage_event(self, event):
        self.staged_events.append(event)

    async def commit(self):
        self.completed = True

    async def rollback(self):
        self.completed = True


def _mutable_decomposition_store(transaction):
    store = MagicMock()
    store.transaction.return_value = _TransactionContext(transaction)
    return store


def _delivery_event(*, company_id="cmp_pjm_delivery", trace_id="trace-rm-pjm"):
    return Event.create(
        event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
        source_agent="requirement-manager",
        payload={
            "company_id": company_id,
            "requirement_id": "req_synthetic_001",
            "requirement_hash": "a" * 64,
            "goal_id": "goal_synthetic_001",
            "work_item_id": "work_synthetic_001",
            "wp_id": 321,
            "project_id": 654,
            "subject": "Deliver reviewed export",
            "description": "Preserve the reviewed requirement context.",
            "wp_type": "Feature",
            "project_name": "Synthetic project",
        },
        trace_id=trace_id,
    )


def _request_workflow(*, store, decompose_service, create_event_fn, messenger=None):
    card_renderer = MagicMock()
    card_renderer.build_decomposition_approval_card.return_value = {"card": "synthetic"}
    return DecompositionRequestWorkflow(
        decomposition_store=store,
        decompose_service=decompose_service,
        push_service=MagicMock(),
        approval_gate=SimpleNamespace(
            enforced=True,
            request_approval=AsyncMock(return_value=None),
        ),
        create_event_fn=create_event_fn,
        config=PJMCoreConfig.from_values(
            company_id="cmp_pjm_delivery",
            decompose_notify_open_id="ou_synthetic_reviewer",
        ),
        messenger=messenger,
        card_renderer=card_renderer,
    ), card_renderer


def _wbs_result():
    return WBSResult(
        summary="Reviewed export delivery",
        subtasks=[
            {
                "subject": "Implement export",
                "estimated_days": 2,
                "children": [{"subject": "Add endpoint", "estimated_hours": 4}],
            }
        ],
    )


def _create_event(event_type, payload, trace_id=None):
    return Event.create(
        event_type=event_type,
        source_agent="pjm-agent",
        payload=payload,
        trace_id=trace_id,
    )


@pytest.mark.asyncio
async def test_approve_decomposition_requires_operator_for_control_plane_approval():
    approval_gate = MagicMock()
    approval_gate.approve_for_sensitive_action = AsyncMock()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
        approval_gate=approval_gate,
        outbox_store=_outbox_store(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="pending",
            decompose_result={"control_plane_approval_id": "appr_pjm_1"},
        )
    )
    orchestrator._decomposition_store = _decomposition_store(repo)

    result = await orchestrator.approve_decomposition(123, approved_by="")

    assert result == {
        "error": "approved_by required for control-plane approval",
        "error_code": "control_plane_approval_resolver_required",
        "wp_id": 123,
        "control_plane_approval_id": "appr_pjm_1",
    }
    approval_gate.approve_for_sensitive_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_decomposition_requires_operator_for_control_plane_rejection():
    approval_gate = MagicMock()
    approval_gate.reject_for_sensitive_action = AsyncMock()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
        approval_gate=approval_gate,
        outbox_store=_outbox_store(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="pending",
            decompose_result={
                "summary": "Split feature",
                "control_plane_approval_id": "appr_pjm_1",
            },
        )
    )
    orchestrator._decomposition_store = _decomposition_store(repo)

    result = await orchestrator.reject_decomposition(123, rejected_by="")

    assert result == {
        "error": "rejected_by required for control-plane rejection",
        "error_code": "control_plane_rejection_resolver_required",
        "wp_id": 123,
        "control_plane_approval_id": "appr_pjm_1",
    }
    approval_gate.reject_for_sensitive_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_decompose_skips_in_progress_write_replay():
    decompose_service = MagicMock()
    decompose_service.decompose = AsyncMock()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=decompose_service,
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
        outbox_store=_outbox_store(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(return_value=SimpleNamespace(status="writing"))
    repo.delete_by_wp_id = AsyncMock()
    orchestrator._decomposition_store = _decomposition_store(repo)

    event = Event.create(
        event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
        source_agent="sync-module",
        payload={
            "wp_id": 123,
            "project_id": 456,
            "subject": "Split feature",
            "wp_type": "Feature",
        },
    )

    result = await orchestrator.handle_decompose(event)

    assert result == []
    repo.delete_by_wp_id.assert_not_awaited()
    decompose_service.decompose.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_decompose_failure_persists_error_code():
    decompose_service = MagicMock()
    decompose_service.decompose = AsyncMock(side_effect=DecomposeError("LLM failed"))
    push_service = MagicMock()
    push_service.send_decompose_failure = AsyncMock()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=decompose_service,
        push_service=push_service,
        create_event_fn=lambda event_type, payload, trace_id=None: Event.create(
            event_type=event_type,
            source_agent="pjm-agent",
            payload=payload,
            trace_id=trace_id,
        ),
        event_publisher=MagicMock(),
        outbox_store=_outbox_store(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(return_value=None)
    repo.create = AsyncMock()
    repo.update_status = AsyncMock()
    orchestrator._decomposition_store = _decomposition_store(repo)

    event = Event.create(
        event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
        source_agent="sync-module",
        payload={
            "wp_id": 123,
            "project_id": 456,
            "subject": "Split feature",
            "wp_type": "Feature",
        },
        trace_id="trace_decompose",
    )

    result = await orchestrator.handle_decompose(event)

    assert result[0].event_type == EventTypes.PM_DECOMPOSE_COMPLETED
    assert result[0].payload["status"] == "rejected"
    assert repo.create.await_args.kwargs["decompose_result"] == {
        "error": "LLM failed",
        "error_code": "pm.decomposition_failed",
    }
    repo.update_status.assert_awaited_once_with(123, "failed")


@pytest.mark.asyncio
async def test_delivery_company_mismatch_is_rejected_before_decomposition():
    store = MagicMock()
    decompose_service = MagicMock()
    decompose_service.decompose = AsyncMock()
    workflow, _ = _request_workflow(
        store=store,
        decompose_service=decompose_service,
        create_event_fn=MagicMock(),
    )

    with pytest.raises(ValueError, match="delivery_handoff_company_mismatch"):
        await workflow.handle_decompose(_delivery_event(company_id="cmp_unexpected_company"))

    decompose_service.decompose.assert_not_awaited()
    store.transaction.assert_not_called()


@pytest.mark.asyncio
async def test_delivery_context_and_trace_survive_persistence_and_approved_dev_handoff():
    transaction = _MutableDecompositionTransaction()
    store = _mutable_decomposition_store(transaction)
    decompose_service = MagicMock()
    decompose_service.decompose = AsyncMock(return_value=_wbs_result())
    messenger = MagicMock()
    messenger.send_card = AsyncMock()
    request_workflow, card_renderer = _request_workflow(
        store=store,
        decompose_service=decompose_service,
        create_event_fn=_create_event,
        messenger=messenger,
    )

    inbound_event = _delivery_event()
    request_events = await request_workflow.handle_decompose(inbound_event)

    persisted_context = transaction.record.decompose_result["delivery_context"]
    assert persisted_context == {
        "company_id": "cmp_pjm_delivery",
        "requirement_id": "req_synthetic_001",
        "requirement_hash": "a" * 64,
        "goal_id": "goal_synthetic_001",
        "work_item_id": "work_synthetic_001",
        "trace_id": "trace-rm-pjm",
        "handoff_event_id": inbound_event.event_id,
    }
    assert transaction.record.status == "pending"
    assert len(request_events) == 1
    assert request_events[0].event_type == EventTypes.PM_DECOMPOSE_COMPLETED
    assert request_events[0].metadata.trace_id == "trace-rm-pjm"
    messenger.send_card.assert_awaited_once()
    card_renderer.build_decomposition_approval_card.assert_called_once()

    approval_gate = MagicMock()
    approval_gate.approve_for_sensitive_action = AsyncMock()
    op_writer = MagicMock()
    op_writer.write_wbs = AsyncMock(return_value={"created": True})
    approval = DecompositionApprovalWorkflow(
        decomposition_store=store,
        approval_gate=approval_gate,
        op_writer=op_writer,
        push_service=MagicMock(),
        create_event_fn=_create_event,
    )

    approved = await approval.approve_decomposition(321, approved_by="human:pm")

    dev_event = next(
        staged.event
        for staged in approved.staged_events
        if staged.event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV
    )
    assert dev_event.metadata.trace_id == "trace-rm-pjm"
    assert dev_event.payload["delivery_context"] == persisted_context
    assert dev_event.payload["tasks"][0]["title"] == "Add endpoint"
    assert op_writer.write_wbs.await_count == 1


@pytest.mark.asyncio
async def test_delivery_persistence_failure_prevents_approval_card_and_success_event():
    transaction = _MutableDecompositionTransaction(fail_create=True)
    store = _mutable_decomposition_store(transaction)
    decompose_service = MagicMock()
    decompose_service.decompose = AsyncMock(return_value=_wbs_result())
    messenger = MagicMock()
    messenger.send_card = AsyncMock()
    create_event_fn = MagicMock()
    workflow, card_renderer = _request_workflow(
        store=store,
        decompose_service=decompose_service,
        create_event_fn=create_event_fn,
        messenger=messenger,
    )

    with pytest.raises(RuntimeError, match="synthetic decomposition persistence failure"):
        await workflow.handle_decompose(_delivery_event())

    create_event_fn.assert_not_called()
    messenger.send_card.assert_not_awaited()
    card_renderer.build_decomposition_approval_card.assert_not_called()


@pytest.mark.asyncio
async def test_retry_decompose_allows_write_failed_records():
    op_client = MagicMock()
    op_client.get_work_package = AsyncMock(
        return_value={
            "subject": "Split feature",
            "description": {"raw": "Break it down"},
            "_links": {
                "type": {"title": "Feature"},
                "project": {"title": "Cell"},
                "assignee": {"title": "Alice"},
            },
        }
    )
    event_publisher = MagicMock()
    event_publisher.publish = AsyncMock()
    outbox_store = _outbox_store()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=event_publisher,
        op_client=op_client,
        outbox_store=outbox_store,
    )
    orchestrator._mark_pjm_event_published = AsyncMock()
    orchestrator._mark_pjm_event_failed = AsyncMock()
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="write_failed",
            project_id=456,
            assignee_id=789,
        )
    )
    repo.delete_by_wp_id = AsyncMock(return_value=True)
    orchestrator._decomposition_store = _decomposition_store(repo)

    result = await orchestrator.retry_decompose(123)

    assert result == {"status": "retrying", "wp_id": 123}
    repo.delete_by_wp_id.assert_awaited_once_with(123)
    repo.stage_event.assert_awaited_once()
    event_publisher.publish.assert_awaited_once()
    published = event_publisher.publish.await_args.args[0]
    assert published.event_type == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE
    assert published.payload["assignee_id"] == 789
    orchestrator._mark_pjm_event_published.assert_awaited_once_with(published)
    orchestrator._mark_pjm_event_failed.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_decompose_requires_wp_id_error_code():
    orchestrator = DecompositionOrchestrator(
        db_manager=MagicMock(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
    )

    result = await orchestrator.retry_decompose(0)

    assert result == {
        "error": "wp_id is required",
        "error_code": "wp_id_required",
    }


@pytest.mark.asyncio
async def test_retry_decompose_missing_record_error_code():
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
        outbox_store=_outbox_store(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(return_value=None)
    orchestrator._decomposition_store = _decomposition_store(repo)

    result = await orchestrator.retry_decompose(123)

    assert result == {
        "error": "record not found",
        "error_code": "pm.decomposition_not_found",
    }


@pytest.mark.asyncio
async def test_approve_decomposition_stages_events_before_publish():
    event_publisher = MagicMock()
    event_publisher.publish = AsyncMock()
    op_writer = MagicMock()
    op_writer.write_wbs = AsyncMock(return_value={"created": True})
    outbox_store = _outbox_store()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=op_writer,
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=lambda event_type, payload, trace_id=None: Event.create(
            event_type=event_type,
            source_agent="pjm-agent",
            payload=payload,
            trace_id=trace_id,
        ),
        event_publisher=event_publisher,
        outbox_store=outbox_store,
    )
    orchestrator._mark_pjm_event_published = AsyncMock()
    orchestrator._mark_pjm_event_failed = AsyncMock()

    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="pending",
            decompose_result={
                "summary": "Split feature",
                "subtasks": [
                    {
                        "subject": "Story 1",
                        "children": [{"subject": "Task 1", "estimated_hours": 5}],
                    }
                ],
            },
            project_id=456,
            assignee_id=789,
        )
    )
    repo.update_status = AsyncMock(return_value=True)
    orchestrator._decomposition_store = _decomposition_store(repo)

    result = await orchestrator.approve_decomposition(123, approved_by="human:pm")

    assert result == {"subject": "Split feature", "story_count": 1, "task_count": 1}
    repo.update_status.assert_any_await(123, "writing", approved_by="human:pm")
    repo.update_status.assert_any_await(123, "approved")
    assert repo.stage_event.await_count == 2
    staged_events = [call.args[0] for call in repo.stage_event.await_args_list]
    assert [event.event_type for event in staged_events] == [
        EventTypes.PM_DECOMPOSE_COMPLETED,
        EventTypes.PM_TASKS_READY_FOR_DEV,
    ]
    assert event_publisher.publish.await_count == 2
    published_events = [call.args[0] for call in event_publisher.publish.await_args_list]
    assert published_events == staged_events
    assert orchestrator._mark_pjm_event_published.await_count == 2
    orchestrator._mark_pjm_event_failed.assert_not_awaited()
