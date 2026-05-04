"""Tests for control-plane approval wiring in PJM decomposition."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from agents.pjm_agent.core.decomposition_orchestrator import (
    DecompositionOrchestrator,
)
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
        event_bus=MagicMock(),
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

    agent = MagicMock()
    agent.approve_decomposition = AsyncMock(
        return_value={"subject": "Split feature", "story_count": 1, "task_count": 2}
    )

    with patch.object(api, "get_agent", return_value=agent):
        result = await api.approve_decomposition(
            123,
            api.ApproveRequest(operator="human:pm"),
        )

    assert result.success is True
    agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="human:pm",
    )


@pytest.mark.asyncio
async def test_decomposition_router_surfaces_approval_errors():
    from agents.pjm_agent.api import decomposition as api

    agent = MagicMock()
    agent.approve_decomposition = AsyncMock(
        return_value={"error": "approved_by required for control-plane approval"}
    )

    with patch.object(api, "get_agent", return_value=agent):
        with pytest.raises(HTTPException) as exc_info:
            await api.approve_decomposition(123, api.ApproveRequest())

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "approved_by required for control-plane approval"
    agent.approve_decomposition.assert_awaited_once_with(123, approved_by="")


def _db_manager_with_session():
    db_manager = MagicMock()
    session = MagicMock()

    @asynccontextmanager
    async def _session():
        yield session

    db_manager.session = _session
    return db_manager


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
        event_bus=MagicMock(),
        approval_gate=approval_gate,
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="pending",
            decompose_result={"control_plane_approval_id": "appr_pjm_1"},
        )
    )

    with patch(
        "agents.pjm_agent.core.decomposition_orchestrator.DecompositionRepository",
        return_value=repo,
    ):
        result = await orchestrator.approve_decomposition(123, approved_by="")

    assert result == {
        "error": "approved_by required for control-plane approval",
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
        event_bus=MagicMock(),
        approval_gate=approval_gate,
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

    with patch(
        "agents.pjm_agent.core.decomposition_orchestrator.DecompositionRepository",
        return_value=repo,
    ):
        result = await orchestrator.reject_decomposition(123, rejected_by="")

    assert result == {
        "error": "rejected_by required for control-plane rejection",
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
        event_bus=MagicMock(),
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(return_value=SimpleNamespace(status="writing"))
    repo.delete_by_wp_id = AsyncMock()

    event = Event.create(
        event_type=EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
        source_agent="sync-agent",
        payload={
            "wp_id": 123,
            "project_id": 456,
            "subject": "Split feature",
            "wp_type": "Feature",
        },
    )

    with patch(
        "agents.pjm_agent.core.decomposition_orchestrator.DecompositionRepository",
        return_value=repo,
    ):
        result = await orchestrator.handle_decompose(event)

    assert result == []
    repo.delete_by_wp_id.assert_not_awaited()
    decompose_service.decompose.assert_not_awaited()


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
    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    orchestrator = DecompositionOrchestrator(
        db_manager=_db_manager_with_session(),
        op_writer=MagicMock(),
        decompose_service=MagicMock(),
        push_service=MagicMock(),
        create_event_fn=MagicMock(),
        event_bus=event_bus,
        op_client=op_client,
    )
    repo = MagicMock()
    repo.get_by_wp_id = AsyncMock(
        return_value=SimpleNamespace(
            status="write_failed",
            project_id=456,
            assignee_id=789,
        )
    )
    repo.delete_by_wp_id = AsyncMock(return_value=True)

    with patch(
        "agents.pjm_agent.core.decomposition_orchestrator.DecompositionRepository",
        return_value=repo,
    ):
        result = await orchestrator.retry_decompose(123)

    assert result == {"status": "retrying", "wp_id": 123}
    repo.delete_by_wp_id.assert_awaited_once_with(123)
    event_bus.publish.assert_awaited_once()
    published = event_bus.publish.await_args.args[0]
    assert published.event_type == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE
    assert published.payload["assignee_id"] == 789
