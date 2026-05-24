"""Tests for execution-link resolution in artifact and decision use cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.artifact_store import SqlAlchemyControlPlaneArtifactStore
from shared.control_plane.artifact_use_cases import (
    ArtifactLinkMismatchError,
    create_artifact_with_audit,
)
from shared.control_plane.decision_store import SqlAlchemyControlPlaneDecisionStore
from shared.control_plane.decision_use_cases import (
    DecisionLinkMismatchError,
    create_decision_with_audit,
)
from shared.control_plane.models import (
    AgentRun,
    AgentRunStatus,
    Artifact,
    ArtifactType,
    CompanyContext,
    Decision,
    Goal,
    GoalStatus,
    WorkItem,
)
from shared.control_plane.store_factory import ControlPlaneStores


@pytest.mark.asyncio
async def test_artifact_creation_resolves_links_from_agent_run(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    await stores.companies.create_company(
        CompanyContext(company_id="cmp_execution_links", name="Execution Links")
    )
    goal = await stores.goals.create_goal(
        Goal(
            company_id="cmp_execution_links",
            title="Ship linked evidence",
            status=GoalStatus.ACTIVE,
        )
    )
    work_item = await stores.work_items.create_work_item(
        WorkItem(
            company_id="cmp_execution_links",
            title="Create artifact",
            goal_id=goal.goal_id,
        )
    )
    run = await stores.agent_runs.create_agent_run(
        AgentRun(
            company_id="cmp_execution_links",
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
        )
    )

    artifact = await create_artifact_with_audit(
        SqlAlchemyControlPlaneArtifactStore(db_session),
        Artifact(
            company_id="cmp_execution_links",
            artifact_type=ArtifactType.REPORT,
            title="Run evidence",
            uri="urn:wisdoverse-cell:artifact:run-evidence",
            run_id=run.run_id,
        ),
        created_by="human:architect",
    )

    assert artifact.goal_id == goal.goal_id
    assert artifact.work_item_id == work_item.work_item_id


@pytest.mark.asyncio
async def test_decision_creation_blocks_mismatched_execution_links(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    await stores.companies.create_company(
        CompanyContext(
            company_id="cmp_execution_link_mismatch",
            name="Execution Link Mismatch",
        )
    )
    run_goal = await stores.goals.create_goal(
        Goal(company_id="cmp_execution_link_mismatch", title="Run goal")
    )
    requested_goal = await stores.goals.create_goal(
        Goal(company_id="cmp_execution_link_mismatch", title="Requested goal")
    )
    run = await stores.agent_runs.create_agent_run(
        AgentRun(
            company_id="cmp_execution_link_mismatch",
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            goal_id=run_goal.goal_id,
        )
    )

    with pytest.raises(DecisionLinkMismatchError) as exc:
        await create_decision_with_audit(
            SqlAlchemyControlPlaneDecisionStore(db_session),
            Decision(
                company_id="cmp_execution_link_mismatch",
                title="Resolve linked decision",
                rationale="Mismatched goal must be rejected.",
                run_id=run.run_id,
                goal_id=requested_goal.goal_id,
            ),
            created_by="human:architect",
        )

    assert str(exc.value) == "goal"


@pytest.mark.asyncio
async def test_artifact_creation_blocks_mismatched_execution_links(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)
    await stores.companies.create_company(
        CompanyContext(
            company_id="cmp_artifact_execution_link_mismatch",
            name="Artifact Execution Link Mismatch",
        )
    )
    run_work_item = await stores.work_items.create_work_item(
        WorkItem(
            company_id="cmp_artifact_execution_link_mismatch",
            title="Run work item",
        )
    )
    requested_work_item = await stores.work_items.create_work_item(
        WorkItem(
            company_id="cmp_artifact_execution_link_mismatch",
            title="Requested work item",
        )
    )
    run = await stores.agent_runs.create_agent_run(
        AgentRun(
            company_id="cmp_artifact_execution_link_mismatch",
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            work_item_id=run_work_item.work_item_id,
        )
    )

    with pytest.raises(ArtifactLinkMismatchError) as exc:
        await create_artifact_with_audit(
            SqlAlchemyControlPlaneArtifactStore(db_session),
            Artifact(
                company_id="cmp_artifact_execution_link_mismatch",
                artifact_type=ArtifactType.REPORT,
                title="Run evidence",
                uri="urn:wisdoverse-cell:artifact:mismatch",
                run_id=run.run_id,
                work_item_id=requested_work_item.work_item_id,
            ),
            created_by="human:architect",
        )

    assert str(exc.value) == "work_item"
