"""
Unit Tests - SyncEngine

SyncEngine 的核心同步逻辑测试，使用 mock 的 op_client 和 bitable_service。
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.capabilities.sync.core.engine import SyncEngine


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


@pytest.mark.asyncio
async def test_sync_op_to_feishu_empty(engine, mock_op_client):
    """OP 无工作包时，同步应成功且 processed=0"""
    mock_op_client.get_work_packages.return_value = []
    result = await engine.sync_op_to_feishu()
    assert result["status"] == "success"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_sync_op_to_feishu_creates_mapping(engine, mock_op_client, mock_bitable):
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

    with patch("agents.capabilities.sync.core.engine.data_mapper") as mock_mapper:
        wp_data = MagicMock()
        wp_data.op_id = 100
        wp_data.project_id = 1
        wp_data.title = "测试任务"
        mock_mapper.op_to_work_package_data.return_value = wp_data
        mock_mapper.work_package_to_feishu_fields.return_value = {"任务名": "测试任务"}

        result = await engine.sync_op_to_feishu()

    assert result["status"] == "success"
    assert result["processed"] == 1
    mock_bitable.create_record.assert_called_once()


@pytest.mark.asyncio
async def test_sync_feishu_to_op_empty(engine, mock_bitable):
    """飞书无记录时，同步应成功且 processed=0"""
    mock_bitable.list_all_records.return_value = []
    result = await engine.sync_feishu_to_op()
    assert result["status"] == "success"
    assert result["processed"] == 0


@pytest.mark.asyncio
async def test_full_sync(engine, mock_op_client, mock_bitable):
    """全量同步应调用双向同步"""
    mock_op_client.get_work_packages.return_value = []
    mock_bitable.list_all_records.return_value = []

    result = await engine.full_sync()
    assert result["status"] == "success"
    assert result["total_processed"] == 0
    assert "op_to_feishu" in result
    assert "feishu_to_op" in result


@pytest.mark.asyncio
async def test_sync_op_to_feishu_handles_wp_error(engine, mock_op_client, mock_bitable):
    """单个工作包同步失败时，应记录错误并继续"""
    mock_op_client.get_work_packages.return_value = [
        {"id": 300, "subject": "失败任务", "_links": {}, "percentageDone": 0},
    ]

    with patch("agents.capabilities.sync.core.engine.data_mapper") as mock_mapper:
        mock_mapper.op_to_work_package_data.side_effect = ValueError("bad data")

        result = await engine.sync_op_to_feishu()

    assert result["status"] == "success"
    assert result["processed"] == 0
    assert len(result["errors"]) == 1
