"""
Unit Tests - SyncEngine

SyncEngine 的核心同步逻辑测试，使用 mock 的 op_client 和 bitable_service。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.capabilities.sync.core import (
    FeishuBitableSyncEngine,
    OpenProjectSyncEngine,
)
from shared.capabilities.sync.core.engine import SyncEngine


@pytest.fixture
def mock_db_manager(db_session):
    """模拟 DatabaseManager，返回真实的 db_session"""
    from contextlib import asynccontextmanager

    manager = MagicMock()

    @asynccontextmanager
    async def _session():
        yield db_session

    manager.session = _session
    return manager


@pytest.fixture
def engine(mock_db_manager, mock_op_client, mock_bitable):
    return SyncEngine(
        db_manager=mock_db_manager,
        op_client=mock_op_client,
        bitable=mock_bitable,
    )


@pytest.fixture
def openproject_engine(mock_db_manager, mock_op_client, mock_bitable):
    return OpenProjectSyncEngine(
        db_manager=mock_db_manager,
        op_client=mock_op_client,
        bitable=mock_bitable,
    )


@pytest.fixture
def feishu_bitable_engine(mock_db_manager, mock_op_client, mock_bitable):
    return FeishuBitableSyncEngine(
        db_manager=mock_db_manager,
        op_client=mock_op_client,
        bitable=mock_bitable,
    )


@pytest.mark.asyncio
async def test_openproject_sync_empty(openproject_engine, mock_op_client):
    """OP 无工作包时，同步应成功且 processed=0"""
    mock_op_client.get_work_packages.return_value = []
    result = await openproject_engine.sync_to_bitable()
    assert result["status"] == "success"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_openproject_sync_creates_mapping(
    openproject_engine,
    mock_op_client,
    mock_bitable,
):
    """OP 有新工作包时，应创建飞书记录和映射"""
    mock_op_client.get_work_packages.return_value = [
        {
            "id": 100,
            "subject": "测试任务",
            "_links": {
                "project": {"href": "/api/v3/projects/1"},
                "status": {"title": "New"},
                "type": {"title": "Task"},
                "assignee": {"title": "张三"},
            },
            "percentageDone": 0,
            "description": {"raw": "描述"},
        }
    ]
    mock_bitable.create_record.return_value = "rec_001"

    with patch("shared.capabilities.sync.core.openproject_sync.data_mapper") as mock_mapper:
        wp_data = MagicMock()
        wp_data.op_id = 100
        wp_data.project_id = 1
        wp_data.title = "测试任务"
        wp_data.parent_id = None
        mock_mapper.op_to_work_package_data.return_value = wp_data
        mock_mapper.work_package_to_feishu_fields.return_value = {"任务名": "测试任务"}

        result = await openproject_engine.sync_to_bitable()

    assert result["status"] == "success"
    assert result["processed"] == 1
    mock_bitable.create_record.assert_called_once()


@pytest.mark.asyncio
async def test_openproject_sync_preserves_trace_id_on_decompose_event(
    mock_db_manager,
    mock_op_client,
    mock_bitable,
):
    """OpenProject-to-PJM handoff events inherit the sync trigger trace ID."""
    event_bus = AsyncMock()
    engine = OpenProjectSyncEngine(
        db_manager=mock_db_manager,
        op_client=mock_op_client,
        bitable=mock_bitable,
        event_bus=event_bus,
        decompose_filter=lambda project_id: project_id == 1,
    )
    mock_op_client.get_work_packages.return_value = [
        {
            "id": 101,
            "subject": "Feature X",
            "_links": {
                "project": {"title": "Project"},
                "status": {"title": "New"},
                "type": {"title": "Feature"},
                "assignee": {"href": "/api/v3/users/7"},
            },
            "percentageDone": 0,
            "description": {"raw": "Description"},
        }
    ]
    mock_bitable.create_record.return_value = "rec_101"

    with patch("shared.capabilities.sync.core.openproject_sync.data_mapper") as mock_mapper:
        wp_data = MagicMock()
        wp_data.op_id = 101
        wp_data.project_id = 1
        wp_data.title = "Feature X"
        wp_data.description = "Description"
        wp_data.parent_id = None
        wp_data.assignee = "Owner"
        mock_mapper.op_to_work_package_data.return_value = wp_data
        mock_mapper.work_package_to_feishu_fields.return_value = {"task": "Feature X"}

        result = await engine.sync_to_bitable(trace_id="trace-sync-op")

    assert result["status"] == "success"
    published_event = event_bus.publish.await_args.args[0]
    assert published_event.event_type == "sync.task-needs-decompose"
    assert published_event.metadata.trace_id == "trace-sync-op"


@pytest.mark.asyncio
async def test_feishu_bitable_sync_empty(feishu_bitable_engine, mock_bitable):
    """飞书无记录时，同步应成功且 processed=0"""
    mock_bitable.list_all_records.return_value = []
    result = await feishu_bitable_engine.sync_progress_to_openproject()
    assert result["status"] == "success"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_full_sync(engine, mock_op_client, mock_bitable):
    """Full sync should call both split sync boundaries."""
    mock_op_client.get_work_packages.return_value = []
    mock_bitable.list_all_records.return_value = []

    result = await engine.full_sync()
    assert result["status"] == "success"
    assert result["total_processed"] == 0
    assert "op_to_feishu" in result
    assert "feishu_to_op" in result


@pytest.mark.asyncio
async def test_openproject_sync_handles_wp_error(
    openproject_engine,
    mock_op_client,
    mock_bitable,
):
    """单个工作包同步失败时，应记录错误并继续"""
    mock_op_client.get_work_packages.return_value = [
        {"id": 300, "subject": "失败任务", "_links": {}, "percentageDone": 0},
    ]

    with patch("shared.capabilities.sync.core.openproject_sync.data_mapper") as mock_mapper:
        mock_mapper.op_to_work_package_data.side_effect = ValueError("bad data")

        result = await openproject_engine.sync_to_bitable()

    assert result["status"] == "success"
    assert result["processed"] == 0
    assert len(result["errors"]) == 1
