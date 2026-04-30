"""Integration Test - Repository"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agents.qa_agent.db.repository import (
    AcceptanceResultRepository,
    AcceptanceRunRepository,
)


@pytest.mark.asyncio
async def test_run_repository_lifecycle(db_session: AsyncSession):
    repo = AcceptanceRunRepository(db_session)

    # 1. Create
    run = await repo.create(
        agent_name="pjm_agent",
        target_path="agents/pjm_agent",
        trigger="manual",
        level="all",
        l0_status="PASS",
        l1_status="PASS",
        l2_status="INFO",
        total_checks=10,
        l0_failure_count=0,
        l1_warning_count=0,
        duration_seconds=1.5,
        runner_exit_code=0,
        raw_report={"summary": {"total": 10}},
    )
    assert run.id is not None
    assert run.agent_name == "pjm_agent"

    # 2. Get by ID
    fetched = await repo.get_by_id(run.id)
    assert fetched is not None
    assert fetched.id == run.id

    # 3. List
    runs = await repo.list_runs(agent_name="pjm_agent")
    assert len(runs) == 1
    assert runs[0].id == run.id


@pytest.mark.asyncio
async def test_result_repository_batch_create(db_session: AsyncSession):
    run_repo = AcceptanceRunRepository(db_session)
    result_repo = AcceptanceResultRepository(db_session)

    run = await run_repo.create(
        agent_name="pjm_agent",
        target_path="agents/pjm_agent",
        trigger="manual",
        level="all",
        l0_status="FAIL",
        l1_status="WARN",
        l2_status="INFO",
        raw_report={},
    )

    results = [
        {
            "run_id": run.id,
            "level": "L0",
            "category": "security",
            "check_name": "no_secrets",
            "status": "FAIL",
            "severity": "critical",
            "is_blocking": True,
            "details": "Secret found in logs",
        },
        {
            "run_id": run.id,
            "level": "L1",
            "category": "architecture",
            "check_name": "decoupling",
            "status": "WARN",
            "severity": "medium",
            "is_blocking": False,
        },
    ]

    created = await result_repo.create_batch(results)
    assert len(created) == 2

    fetched = await result_repo.list_by_run_id(run.id)
    assert len(fetched) == 2
    assert fetched[0].check_name == "no_secrets"


@pytest.mark.asyncio
async def test_repository_get_stats(db_session: AsyncSession):
    run_repo = AcceptanceRunRepository(db_session)
    result_repo = AcceptanceResultRepository(db_session)

    # Create a PASS run
    await run_repo.create(
        agent_name="pjm_agent",
        target_path="agents/pjm_agent",
        trigger="manual",
        level="all",
        l0_status="PASS",
        l1_status="PASS",
        l2_status="INFO",
        duration_seconds=1.0,
        raw_report={},
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )

    # Create a FAIL run
    run2 = await run_repo.create(
        agent_name="pjm_agent",
        target_path="agents/pjm_agent",
        trigger="manual",
        level="all",
        l0_status="FAIL",
        l1_status="WARN",
        l2_status="INFO",
        duration_seconds=2.0,
        raw_report={},
        created_at=datetime.now(UTC),
    )

    await result_repo.create_batch(
        [
            {
                "run_id": run2.id,
                "level": "L0",
                "category": "security",
                "check_name": "secret_check",
                "status": "FAIL",
                "severity": "critical",
            },
            {
                "run_id": run2.id,
                "level": "L1",
                "category": "style",
                "check_name": "lint",
                "status": "WARN",
                "severity": "low",
            },
        ]
    )

    stats = await run_repo.get_stats(agent_name="pjm_agent", days=1)
    assert stats.total_runs == 2
    assert stats.pass_runs == 1
    assert stats.failed_runs == 1
    assert stats.avg_duration_seconds == 1.5
    assert len(stats.top_l0_failures) == 1
    assert stats.top_l0_failures[0].check == "secret_check"
    assert stats.top_l0_failures[0].count == 1
