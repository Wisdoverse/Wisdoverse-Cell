"""
Integration Tests - SyncEngine (requires PostgreSQL)

Tests that exercise SyncEngine with real database operations.
"""
from unittest.mock import MagicMock, patch

import pytest

from shared.capabilities.sync.core.engine import SyncEngine
from shared.capabilities.sync.db.repository import SyncMappingRepository
from shared.capabilities.sync.db.sync_stores import (
    SqlAlchemyFeishuBitableSyncStore,
    SqlAlchemyOpenProjectSyncStore,
    SqlAlchemySyncLockStore,
)


@pytest.fixture
def mock_db_manager(db_session):
    """DatabaseManager wrapping real db_session"""
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
        openproject_store=SqlAlchemyOpenProjectSyncStore(mock_db_manager),
        lock_store=SqlAlchemySyncLockStore(mock_db_manager),
        feishu_bitable_store=SqlAlchemyFeishuBitableSyncStore(mock_db_manager),
        op_client=mock_op_client,
        bitable=mock_bitable,
    )


@pytest.mark.asyncio
async def test_sync_op_to_feishu_updates_existing(engine, mock_op_client, mock_bitable, db_session):
    """Update an existing Feishu record instead of creating a new one."""
    # Create an existing mapping first.
    repo = SyncMappingRepository(db_session)
    await repo.upsert(op_id=200, record_id="rec_existing", project_id=1, title="旧任务")

    mock_op_client.get_work_packages.return_value = [
        {
            "id": 200,
            "subject": "更新任务",
            "_links": {
                "project": {"href": "/api/v3/projects/1"},
                "status": {"title": "In Progress"},
                "type": {"title": "Task"},
                "assignee": {"title": "李四"},
            },
            "percentageDone": 50,
            "description": {"raw": ""},
        }
    ]

    with patch("shared.capabilities.sync.core.openproject_sync.data_mapper") as mock_mapper:
        wp_data = MagicMock()
        wp_data.op_id = 200
        wp_data.project_id = 1
        wp_data.title = "更新任务"
        wp_data.parent_id = None
        mock_mapper.op_to_work_package_data.return_value = wp_data
        mock_mapper.work_package_to_feishu_fields.return_value = {"任务名": "更新任务"}

        result = await engine.sync_op_to_feishu()

    assert result["status"] == "success"
    assert result["processed"] == 1
    mock_bitable.update_record.assert_called_once()
    mock_bitable.create_record.assert_not_called()


@pytest.mark.asyncio
async def test_sync_op_to_feishu_lock_held(engine, db_session):
    """Skip sync when the lock is held."""
    from shared.capabilities.sync.db.repository import SyncLockRepository

    lock_repo = SyncLockRepository(db_session)
    await lock_repo.acquire("sync_op_to_feishu", "other-agent")

    result = await engine.sync_op_to_feishu()
    assert result["status"] == "skipped"
    assert result["reason"] == "lock_held"
