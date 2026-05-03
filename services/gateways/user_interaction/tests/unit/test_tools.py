"""
Unit Tests - ToolExecutor

测试工具执行器的各个工具处理函数。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from shared.infra import event_bus as _event_bus_mod


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
    configure_tool_dependencies(
        ToolDependencies(
            op_client=mock_op,
            bitable=mock_bitable,
            messenger=mock_messenger,
            contact_lookup=mock_contact_lookup,
        )
    )
    yield {
        "op": mock_op,
        "bitable": mock_bitable,
        "messenger": mock_messenger,
        "contact_lookup": mock_contact_lookup,
    }
    configure_tool_dependencies(None)


@pytest.fixture
def executor(tool_dependencies):
    from services.gateways.user_interaction.core.tools import ToolExecutor

    return ToolExecutor


@pytest.mark.asyncio
async def test_sync_now_publishes_event(executor):
    """sync_now 应通过 event_bus 发布 sync.trigger 事件"""
    mock_bus = AsyncMock()
    mock_bus.connect = AsyncMock()
    mock_bus.publish = AsyncMock(return_value=True)

    with patch.object(_event_bus_mod, "event_bus", mock_bus):
        result_str = await executor.execute("sync_now", {})

    result = json.loads(result_str)
    assert result["success"] is True
    assert "触发" in result["message"]
    mock_bus.connect.assert_called_once()
    mock_bus.publish.assert_called_once()

    # 验证发布的事件类型
    published_event = mock_bus.publish.call_args[0][0]
    assert published_event.event_type == "sync.trigger"
    assert published_event.source_agent == "chat-agent"


@pytest.mark.asyncio
async def test_sync_now_publish_failure(executor):
    """event_bus publish 失败时应返回错误"""
    mock_bus = AsyncMock()
    mock_bus.connect = AsyncMock()
    mock_bus.publish = AsyncMock(return_value=False)

    with patch.object(_event_bus_mod, "event_bus", mock_bus):
        result_str = await executor.execute("sync_now", {})

    result = json.loads(result_str)
    assert "error" in result or result.get("success") is not True
    # publish 返回 False 时应返回失败消息
    assert "失败" in result.get("error", result.get("message", ""))


@pytest.mark.asyncio
async def test_execute_unknown_tool(executor):
    """未知工具名应返回错误响应"""
    result_str = await executor.execute("nonexistent_tool", {})
    result = json.loads(result_str)
    assert "error" in result
    assert "未知工具" in result["error"]


@pytest.mark.asyncio
async def test_get_work_packages(executor, tool_dependencies):
    """get_work_packages 应调用 OP client 并返回格式化的 JSON"""
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
    """进度超出 0-100 范围应返回错误"""
    # 测试超过 100
    result_str = await executor.execute("update_work_package_progress", {
        "work_package_id": 1,
        "progress": 150,
    })
    result = json.loads(result_str)
    assert "error" in result
    assert "0-100" in result["error"]

    # 测试低于 0
    result_str = await executor.execute("update_work_package_progress", {
        "work_package_id": 1,
        "progress": -5,
    })
    result = json.loads(result_str)
    assert "error" in result
    assert "0-100" in result["error"]
