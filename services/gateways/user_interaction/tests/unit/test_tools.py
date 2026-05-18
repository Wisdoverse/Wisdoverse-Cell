"""Unit tests for ToolExecutor handlers."""
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.gateways.user_interaction.core.config import UserInteractionCoreConfig


class FakeToolCardRenderer:
    def build_bitable_update_confirmation(
        self,
        *,
        title: str,
        record_id: str,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict:
        return {
            "kind": "update",
            "title": title or record_id,
            "field_lines": field_lines,
            "action_id": action_id,
            "is_group_chat": is_group_chat,
        }

    def build_bitable_create_confirmation(
        self,
        *,
        field_lines: str,
        action_id: str,
        is_group_chat: bool,
    ) -> dict:
        return {
            "kind": "create",
            "field_lines": field_lines,
            "action_id": action_id,
            "is_group_chat": is_group_chat,
        }


class FakeApprovalGate:
    def __init__(self):
        self.ensure_approved_for_sensitive_action = AsyncMock(return_value=None)


@pytest.fixture
def tool_dependencies():
    from services.gateways.user_interaction.core.tools import (
        ToolDependencies,
        configure_tool_dependencies,
    )

    mock_op = AsyncMock()
    mock_bitable = AsyncMock()
    mock_messenger = AsyncMock()
    mock_contact_lookup = AsyncMock()
    mock_event_publisher = AsyncMock()
    mock_event_publisher.publish_sync_trigger = AsyncMock(return_value=True)
    mock_card_operation_store = AsyncMock()
    mock_daily_progress_store = AsyncMock()
    card_renderer = FakeToolCardRenderer()
    approval_gate = FakeApprovalGate()
    configure_tool_dependencies(
        ToolDependencies(
            op_client=mock_op,
            bitable=mock_bitable,
            messenger=mock_messenger,
            contact_lookup=mock_contact_lookup,
            card_renderer=card_renderer,
            event_publisher=mock_event_publisher,
            card_operation_store=mock_card_operation_store,
            daily_progress_store=mock_daily_progress_store,
            approval_gate=approval_gate,
            config=UserInteractionCoreConfig.from_values(
                redis_url="redis://redis:6379/2",
                feishu_bitable_app_token="app-token",
                feishu_bitable_member_table_id="member-table",
                feishu_bitable_table_id="task-table",
                feishu_bitable_category_table_id="category-table",
                feishu_bitable_report_table_id="report-table",
            ),
        )
    )
    yield {
        "op": mock_op,
        "bitable": mock_bitable,
        "messenger": mock_messenger,
        "contact_lookup": mock_contact_lookup,
        "card_renderer": card_renderer,
        "event_publisher": mock_event_publisher,
        "card_operation_store": mock_card_operation_store,
        "daily_progress_store": mock_daily_progress_store,
        "approval_gate": approval_gate,
    }
    configure_tool_dependencies(None)


@pytest.fixture
def executor(tool_dependencies):
    from services.gateways.user_interaction.core.tools import ToolExecutor

    return ToolExecutor


@pytest.mark.asyncio
async def test_sync_now_publishes_event(executor, tool_dependencies):
    """sync_now publishes a sync.trigger command through the gateway publisher."""
    publisher = tool_dependencies["event_publisher"]

    result_str = await executor.execute("sync_now", {})

    result = json.loads(result_str)
    assert result["success"] is True
    assert "触发" in result["message"]
    publisher.publish_sync_trigger.assert_awaited_once_with(scope="full")


@pytest.mark.asyncio
async def test_sync_openproject_publishes_scoped_event(executor, tool_dependencies):
    """sync_openproject publishes an OpenProject-scoped sync.trigger command."""
    publisher = tool_dependencies["event_publisher"]

    result_str = await executor.execute("sync_openproject", {})

    result = json.loads(result_str)
    assert result["success"] is True
    publisher.publish_sync_trigger.assert_awaited_once_with(scope="openproject")


@pytest.mark.asyncio
async def test_sync_feishu_bitable_publishes_scoped_event(executor, tool_dependencies):
    """sync_feishu_bitable publishes a Bitable-scoped sync.trigger command."""
    publisher = tool_dependencies["event_publisher"]

    result_str = await executor.execute("sync_feishu_bitable", {})

    result = json.loads(result_str)
    assert result["success"] is True
    publisher.publish_sync_trigger.assert_awaited_once_with(scope="feishu_bitable")


@pytest.mark.asyncio
async def test_sync_now_publish_failure(executor, tool_dependencies):
    """Gateway publisher failures return an error."""
    publisher = tool_dependencies["event_publisher"]
    publisher.publish_sync_trigger.return_value = False

    result_str = await executor.execute("sync_now", {})

    result = json.loads(result_str)
    assert "error" in result or result.get("success") is not True
    assert "失败" in result.get("error", result.get("message", ""))


@pytest.mark.asyncio
async def test_list_card_operations_uses_injected_store(executor, tool_dependencies):
    """list_card_operations reads card-operation rows through the injected store."""
    store = tool_dependencies["card_operation_store"]
    store.query = AsyncMock(
        return_value=[
            SimpleNamespace(
                action="confirm_create",
                user_name="Alice",
                assignee_name="Bob",
                record_id="rec_1",
                result="success",
                created_at=datetime(2026, 5, 17, tzinfo=UTC),
                error_message="",
            )
        ]
    )

    result_str = await executor.execute(
        "list_card_operations",
        {"user_id": "ou_user_1", "action": "confirm_create", "limit": 5},
    )

    result = json.loads(result_str)
    assert result["total"] == 1
    assert result["operations"][0]["record_id"] == "rec_1"
    store.query.assert_awaited_once_with(
        user_id="ou_user_1",
        action="confirm_create",
        limit=5,
    )


@pytest.mark.asyncio
async def test_update_daily_progress_uses_injected_store(executor, tool_dependencies):
    """update_daily_progress updates progress through the injected store."""
    store = tool_dependencies["daily_progress_store"]
    bitable = tool_dependencies["bitable"]
    progress = SimpleNamespace(
        id=1,
        user_id="ou_user_1",
        date=datetime(2026, 5, 17, tzinfo=UTC).date(),
        task_record_id="rec_task_1",
        task_title="Build report",
    )
    store.update_progress = AsyncMock(return_value=progress)
    store.get_pending = AsyncMock(return_value=[SimpleNamespace(status="completed")])
    bitable.update_record = AsyncMock()

    result_str = await executor.execute(
        "update_daily_progress",
        {"progress_id": 1, "status": "completed", "note": "done"},
    )

    result = json.loads(result_str)
    assert result["success"] is True
    assert result["all_tasks_updated"] is True
    store.update_progress.assert_awaited_once_with(1, "completed", note="done")
    store.get_pending.assert_awaited_once_with("ou_user_1", progress.date)
    bitable.update_record.assert_awaited_once_with("rec_task_1", {"状态": "已完成"})


@pytest.mark.asyncio
async def test_execute_unknown_tool(executor):
    """Unknown tool names return an error response."""
    result_str = await executor.execute("nonexistent_tool", {})
    result = json.loads(result_str)
    assert "error" in result
    assert "未知工具" in result["error"]


@pytest.mark.asyncio
async def test_get_work_packages(executor, tool_dependencies):
    """get_work_packages calls the OpenProject port and returns formatted JSON."""
    mock_op = tool_dependencies["op"]
    mock_op.get_work_packages = AsyncMock(return_value=[
        {
            "id": 1,
            "subject": "测试任务",
            "_links": {
                "status": {"title": "New"},
                "assignee": {"title": "张三"},
            },
            "percentageDone": 30,
            "dueDate": "2026-04-01",
        },
        {
            "id": 2,
            "subject": "另一个任务",
            "_links": {
                "status": {"title": "In Progress"},
                "assignee": {"title": "李四"},
            },
            "percentageDone": 60,
            "dueDate": None,
        },
    ])

    result_str = await executor.execute("get_work_packages", {"project_id": 1, "limit": 10})

    result = json.loads(result_str)
    assert "work_packages" in result
    assert result["total"] == 2
    assert result["work_packages"][0]["id"] == 1
    assert result["work_packages"][0]["subject"] == "测试任务"
    assert result["work_packages"][0]["status"] == "New"
    assert result["work_packages"][0]["assignee"] == "张三"
    assert result["work_packages"][1]["progress"] == 60
    mock_op.get_work_packages.assert_called_once_with(project_id=1, page_size=10)


@pytest.mark.asyncio
async def test_update_progress_validates_range(executor):
    """Progress outside 0-100 returns an error."""
    result_str = await executor.execute("update_work_package_progress", {
        "work_package_id": 1,
        "progress": 150,
    })
    result = json.loads(result_str)
    assert "error" in result
    assert "0-100" in result["error"]


@pytest.mark.asyncio
async def test_add_bitable_field_requires_technical_approval(executor, tool_dependencies):
    """Bitable schema changes must fail closed without explicit approval context."""
    mock_bitable = tool_dependencies["bitable"]

    result_str = await executor.execute(
        "add_bitable_field",
        {"field_name": "New Field", "field_type": 1},
        context={"user_id": "user1"},
    )

    result = json.loads(result_str)
    assert "error" in result
    assert "技术审批" in result["error"]
    mock_bitable.create_field.assert_not_awaited()
    approval_gate = tool_dependencies["approval_gate"]
    approval_gate.ensure_approved_for_sensitive_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_bitable_field_allows_explicit_technical_approval(
    executor, tool_dependencies
):
    """Approved control-plane contexts may execute the schema mutation."""
    mock_bitable = tool_dependencies["bitable"]
    mock_bitable.create_field = AsyncMock(return_value={"field_id": "fld_1"})

    result_str = await executor.execute(
        "add_bitable_field",
        {"field_name": "New Field", "field_type": 1, "table_id": "tbl_1"},
        context={
            "user_id": "operator",
            "control_plane_approval_id": "appr_schema_1",
        },
    )

    result = json.loads(result_str)
    assert result["success"] is True
    assert result["field_id"] == "fld_1"
    mock_bitable.create_field.assert_awaited_once_with(
        "New Field",
        1,
        table_id="tbl_1",
    )
    approval_gate = tool_dependencies["approval_gate"]
    approval_gate.ensure_approved_for_sensitive_action.assert_awaited_once_with(
        "appr_schema_1",
    )


@pytest.mark.asyncio
async def test_add_bitable_field_accepts_tool_input_approval_id(
    executor, tool_dependencies
):
    """Tool input may carry the control-plane approval id."""
    mock_bitable = tool_dependencies["bitable"]
    mock_bitable.create_field = AsyncMock(return_value={"field_id": "fld_1"})

    result_str = await executor.execute(
        "add_bitable_field",
        {
            "field_name": "New Field",
            "field_type": 1,
            "table_id": "tbl_1",
            "approval_id": "appr_schema_2",
        },
        context={"user_id": "operator"},
    )

    result = json.loads(result_str)
    assert result["success"] is True
    approval_gate = tool_dependencies["approval_gate"]
    approval_gate.ensure_approved_for_sensitive_action.assert_awaited_once_with(
        "appr_schema_2",
    )


@pytest.mark.asyncio
async def test_add_bitable_field_rejects_unapproved_control_plane_id(
    executor, tool_dependencies
):
    """Rejected or pending control-plane approvals fail closed."""
    mock_bitable = tool_dependencies["bitable"]
    tool_dependencies["approval_gate"].ensure_approved_for_sensitive_action = AsyncMock(
        side_effect=PermissionError("approval_required"),
    )

    result_str = await executor.execute(
        "add_bitable_field",
        {"field_name": "New Field", "field_type": 1, "approval_id": "appr_pending"},
        context={"user_id": "operator"},
    )

    result = json.loads(result_str)
    assert "error" in result
    assert "技术审批" in result["error"]
    mock_bitable.create_field.assert_not_awaited()
    approval_gate = tool_dependencies["approval_gate"]
    approval_gate.ensure_approved_for_sensitive_action.assert_awaited_once_with(
        "appr_pending",
    )


@pytest.mark.asyncio
async def test_update_progress_rejects_negative_range(executor):
    """Negative progress values return an error."""

    result_str = await executor.execute("update_work_package_progress", {
        "work_package_id": 1,
        "progress": -5,
    })
    result = json.loads(result_str)
    assert "error" in result
    assert "0-100" in result["error"]


@pytest.mark.asyncio
async def test_list_bitable_records_uses_injected_primary_table_id(
    executor,
    tool_dependencies,
):
    """list_bitable_records annotates records with the injected primary table ID."""
    mock_bitable = tool_dependencies["bitable"]
    mock_bitable.list_records = AsyncMock(
        return_value={"items": [{"record_id": "rec_1", "fields": {"Name": "Task"}}]}
    )

    result_str = await executor.execute("list_bitable_records", {"limit": 5})

    result = json.loads(result_str)
    assert result["records"][0]["table_id"] == "task-table"
    mock_bitable.list_records.assert_awaited_once_with(page_size=5)


@pytest.mark.asyncio
async def test_list_member_records_uses_injected_member_table_config(
    executor,
    tool_dependencies,
):
    """list_member_records uses the injected app token and member table ID."""
    mock_bitable = tool_dependencies["bitable"]
    mock_bitable.list_records = AsyncMock(
        return_value={"items": [{"record_id": "rec_member", "fields": {"Name": "Alice"}}]}
    )

    result_str = await executor.execute("list_member_records", {"limit": 3})

    result = json.loads(result_str)
    assert result["records"][0]["table_id"] == "member-table"
    mock_bitable.list_records.assert_awaited_once_with(
        app_token="app-token",
        table_id="member-table",
        page_size=3,
    )


@pytest.mark.asyncio
async def test_query_pm_table_uses_injected_report_table_config(
    executor,
    tool_dependencies,
):
    """query_pm_table uses injected table IDs for PM side tables."""
    mock_bitable = tool_dependencies["bitable"]
    mock_bitable.list_records = AsyncMock(
        return_value={"items": [{"record_id": "rec_report", "fields": {"Week": "W18"}}]}
    )

    result_str = await executor.execute(
        "query_pm_table",
        {"table_name": "weekly_report", "limit": 2},
    )

    result = json.loads(result_str)
    assert result["table"] == "weekly_report"
    assert result["records"][0]["table_id"] == "report-table"
    mock_bitable.list_records.assert_awaited_once_with(
        app_token="app-token",
        table_id="report-table",
        page_size=2,
    )
