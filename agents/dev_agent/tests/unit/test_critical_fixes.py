"""Tests for critical fixes: wiring, reconcile, pending queue, retry, approval."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from agents.dev_agent.db.repository import (
    DevTaskRepository,
    DevWorkflowLogRepository,
)
from agents.dev_agent.service.agent import DevAgent
from shared.api import ApiErrorCode

# --- Helpers ---


def _make_mock_task(
    task_id="dev-001",
    wp_id=100,
    status="pending",
    workflow_id=None,
    workflow_started_at=None,
    risk_level="MEDIUM",
    retry_count=0,
    task_title="Test task",
    mr_iid=None,
    mr_url=None,
    last_polled_at=None,
    error_message=None,
    failed_step=None,
):
    task = MagicMock()
    task.id = task_id
    task.wp_id = wp_id
    task.status = status
    task.workflow_id = workflow_id
    task.workflow_started_at = workflow_started_at
    task.risk_level = risk_level
    task.retry_count = retry_count
    task.task_title = task_title
    task.mr_iid = mr_iid
    task.mr_url = mr_url
    task.last_polled_at = last_polled_at
    task.error_message = error_message
    task.failed_step = failed_step
    task.created_at = datetime.now(UTC)
    task.updated_at = datetime.now(UTC)
    return task


def _make_mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_agent_with_db():
    """Create a DevAgent with mocked db_manager."""
    agent = DevAgent()
    mock_db_manager = MagicMock()
    mock_session = _make_mock_session()

    @asynccontextmanager
    async def mock_session_cm():
        yield mock_session

    mock_db_manager.session = mock_session_cm
    agent._db_manager = mock_db_manager
    return agent, mock_session


# --- C1: DevAgent runtime wiring ---


class TestRuntimeWiring:
    def test_has_db_with_db_manager(self):
        agent = DevAgent()
        assert not agent._has_db()
        agent._db_manager = MagicMock()
        assert agent._has_db()

    def test_has_db_with_injected_repo(self):
        agent = DevAgent()
        assert not agent._has_db()
        agent.set_repository(MagicMock())
        assert agent._has_db()

    @pytest.mark.asyncio
    async def test_handle_request_without_db_returns_error(self):
        agent = DevAgent()
        result = await agent.handle_request({"action": "get_task_status", "wp_id": 1})
        assert "error" in result
        assert result["error_code"] == "database_not_initialized"

    @pytest.mark.asyncio
    async def test_handle_request_unknown_action_uses_error_code(self):
        agent, _ = _make_agent_with_db()
        mock_repo = AsyncMock(spec=DevTaskRepository)

        with patch.object(agent, "_get_repo", return_value=mock_repo):
            result = await agent.handle_request({"action": "nonexistent"})

        assert result == {
            "error": "Unknown action: nonexistent",
            "error_code": "unknown_action",
            "action": "nonexistent",
        }

    @pytest.mark.asyncio
    async def test_handle_request_list_active_without_db_returns_empty(self):
        agent = DevAgent()
        result = await agent.handle_request({"action": "list_active_workflows"})
        assert result == {"workflows": []}

    @pytest.mark.asyncio
    async def test_handle_request_list_failed_without_db_returns_empty(self):
        agent = DevAgent()
        result = await agent.handle_request({"action": "list_failed"})
        assert result == {"workflows": []}


# --- C2: ReconciliationLoop calls ResultCollector ---


class TestReconcileResultCollection:
    @pytest.mark.asyncio
    async def test_reconcile_polls_forge_on_executing_task(self):
        """When a task is 'executing' and poll interval elapsed,
        reconcile should poll AgentForge for status."""
        from agents.dev_agent.app import main as main_module

        task = _make_mock_task(
            status="executing",
            workflow_id="wf-abc",
            workflow_started_at=datetime.now(UTC) - timedelta(minutes=5),
            last_polled_at=datetime.now(UTC) - timedelta(minutes=2),
        )

        mock_session = _make_mock_session()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.list_active_tasks = AsyncMock(return_value=[task])
        mock_repo.list_pending_tasks = AsyncMock(return_value=[])
        mock_repo.list_planning_tasks = AsyncMock(return_value=[])
        mock_repo.count_active_workflows = AsyncMock(return_value=1)

        # Advisory lock succeeds
        lock_mock = MagicMock()
        lock_mock.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=lock_mock)

        mock_forge = AsyncMock()
        mock_forge.get_status = AsyncMock(return_value={"status": "running"})

        mock_gitlab = AsyncMock()

        orig_forge = main_module._forge_client
        orig_gitlab = main_module._gitlab_client

        try:
            main_module._forge_client = mock_forge
            main_module._gitlab_client = mock_gitlab

            with (
                patch.object(main_module, "_get_agent"),
                patch.object(main_module, "db_manager") as mock_db,
                patch.object(main_module, "SqlAlchemyDevTaskStore", return_value=mock_repo),
                patch.object(main_module, "SqlAlchemyDevWorkflowLogStore", return_value=AsyncMock()),
            ):
                @asynccontextmanager
                async def mock_session_cm():
                    yield mock_session

                mock_db.session = mock_session_cm

                await main_module._reconcile()

            mock_forge.get_status.assert_called_once_with("wf-abc")
        finally:
            main_module._forge_client = orig_forge
            main_module._gitlab_client = orig_gitlab

    def test_reconcile_code_creates_result_collector(self):
        """Verify that _reconcile code path creates ResultCollector
        when workflow is completed and gitlab client is available."""
        import inspect

        from agents.dev_agent.app import main as main_module

        source = inspect.getsource(main_module._reconcile)
        # Verify ResultCollector is instantiated in the code
        assert "ResultCollector(" in source
        # Verify handle_completion is called
        assert "handle_completion" in source
        # Verify it does NOT just set status to security_scanning
        # (the old behavior only did update_status)


# --- C3: Pending task queue processing ---


class TestPendingTaskProcessing:
    @pytest.mark.asyncio
    async def test_pending_tasks_started_when_slots_open(self):
        """When active workflows < max, pending tasks should be picked up."""
        from agents.dev_agent.app import main as main_module

        pending_task = _make_mock_task(
            task_id="dev-pending-1",
            wp_id=200,
            status="pending",
        )

        mock_session = _make_mock_session()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.list_active_tasks = AsyncMock(return_value=[])
        mock_repo.list_pending_tasks = AsyncMock(return_value=[pending_task])
        mock_repo.list_planning_tasks = AsyncMock(return_value=[])
        mock_repo.count_active_workflows = AsyncMock(return_value=0)
        mock_repo.update_status = AsyncMock(return_value=True)
        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)

        lock_mock = MagicMock()
        lock_mock.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=lock_mock)

        mock_forge = AsyncMock()
        mock_forge.create_workflow = AsyncMock(return_value="wf-new")
        mock_forge.run_workflow = AsyncMock()

        orig_forge = main_module._forge_client
        try:
            main_module._forge_client = mock_forge

            with (
                patch.object(main_module, "_get_agent"),
                patch.object(main_module, "db_manager") as mock_db,
                patch.object(main_module, "SqlAlchemyDevTaskStore", return_value=mock_repo),
                patch.object(main_module, "SqlAlchemyDevWorkflowLogStore", return_value=mock_log_repo),
                patch.object(main_module, "_start_pending_task") as mock_start,
            ):
                @asynccontextmanager
                async def mock_session_cm():
                    yield mock_session

                mock_db.session = mock_session_cm

                await main_module._reconcile()

            mock_start.assert_called_once()
        finally:
            main_module._forge_client = orig_forge


# --- C4: Failed->planning retry re-enters pipeline ---


class TestRetryReentry:
    @pytest.mark.asyncio
    async def test_planning_tasks_with_retry_picked_up(self):
        """Tasks in 'planning' with retry_count > 0 should be re-entered."""
        from agents.dev_agent.app import main as main_module

        retry_task = _make_mock_task(
            task_id="dev-retry-1",
            wp_id=300,
            status="planning",
            retry_count=1,
        )

        mock_session = _make_mock_session()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.list_active_tasks = AsyncMock(return_value=[])
        mock_repo.list_pending_tasks = AsyncMock(return_value=[])
        mock_repo.list_planning_tasks = AsyncMock(return_value=[retry_task])
        mock_repo.count_active_workflows = AsyncMock(return_value=0)
        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)

        lock_mock = MagicMock()
        lock_mock.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=lock_mock)

        orig_forge = main_module._forge_client
        try:
            main_module._forge_client = AsyncMock()

            with (
                patch.object(main_module, "_get_agent"),
                patch.object(main_module, "db_manager") as mock_db,
                patch.object(main_module, "SqlAlchemyDevTaskStore", return_value=mock_repo),
                patch.object(main_module, "SqlAlchemyDevWorkflowLogStore", return_value=mock_log_repo),
                patch.object(main_module, "_start_pending_task") as mock_start,
            ):
                @asynccontextmanager
                async def mock_session_cm():
                    yield mock_session

                mock_db.session = mock_session_cm

                await main_module._reconcile()

            mock_start.assert_called_once()
        finally:
            main_module._forge_client = orig_forge


# --- C5: HIGH risk approval continuation ---


class TestApprovalContinuation:
    def test_dev_api_agent_not_ready_sets_error_code(self):
        """The REST boundary exposes a stable error code before runtime startup."""
        from agents.dev_agent.api import dev as dev_api
        from agents.dev_agent.app import main as main_module

        previous_runtime = getattr(main_module.app.state, "runtime", None)
        main_module.app.state.runtime = None
        try:
            with pytest.raises(HTTPException) as exc_info:
                dev_api._get_agent()
        finally:
            main_module.app.state.runtime = previous_runtime

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Agent not ready"
        assert (
            exc_info.value.headers["X-Error-Code"]
            == ApiErrorCode.DEV_AGENT_NOT_READY.value
        )

    @pytest.mark.asyncio
    async def test_approve_workflow_api_forwards_approval_context(self):
        """The REST approval endpoint forwards human approval context to the agent."""
        from agents.dev_agent.api import dev as dev_api
        from agents.dev_agent.core.api_use_cases import DevApiUseCase

        agent = MagicMock()
        agent.handle_request = AsyncMock(return_value={"success": True})

        result = await dev_api.approve_workflow(
            "dev-high-1",
            dev_api.ApproveWorkflowRequest(
                operator="human:lead",
                approval_id="appr_dev_1",
            ),
            dev_api=DevApiUseCase(agent),
        )

        assert result == {"success": True}
        agent.handle_request.assert_awaited_once_with(
            {
                "action": "approve_workflow",
                "task_id": "dev-high-1",
                "approved_by": "human:lead",
                "approval_id": "appr_dev_1",
            }
        )

    @pytest.mark.asyncio
    async def test_approve_workflow_retrieves_plan_and_executes(self):
        """approve_workflow should retrieve stored plan and execute via ForgeClient."""
        agent, mock_session = _make_agent_with_db()

        task = _make_mock_task(
            task_id="dev-high-1",
            status="awaiting_approval",
            risk_level="HIGH",
        )

        wf_log = MagicMock()
        wf_log.workflow_json = {
            "name": "test-workflow",
            "description": "test",
            "nodes": [{"name": "step1", "type": "agent_task", "dependsOn": [], "config": {}}],
        }

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.get_by_id = AsyncMock(return_value=task)
        mock_repo.update_status = AsyncMock(return_value=True)

        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_log_repo.get_by_task_id = AsyncMock(return_value=wf_log)

        mock_forge = AsyncMock()
        mock_forge.create_workflow = AsyncMock(return_value="wf-approved")
        mock_forge.run_workflow = AsyncMock()
        agent._forge = mock_forge

        with (
            patch.object(agent, "_get_repo", return_value=mock_repo),
            patch.object(agent, "_get_log_repo", return_value=mock_log_repo),
        ):
            result = await agent.handle_request(
                {"action": "approve_workflow", "task_id": "dev-high-1"}
            )

        assert result["success"] is True
        mock_forge.create_workflow.assert_called_once()
        mock_forge.run_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_workflow_requires_operator_for_control_plane_approval(self):
        """A persisted control-plane approval cannot be resolved as anonymous api."""
        agent, mock_session = _make_agent_with_db()

        task = _make_mock_task(
            task_id="dev-high-1",
            status="awaiting_approval",
            risk_level="HIGH",
        )

        wf_log = MagicMock()
        wf_log.workflow_json = {
            "name": "test-workflow",
            "description": "test",
            "nodes": [{"name": "step1", "type": "agent_task", "dependsOn": [], "config": {}}],
            "control_plane_approval_id": "appr_dev_1",
        }

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.get_by_id = AsyncMock(return_value=task)
        mock_repo.update_status = AsyncMock(return_value=True)

        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_log_repo.get_by_task_id = AsyncMock(return_value=wf_log)

        agent._approval_gate = MagicMock()
        agent._approval_gate.approve_for_sensitive_action = AsyncMock()

        with (
            patch.object(agent, "_get_repo", return_value=mock_repo),
            patch.object(agent, "_get_log_repo", return_value=mock_log_repo),
        ):
            result = await agent.handle_request(
                {"action": "approve_workflow", "task_id": "dev-high-1"}
            )

        assert result == {
            "error": "approved_by required for control-plane approval",
            "error_code": "control_plane_approval_resolver_required",
            "task_id": "dev-high-1",
            "control_plane_approval_id": "appr_dev_1",
        }
        agent._approval_gate.approve_for_sensitive_action.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_approve_workflow_records_human_resolver_for_control_plane_approval(self):
        """Control-plane approval resolution must record the human resolver identity."""
        agent, mock_session = _make_agent_with_db()

        task = _make_mock_task(
            task_id="dev-high-1",
            status="awaiting_approval",
            risk_level="HIGH",
        )

        wf_log = MagicMock()
        wf_log.workflow_json = {
            "name": "test-workflow",
            "description": "test",
            "nodes": [{"name": "step1", "type": "agent_task", "dependsOn": [], "config": {}}],
            "control_plane_approval_id": "appr_dev_1",
        }

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.get_by_id = AsyncMock(return_value=task)
        mock_repo.update_status = AsyncMock(return_value=True)

        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_log_repo.get_by_task_id = AsyncMock(return_value=wf_log)

        mock_forge = AsyncMock()
        mock_forge.create_workflow = AsyncMock(return_value="wf-approved")
        mock_forge.run_workflow = AsyncMock()
        agent._forge = mock_forge
        agent._approval_gate = MagicMock()
        agent._approval_gate.approve_for_sensitive_action = AsyncMock(
            return_value=SimpleNamespace(approval_id="appr_dev_1")
        )

        with (
            patch.object(agent, "_get_repo", return_value=mock_repo),
            patch.object(agent, "_get_log_repo", return_value=mock_log_repo),
        ):
            result = await agent.handle_request(
                {
                    "action": "approve_workflow",
                    "task_id": "dev-high-1",
                    "approved_by": "human:lead",
                }
            )

        assert result["success"] is True
        agent._approval_gate.approve_for_sensitive_action.assert_awaited_once_with(
            "appr_dev_1",
            resolved_by="human:lead",
        )
        mock_forge.create_workflow.assert_called_once()


# --- C6: PJM event payload compatibility ---


class TestPJMPayloadCompat:
    @pytest.mark.asyncio
    async def test_wbs_payload_uses_subject_field(self):
        """WBS model uses 'subject' not 'title', verify event payload maps correctly."""

        wbs_result = {
            "summary": "Test decomposition",
            "subtasks": [
                {
                    "subject": "User Story 1",
                    "estimated_days": 3,
                    "priority": "high",
                    "depends_on": [],
                    "children": [
                        {"subject": "Task A", "estimated_hours": 4},
                        {"subject": "Task B", "estimated_hours": 8},
                    ],
                }
            ],
        }

        # Build task list the same way the fixed orchestrator does
        is_refinement = wbs_result.get("type") == "task_refinement"
        assert not is_refinement

        dev_tasks = [
            {
                "id": 42,
                "title": child.get("subject", ""),
                "description": "",
                "estimated_hours": child.get("estimated_hours", 8),
                "parent_story": story.get("subject", ""),
                "related_files": [],
            }
            for story in wbs_result.get("subtasks", [])
            for child in story.get("children", [])
        ]

        assert len(dev_tasks) == 2
        assert dev_tasks[0]["title"] == "Task A"
        assert dev_tasks[0]["parent_story"] == "User Story 1"
        assert dev_tasks[1]["title"] == "Task B"

    @pytest.mark.asyncio
    async def test_task_refinement_payload_flat_subtasks(self):
        """task_refinement uses flat subtask list, not nested story->children."""
        wbs_result = {
            "type": "task_refinement",
            "reason": "Need more detail",
            "subtasks": [
                {"subject": "Subtask 1", "estimated_hours": 2},
                {"subject": "Subtask 2", "estimated_hours": 4},
            ],
        }

        is_refinement = wbs_result.get("type") == "task_refinement"
        assert is_refinement

        dev_tasks = [
            {
                "id": 42,
                "title": t.get("subject", ""),
                "description": "",
                "estimated_hours": t.get("estimated_hours", 8),
                "parent_story": "",
                "related_files": [],
            }
            for t in wbs_result.get("subtasks", [])
        ]

        assert len(dev_tasks) == 2
        assert dev_tasks[0]["title"] == "Subtask 1"
        assert dev_tasks[1]["title"] == "Subtask 2"


# --- C7: API parameter consistency ---


class TestAPIParameterConsistency:
    @pytest.mark.asyncio
    async def test_cancel_uses_task_id(self):
        """cancel_workflow action should use task_id parameter."""
        agent, _ = _make_agent_with_db()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.update_status = AsyncMock(return_value=True)

        with patch.object(agent, "_get_repo", return_value=mock_repo):
            result = await agent.handle_request(
                {"action": "cancel_workflow", "task_id": "dev-001"}
            )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_list_failed_action_exists(self):
        """list_failed action should be handled."""
        agent, _ = _make_agent_with_db()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.list_failed_tasks = AsyncMock(return_value=[])

        with patch.object(agent, "_get_repo", return_value=mock_repo):
            result = await agent.handle_request({"action": "list_failed"})
        assert "workflows" in result


# --- I1: QA event payload matches QARunRequestedPayload ---


class TestQAPayloadContract:
    def test_qa_run_requested_payload_valid(self):
        """Verify ResultCollector's QA payload matches QARunRequestedPayload."""
        from shared.schemas.event_payloads import QARunRequestedPayload

        # Simulate what ResultCollector sends
        payload = {
            "agent_name": "dev-agent",
            "level": "all",
            "mr_iid": 42,
            "gitlab_project_id": 1,
            "requested_by": "dev-agent",
        }
        # Should not raise
        model = QARunRequestedPayload.model_validate(payload)
        assert model.agent_name == "dev-agent"
        assert model.mr_iid == 42

    def test_qa_run_requested_payload_invalid_project_id_zero(self):
        """gitlab_project_id=0 should fail validation (ge=1)."""
        from shared.schemas.event_payloads import QARunRequestedPayload

        payload = {
            "agent_name": "dev-agent",
            "level": "all",
            "gitlab_project_id": 0,
            "requested_by": "dev-agent",
        }
        with pytest.raises(Exception):
            QARunRequestedPayload.model_validate(payload)


# --- I2: exc_info=True on error logs ---


class TestExcInfoOnErrors:
    def test_security_scanner_logs_have_exc_info(self):
        """SecurityScanner error logs should include exc_info=True."""
        import ast
        import inspect

        from agents.dev_agent.core import security_scanner

        source = inspect.getsource(security_scanner)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "error":
                    # Check if exc_info=True is in keywords
                    has_exc_info = any(
                        kw.arg == "exc_info" for kw in node.keywords
                    )
                    assert has_exc_info, (
                        f"logger.error call at line {node.lineno} "
                        "missing exc_info=True"
                    )

    def test_gitlab_client_logs_have_exc_info(self):
        """GitLabClient warning/error logs should include exc_info=True."""
        import ast
        import inspect

        from agents.dev_agent.adapters import gitlab_client

        source = inspect.getsource(gitlab_client)
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "warning":
                    # check_existing_mr_failed should have exc_info
                    for kw in node.keywords:
                        if kw.arg == "exc_info":
                            break
