"""Integration tests for PJM repositories."""

import pytest
from sqlalchemy.exc import IntegrityError

from agents.pjm_agent.db.repository import DecompositionRepository


@pytest.mark.integration
async def test_decomposition_repository_allows_write_lifecycle_statuses(db_session):
    repo = DecompositionRepository(db_session)
    record = await repo.create(
        wp_id=12001,
        project_id=34001,
        decompose_result={"summary": "Split feature", "subtasks": []},
    )

    assert record.status == "pending"

    assert await repo.update_status(12001, "writing", approved_by="human:pm")
    await db_session.refresh(record)
    assert record.status == "writing"
    assert record.approved_by == "human:pm"
    assert record.approved_at is not None

    assert await repo.update_status(12001, "write_failed")
    await db_session.refresh(record)
    assert record.status == "write_failed"


@pytest.mark.integration
async def test_decomposition_repository_rejects_unknown_status(db_session):
    repo = DecompositionRepository(db_session)
    await repo.create(
        wp_id=12002,
        project_id=34001,
        decompose_result={"summary": "Split feature", "subtasks": []},
    )

    with pytest.raises(IntegrityError):
        await repo.update_status(12002, "unknown")
