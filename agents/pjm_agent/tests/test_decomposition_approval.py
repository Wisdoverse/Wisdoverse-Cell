"""Tests for control-plane approval wiring in PJM decomposition."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from agents.pjm_agent.core.decompose import DecomposeError
from agents.pjm_agent.core.decomposition_orchestrator import (
    DecompositionOrchestrator,
)
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
    orchestrator = DecompositionOrchestrator(
        db_manager=MagicMock(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_publisher=MagicMock(),
        approval_gate=approval_gate,
    )
    result_dict = {"summary": "Split feature"}

    approval_id = await orchestrator._request_decomposition_approval(
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
    store = MagicMock()
    store.transaction.return_value = _TransactionContext(transaction)
    return store


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
