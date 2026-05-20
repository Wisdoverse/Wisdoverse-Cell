"""Tests for the dedicated control-plane artifact store."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.agent_run_store import SqlAlchemyControlPlaneAgentRunStore
from shared.control_plane.artifact_store import SqlAlchemyControlPlaneArtifactStore
from shared.control_plane.company_store import SqlAlchemyControlPlaneCompanyStore
from shared.control_plane.goal_store import SqlAlchemyControlPlaneGoalStore
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    Artifact,
    ArtifactType,
    AuditEvent,
    CompanyContext,
    Goal,
    GoalStatus,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from shared.control_plane.tables import AuditEventTable
from shared.control_plane.work_item_store import SqlAlchemyControlPlaneWorkItemStore


@pytest.mark.asyncio
async def test_artifact_store_owns_artifact_queries(
    db_session: AsyncSession,
) -> None:
    company_store = SqlAlchemyControlPlaneCompanyStore(db_session)
    goal_store = SqlAlchemyControlPlaneGoalStore(db_session)
    work_item_store = SqlAlchemyControlPlaneWorkItemStore(db_session)
    run_store = SqlAlchemyControlPlaneAgentRunStore(db_session)
    artifact_store = SqlAlchemyControlPlaneArtifactStore(db_session)

    company = await company_store.create_company(
        CompanyContext(company_id="cmp_artifact_store", name="Wisdoverse Cell")
    )
    goal = await goal_store.create_goal(
        Goal(
            company_id=company.company_id,
            title="Make artifacts explicit",
            status=GoalStatus.ACTIVE,
        )
    )
    work_item = await work_item_store.create_work_item(
        WorkItem(
            company_id=company.company_id,
            goal_id=goal.goal_id,
            title="Extract artifact persistence",
            status=WorkItemStatus.READY,
            priority=WorkItemPriority.HIGH,
        )
    )
    run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_artifact_store",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
        )
    )
    artifact = await artifact_store.create_artifact(
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="Artifact store extraction report",
            uri="s3://wisdoverse-cell/artifacts/report.md",
            content_hash="sha256:artifact-store",
            run_id=run.run_id,
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            created_by_agent_id="dev-agent",
            metadata={"source": "artifact-store"},
        )
    )
    other_run = await run_store.create_agent_run(
        AgentRun(
            company_id=company.company_id,
            agent_id="qa-agent",
            status=AgentRunStatus.RUNNING,
            trace_id="trace_artifact_store_other",
        )
    )
    other_artifact = await artifact_store.create_artifact(
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.CODE_PATCH,
            title="Boundary assertion patch",
            uri="git://wisdoverse-cell/pull/next.patch",
            run_id=other_run.run_id,
            created_by_agent_id="qa-agent",
        )
    )

    rows = await artifact_store.list_artifacts(
        company_id=company.company_id,
        artifact_type=ArtifactType.REPORT.value,
        run_id=run.run_id,
        goal_id=goal.goal_id,
        work_item_id=work_item.work_item_id,
        created_by_agent_id="dev-agent",
    )
    run_rows = await artifact_store.list_artifacts(
        company_id=company.company_id,
        run_ids=[run.run_id, other_run.run_id],
    )
    fetched = await artifact_store.get_artifact(artifact.artifact_id)

    assert [row.artifact_id for row in rows] == [artifact.artifact_id]
    assert {row.artifact_id for row in run_rows} == {
        artifact.artifact_id,
        other_artifact.artifact_id,
    }
    assert fetched is not None
    assert fetched.artifact_type == ArtifactType.REPORT.value
    assert fetched.metadata == {"source": "artifact-store"}
    assert not hasattr(fetched, "metadata_json")


@pytest.mark.asyncio
async def test_artifact_store_records_idempotent_audit_events(
    db_session: AsyncSession,
) -> None:
    store = SqlAlchemyControlPlaneArtifactStore(db_session)
    company = await store.create_company(
        CompanyContext(company_id="cmp_artifact_store_audit", name="Wisdoverse Cell")
    )
    event = AuditEvent(
        company_id=company.company_id,
        action="artifact.created",
        target_type="artifact",
        target_id="art_001",
        idempotency_key="art_001:created",
        detail={"source": "artifact-store"},
    )

    first = await store.append_audit_event(event)
    second = await store.append_audit_event(event)
    result = await db_session.execute(
        select(AuditEventTable).where(
            AuditEventTable.company_id == company.company_id,
            AuditEventTable.idempotency_key == "art_001:created",
        )
    )

    assert first.audit_event_id == second.audit_event_id
    assert len(list(result.scalars().all())) == 1
