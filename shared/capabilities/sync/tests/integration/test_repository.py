"""
Unit Tests - SyncMappingRepository / SyncLockRepository

Tests data access CRUD and lock operations.
"""
import pytest

from shared.capabilities.sync.db.repository import (
    SubtaskMappingRepository,
    SyncLockRepository,
    SyncLogRepository,
    SyncMappingRepository,
)

# ── SyncMappingRepository ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_creates_new_mapping(db_session):
    """upsert should create a new mapping."""
    repo = SyncMappingRepository(db_session)
    mapping = await repo.upsert(op_id=1001, record_id="rec_aaa", project_id=5, title="新任务")

    assert mapping.id is not None
    assert mapping.op_work_package_id == 1001
    assert mapping.feishu_record_id == "rec_aaa"
    assert mapping.op_project_id == 5
    assert mapping.title == "新任务"


@pytest.mark.asyncio
async def test_upsert_updates_existing_mapping(db_session):
    """upsert should update an existing mapping."""
    repo = SyncMappingRepository(db_session)
    await repo.upsert(op_id=1002, record_id="rec_old", project_id=1, title="旧标题")
    updated = await repo.upsert(op_id=1002, record_id="rec_new", project_id=1, title="新标题")

    assert updated.feishu_record_id == "rec_new"
    assert updated.title == "新标题"


@pytest.mark.asyncio
async def test_get_by_op_id(db_session):
    """Query mappings by OpenProject work package ID."""
    repo = SyncMappingRepository(db_session)
    await repo.upsert(op_id=2001, record_id="rec_bbb")

    found = await repo.get_by_op_id(2001)
    assert found is not None
    assert found.feishu_record_id == "rec_bbb"

    not_found = await repo.get_by_op_id(9999)
    assert not_found is None


@pytest.mark.asyncio
async def test_get_by_record_id(db_session):
    """Query mappings by Feishu record ID."""
    repo = SyncMappingRepository(db_session)
    await repo.upsert(op_id=3001, record_id="rec_ccc")

    found = await repo.get_by_record_id("rec_ccc")
    assert found is not None
    assert found.op_work_package_id == 3001

    not_found = await repo.get_by_record_id("rec_nonexist")
    assert not_found is None


@pytest.mark.asyncio
async def test_list_all(db_session):
    """List all mappings."""
    repo = SyncMappingRepository(db_session)
    await repo.upsert(op_id=4001, record_id="rec_d1")
    await repo.upsert(op_id=4002, record_id="rec_d2")
    await repo.upsert(op_id=4003, record_id="rec_d3")

    all_mappings = await repo.list_all()
    assert len(all_mappings) == 3


# ── SyncLockRepository ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_acquire_lock_new(db_session):
    """First lock acquisition should succeed."""
    repo = SyncLockRepository(db_session)
    acquired = await repo.acquire("test_lock", "agent-1")
    assert acquired is True


@pytest.mark.asyncio
async def test_acquire_lock_already_held(db_session):
    """Lock acquisition should fail when the lock is already held."""
    repo = SyncLockRepository(db_session)
    await repo.acquire("test_lock_2", "agent-1")
    acquired = await repo.acquire("test_lock_2", "agent-2")
    assert acquired is False


@pytest.mark.asyncio
async def test_release_lock(db_session):
    """Another owner should acquire the lock after release."""
    repo = SyncLockRepository(db_session)
    await repo.acquire("test_lock_3", "agent-1")
    await repo.release("test_lock_3")
    acquired = await repo.acquire("test_lock_3", "agent-2")
    assert acquired is True


@pytest.mark.asyncio
async def test_acquire_expired_lock(db_session):
    """Expired locks should be acquirable again."""
    from datetime import UTC, datetime, timedelta

    from shared.capabilities.sync.models.sync import SyncLock

    # Insert an expired lock manually.
    expired_lock = SyncLock(
        lock_name="expired_lock",
        locked_by="old-agent",
        locked_at=datetime.now(UTC) - timedelta(minutes=20),
        expires_at=datetime.now(UTC) - timedelta(minutes=10),
        is_locked=True,
    )
    db_session.add(expired_lock)
    await db_session.flush()

    repo = SyncLockRepository(db_session)
    acquired = await repo.acquire("expired_lock", "new-agent")
    assert acquired is True


# ── SyncLogRepository ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_complete_log(db_session):
    """Create a log entry and mark it completed."""
    repo = SyncLogRepository(db_session)
    log = await repo.create("op_to_feishu", "started")
    assert log.id is not None
    assert log.status == "started"

    await repo.complete(log.id, records_processed=10)

    from sqlalchemy import select

    from shared.capabilities.sync.models.sync import SyncLog

    result = await db_session.execute(select(SyncLog).where(SyncLog.id == log.id))
    updated = result.scalar_one()
    assert updated.status == "completed"
    assert updated.records_processed == 10
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_complete_log_with_error(db_session):
    """Mark a log entry as failed."""
    repo = SyncLogRepository(db_session)
    log = await repo.create("feishu_to_op", "started")
    await repo.complete(log.id, records_processed=0, error="connection timeout")

    from sqlalchemy import select

    from shared.capabilities.sync.models.sync import SyncLog

    result = await db_session.execute(select(SyncLog).where(SyncLog.id == log.id))
    updated = result.scalar_one()
    assert updated.status == "failed"
    assert updated.error_message == "connection timeout"


# ── SubtaskMappingRepository ───────────────────────────────────────


@pytest.mark.asyncio
async def test_subtask_upsert_and_query(db_session):
    """Create and query a subtask mapping."""
    repo = SubtaskMappingRepository(db_session)
    mapping = await repo.upsert(parent_op_id=500, record_id="sub_001", name="子任务A", status="进行中")
    assert mapping.id is not None

    found = await repo.get_by_record_id("sub_001")
    assert found is not None
    assert found.subtask_name == "子任务A"

    by_parent = await repo.get_by_parent(500)
    assert len(by_parent) == 1


@pytest.mark.asyncio
async def test_subtask_upsert_updates(db_session):
    """Update a subtask mapping."""
    repo = SubtaskMappingRepository(db_session)
    await repo.upsert(parent_op_id=600, record_id="sub_002", name="旧名", status="未开始")
    updated = await repo.upsert(parent_op_id=600, record_id="sub_002", name="新名", status="完成")
    assert updated.subtask_name == "新名"
    assert updated.subtask_status == "完成"
