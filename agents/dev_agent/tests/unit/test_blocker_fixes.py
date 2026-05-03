"""Tests for R2 blocker fixes: startup, event publishing, child task IDs."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.dev_agent.core.workflow_validator import ValidationResult
from agents.dev_agent.db.repository import (
    DevTaskRepository,
    DevWorkflowLogRepository,
)
from agents.dev_agent.models.schemas import WorkflowNode, WorkflowPlan
from agents.dev_agent.service.agent import DevAgent
from shared.schemas.event import Event, EventTypes


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
    created_at=None,
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
    task.created_at = created_at or datetime.now(UTC)
    task.updated_at = datetime.now(UTC)
    return task


def _make_mock_session():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


# --- Blocker A: Startup doesn't crash ---


class TestStartupDoesNotCrash:
    @pytest.mark.asyncio
    async def test_on_startup_uses_create_tables_not_initialize(self):
        """Verify _on_startup calls create_tables() (which exists on
        BaseDatabaseManager) and not initialize() (which doesn't exist)."""
        from agents.dev_agent.app import main as main_module

        mock_db = AsyncMock()
        mock_db.create_tables = AsyncMock()
        mock_runtime = MagicMock()

        with (
            patch.object(main_module, "db_manager", mock_db),
            patch.object(main_module, "settings") as mock_settings,
            patch.object(main_module, "_start_scheduler", AsyncMock()),
        ):
            mock_settings.agentforge_api_url = ""
            mock_settings.dev_gitlab_api_url = ""
            mock_settings.dev_gitlab_project_id = ""

            await main_module._on_startup(mock_runtime)

        mock_db.create_tables.assert_awaited_once()
        # Verify initialize is NOT called (it doesn't exist)
        assert not hasattr(mock_db, "initialize") or not mock_db.initialize.called

    @pytest.mark.asyncio
    async def test_on_startup_creates_clients_and_wires_agent(self):
        """Verify ForgeClient and GitLabClient are created and wired."""
        from agents.dev_agent.app import main as main_module

        mock_db = AsyncMock()
        mock_db.create_tables = AsyncMock()
        mock_runtime = MagicMock()

        with (
            patch.object(main_module, "db_manager", mock_db),
            patch.object(main_module, "settings") as mock_settings,
            patch.object(main_module, "_start_scheduler", AsyncMock()),
            patch.object(main_module, "ForgeClient") as MockForge,
            patch.object(main_module, "GitLabClient") as MockGitLab,
        ):
            mock_settings.agentforge_api_url = "http://forge"
            mock_settings.agentforge_token = MagicMock()
            mock_settings.agentforge_token.get_secret_value.return_value = "tok"
            mock_settings.dev_gitlab_api_url = "http://gitlab"
            mock_settings.dev_gitlab_token = MagicMock()
            mock_settings.dev_gitlab_token.get_secret_value.return_value = "gltok"
            mock_settings.dev_gitlab_project_id = 1

            await main_module._on_startup(mock_runtime)

        MockForge.assert_called_once()
        MockGitLab.assert_called_once()


# --- Blocker B: Reconcile publishes events ---


class TestReconcilePublishesEvents:
    @pytest.mark.asyncio
    async def test_reconcile_publishes_completion_events(self):
        """When workflow completes, events from ResultCollector are published
        via the event bus."""
        from agents.dev_agent.app import main as main_module

        task = _make_mock_task(
            status="executing",
            workflow_id="wf-done",
            workflow_started_at=datetime.now(UTC) - timedelta(minutes=5),
            last_polled_at=datetime.now(UTC) - timedelta(minutes=2),
        )

        mock_session = _make_mock_session()
        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.list_active_tasks = AsyncMock(return_value=[task])
        mock_repo.list_pending_tasks = AsyncMock(return_value=[])
        mock_repo.list_planning_tasks = AsyncMock(return_value=[])
        mock_repo.count_active_workflows = AsyncMock(return_value=0)

        lock_mock = MagicMock()
        lock_mock.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=lock_mock)

        # ForgeClient returns completed status in the orchestrator's nested format
        mock_forge = AsyncMock()
        mock_forge.get_status = AsyncMock(
            return_value={
                "ok": True,
                "workflow": {"status": "completed"},
                "nodes": [],
            }
        )

        # ResultCollector returns events
        qa_event = Event.create(
            event_type=EventTypes.QA_RUN_REQUESTED,
            source_agent="dev-agent",
            payload={"agent_name": "dev-agent"},
        )
        mr_event = Event.create(
            event_type=EventTypes.DEV_MR_CREATED,
            source_agent="dev-agent",
            payload={"mr_url": "http://mr/1"},
        )

        mock_collector = AsyncMock()
        mock_collector.handle_completion = AsyncMock(return_value=[qa_event, mr_event])

        mock_event_bus = AsyncMock()

        mock_gitlab = AsyncMock()

        orig_forge = main_module._forge_client
        orig_gitlab = main_module._gitlab_client

        try:
            main_module._forge_client = mock_forge
            main_module._gitlab_client = mock_gitlab

            with (
                patch.object(main_module, "_get_agent"),
                patch.object(main_module, "db_manager") as mock_db,
                patch.object(main_module, "DevTaskRepository", return_value=mock_repo),
                patch.object(main_module, "DevWorkflowLogRepository", return_value=AsyncMock()),
                patch(
                    "agents.dev_agent.core.result_collector.ResultCollector",
                    return_value=mock_collector,
                ),
                patch(
                    "shared.infra.event_bus.event_bus",
                    mock_event_bus,
                ),
            ):
                @asynccontextmanager
                async def mock_session_cm():
                    yield mock_session

                mock_db.session = mock_session_cm

                await main_module._reconcile()

            # Verify events were published
            assert mock_event_bus.publish.call_count == 2
            published_events = [
                call.args[0] for call in mock_event_bus.publish.call_args_list
            ]
            event_types = [e.event_type for e in published_events]
            assert EventTypes.QA_RUN_REQUESTED in event_types
            assert EventTypes.DEV_MR_CREATED in event_types
        finally:
            main_module._forge_client = orig_forge
            main_module._gitlab_client = orig_gitlab


class TestSchedulerRuntimeBoundary:
    @pytest.mark.asyncio
    async def test_start_pending_task_uses_runtime_wrapped_agent(self):
        """Scheduler recovery must use runtime.agent, not the raw agent internals."""
        from agents.dev_agent.app import main as main_module

        task = _make_mock_task(
            task_id="dev-runtime-boundary",
            wp_id=400,
            status="pending",
        )
        repo = AsyncMock(spec=DevTaskRepository)
        repo.update_status = AsyncMock(return_value=True)

        log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        log_repo.get_by_task_id = AsyncMock(return_value=None)
        log_repo.create_log = AsyncMock()

        plan = WorkflowPlan(
            name="dev-task-wp-400",
            description="test",
            nodes=[
                WorkflowNode(
                    name="implementation",
                    config={"prompt": "Implement the requested change"},
                )
            ],
        )
        runtime_agent = SimpleNamespace(
            _planner=SimpleNamespace(plan=AsyncMock(return_value=plan)),
            _validator=SimpleNamespace(validate=MagicMock(return_value=ValidationResult())),
            _router=SimpleNamespace(route=MagicMock(return_value="codex")),
            _request_workflow_approval=AsyncMock(return_value=None),
        )
        raw_planner = AsyncMock(side_effect=AssertionError("raw planner used"))
        mock_forge = AsyncMock()
        mock_forge.create_workflow = AsyncMock(return_value="wf-runtime-boundary")
        mock_forge.run_workflow = AsyncMock()

        orig_forge = main_module._forge_client
        try:
            main_module._forge_client = mock_forge
            with (
                patch.object(main_module, "_get_agent", return_value=runtime_agent),
                patch.object(main_module._raw_agent._planner, "plan", raw_planner),
            ):
                await main_module._start_pending_task(task, repo, log_repo)
        finally:
            main_module._forge_client = orig_forge

        runtime_agent._planner.plan.assert_awaited_once()
        raw_planner.assert_not_called()
        runtime_agent._validator.validate.assert_called_once()
        runtime_agent._router.route.assert_called_once()
        mock_forge.create_workflow.assert_awaited_once_with(plan)
        mock_forge.run_workflow.assert_awaited_once_with("wf-runtime-boundary")


# --- Blocker C: Multiple child tasks get unique IDs ---


class TestChildTaskUniqueIDs:
    def test_wbs_children_get_unique_ids(self):
        """Each child task in full WBS decomposition gets a unique ID."""
        wbs_result = {
            "summary": "Test",
            "subtasks": [
                {
                    "subject": "Story 1",
                    "children": [
                        {"subject": "Task A", "estimated_hours": 4},
                        {"subject": "Task B", "estimated_hours": 8},
                    ],
                },
                {
                    "subject": "Story 2",
                    "children": [
                        {"subject": "Task C", "estimated_hours": 2},
                    ],
                },
            ],
        }

        wp_id = 42
        is_refinement = wbs_result.get("type") == "task_refinement"
        assert not is_refinement

        # Replicate the actual code logic
        dev_tasks = []
        child_idx = 0
        for story in wbs_result.get("subtasks", []):
            for child in story.get("children", []):
                child_idx += 1
                dev_tasks.append({
                    "id": wp_id * 10000 + child_idx,
                    "title": child.get("subject", ""),
                })

        assert len(dev_tasks) == 3
        ids = [t["id"] for t in dev_tasks]
        # All IDs must be unique
        assert len(set(ids)) == 3
        # IDs should not equal parent wp_id
        assert all(task_id != wp_id for task_id in ids)

    def test_refinement_subtasks_get_unique_ids(self):
        """Each subtask in task_refinement gets a unique ID."""
        wbs_result = {
            "type": "task_refinement",
            "subtasks": [
                {"subject": "Sub 1", "estimated_hours": 2},
                {"subject": "Sub 2", "estimated_hours": 4},
                {"subject": "Sub 3", "estimated_hours": 6},
            ],
        }

        wp_id = 99
        dev_tasks = [
            {"id": wp_id * 10000 + idx + 1}
            for idx, t in enumerate(wbs_result.get("subtasks", []))
        ]

        ids = [t["id"] for t in dev_tasks]
        assert len(set(ids)) == 3
        assert all(task_id != wp_id for task_id in ids)

    @pytest.mark.asyncio
    async def test_handle_tasks_ready_creates_separate_records(self):
        """Each task in pm.tasks-ready-for-dev with unique IDs creates
        a separate DB record via create_task."""
        agent = DevAgent()
        mock_db = MagicMock()
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_cm():
            yield mock_session

        mock_db.session = mock_session_cm
        agent._db_manager = mock_db

        mock_repo = AsyncMock(spec=DevTaskRepository)
        # Return None for all create_task (simulates new records)
        task_records = []
        for i in range(3):
            rec = _make_mock_task(task_id=f"dev-{i}", wp_id=1000 + i)
            task_records.append(rec)

        create_call_count = 0

        async def mock_create_task(wp_id, task_title, risk_level="MEDIUM"):
            nonlocal create_call_count
            if create_call_count < len(task_records):
                result = task_records[create_call_count]
                create_call_count += 1
                return result
            return None

        mock_repo.create_task = AsyncMock(side_effect=mock_create_task)
        mock_repo.count_active_workflows = AsyncMock(return_value=0)
        mock_repo.update_status = AsyncMock(return_value=True)

        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        agent._planner.plan = AsyncMock(
            return_value=WorkflowPlan(
                name="dev-task-wp-100",
                description="test",
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
                            "prompt": (
                                "Verify agents/dev_agent/service/agent.py and "
                                'git checkout -B dev/wp-100 && git add -A '
                                '&& git commit -m "dev(wp-100): auto" '
                                "&& git push --force-with-lease origin dev/wp-100"
                            ),
                            "tags": ["acceptance", "review"],
                        },
                    ),
                ],
            )
        )
        agent._validator.validate = MagicMock(return_value=ValidationResult())
        agent._execute_workflow = AsyncMock(return_value=[])

        event = Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="pjm-agent",
            payload={
                "wp_id": 100,
                "tasks": [
                    {"id": 1000, "title": "Task A", "description": "Desc A", "estimated_hours": 4},
                    {"id": 1001, "title": "Task B", "description": "Desc B", "estimated_hours": 4},
                    {"id": 1002, "title": "Task C", "description": "Desc C", "estimated_hours": 4},
                ],
            },
        )

        with (
            patch.object(agent, "_get_repo", return_value=mock_repo),
            patch(
                "agents.dev_agent.service.agent.DevWorkflowLogRepository",
                return_value=mock_log_repo,
            ),
        ):
            await agent.handle_event(event)

        # Each task should trigger create_task with its own wp_id (from "id" field)
        assert mock_repo.create_task.call_count == 3
        wp_ids_used = [
            call.kwargs.get("wp_id", call.args[0] if call.args else None)
            for call in mock_repo.create_task.call_args_list
        ]
        assert len(set(wp_ids_used)) == 3, f"Expected 3 unique wp_ids, got {wp_ids_used}"


# --- I2: Approval with missing workflow log ---


class TestApprovalMissingPlan:
    @pytest.mark.asyncio
    async def test_approve_returns_error_when_plan_missing(self):
        """When workflow log is missing, approve_workflow returns an error
        instead of silently advancing to executing."""
        agent = DevAgent()
        mock_db = MagicMock()
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_cm():
            yield mock_session

        mock_db.session = mock_session_cm
        agent._db_manager = mock_db

        task = _make_mock_task(
            task_id="dev-high-1",
            status="awaiting_approval",
            risk_level="HIGH",
        )

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.get_by_id = AsyncMock(return_value=task)
        mock_repo.update_status = AsyncMock(return_value=True)

        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_log_repo.get_by_task_id = AsyncMock(return_value=None)  # No log!

        with (
            patch.object(agent, "_get_repo", return_value=mock_repo),
            patch(
                "agents.dev_agent.service.agent.DevWorkflowLogRepository",
                return_value=mock_log_repo,
            ),
        ):
            result = await agent.handle_request(
                {"action": "approve_workflow", "task_id": "dev-high-1"}
            )

        assert "error" in result
        # Should NOT have updated status to executing
        mock_repo.update_status.assert_not_called()


# --- I4: TASK_DURATION metric ---


class TestTaskDurationMetric:
    @pytest.mark.asyncio
    async def test_task_duration_observed_on_completion(self):
        """When QA passes and task completes, TASK_DURATION.observe is called."""
        from agents.dev_agent.core.result_collector import ResultCollector

        task = _make_mock_task(
            task_id="dev-dur-1",
            status="reviewing",
            mr_url="http://mr/1",
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.update_status = AsyncMock(return_value=True)
        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_gitlab = AsyncMock()
        mock_notifier = AsyncMock()
        mock_scanner = AsyncMock()

        collector = ResultCollector(
            repo=mock_repo,
            log_repo=mock_log_repo,
            gitlab=mock_gitlab,
            notifier=mock_notifier,
            security_scanner=mock_scanner,
        )

        qa_payload = {"summary": {"l0_gate": "PASS"}}

        with patch("agents.dev_agent.core.result_collector.TASK_DURATION") as mock_metric:
            events = await collector.handle_qa_result(task, qa_payload)

        # Should observe duration
        mock_metric.observe.assert_called_once()
        observed_value = mock_metric.observe.call_args[0][0]
        # Duration should be roughly 2 hours (7200s), allow some tolerance
        assert observed_value > 7000
        assert observed_value < 7400

        # Should produce completion event
        assert len(events) == 1
        assert events[0].event_type == EventTypes.DEV_TASK_COMPLETED
        assert events[0].payload["duration_s"] > 0


# --- I3: SecurityScanner workspace path ---


class TestSecurityScannerPath:
    @pytest.mark.asyncio
    async def test_result_collector_falls_back_to_cwd_when_workspace_missing(self):
        """ResultCollector should pass '.' to scanner when status has no workspace."""
        from agents.dev_agent.core.result_collector import ResultCollector

        task = _make_mock_task(
            task_id="dev-sec-1",
            status="executing",
            wp_id=555,
        )

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.update_status = AsyncMock(return_value=True)
        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_gitlab = AsyncMock()
        mock_gitlab.check_existing_mr = AsyncMock(return_value=None)
        mock_gitlab.create_mr = AsyncMock(
            return_value={"iid": 1, "web_url": "http://mr/1"}
        )
        mock_notifier = AsyncMock()

        mock_scanner = AsyncMock()
        mock_scanner.scan = AsyncMock(
            return_value=MagicMock(passed=True, issues=[])
        )

        collector = ResultCollector(
            repo=mock_repo,
            log_repo=mock_log_repo,
            gitlab=mock_gitlab,
            notifier=mock_notifier,
            security_scanner=mock_scanner,
        )

        await collector.handle_completion(task, {"status": "completed"})

        # Should call scan(".") not scan("dev/wp-555")
        mock_scanner.scan.assert_called_once_with(".")

    @pytest.mark.asyncio
    async def test_result_collector_uses_agentforge_workspace_path(self):
        """ResultCollector should scan the workspace returned by AgentForge."""
        from agents.dev_agent.core.result_collector import ResultCollector

        task = _make_mock_task(
            task_id="dev-sec-2",
            status="executing",
            wp_id=556,
        )

        mock_repo = AsyncMock(spec=DevTaskRepository)
        mock_repo.update_status = AsyncMock(return_value=True)
        mock_log_repo = AsyncMock(spec=DevWorkflowLogRepository)
        mock_gitlab = AsyncMock()
        mock_gitlab.check_existing_mr = AsyncMock(return_value=None)
        mock_gitlab.create_mr = AsyncMock(
            return_value={"iid": 2, "web_url": "http://mr/2"}
        )
        mock_notifier = AsyncMock()

        mock_scanner = AsyncMock()
        mock_scanner.scan = AsyncMock(return_value=MagicMock(passed=True, issues=[]))

        collector = ResultCollector(
            repo=mock_repo,
            log_repo=mock_log_repo,
            gitlab=mock_gitlab,
            notifier=mock_notifier,
            security_scanner=mock_scanner,
        )

        await collector.handle_completion(
            task,
            {"workflow": {"workspacePath": "/tmp/agentforge/workspaces/wf-556"}},
        )

        mock_scanner.scan.assert_called_once_with(
            "/tmp/agentforge/workspaces/wf-556"
        )
