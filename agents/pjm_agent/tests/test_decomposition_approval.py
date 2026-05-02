"""Tests for control-plane approval wiring in PJM decomposition."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.pjm_agent.core.decomposition_orchestrator import DecompositionOrchestrator


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
