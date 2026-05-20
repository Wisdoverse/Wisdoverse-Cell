"""Tests for control-plane application-domain return boundaries."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api import _row_to_dict
from shared.control_plane.artifact_use_cases import (
    create_artifact_with_audit,
    list_artifacts,
)
from shared.control_plane.company_use_cases import (
    create_company_with_audit,
    list_companies,
)
from shared.control_plane.decision_use_cases import (
    create_decision_with_audit,
    list_decisions,
)
from shared.control_plane.goal_use_cases import create_goal_with_audit, list_goals
from shared.control_plane.models import (
    Artifact,
    ArtifactType,
    CompanyContext,
    Decision,
    Goal,
    GoalStatus,
    WorkItem,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.work_item_use_cases import (
    create_work_item_with_audit,
    list_work_items,
)


@pytest.mark.asyncio
async def test_operator_use_cases_return_domain_records(
    db_session: AsyncSession,
) -> None:
    stores = ControlPlaneStores(db_session)

    company = await create_company_with_audit(
        stores.companies,
        company_id="cmp_domain_records",
        name="Domain Records Inc.",
        mission="Keep application use cases free of ORM rows",
        metadata={"layer": "application"},
        created_by="architect",
    )
    goal = await create_goal_with_audit(
        stores.goals,
        Goal(
            company_id=company.company_id,
            title="Expose domain records",
            status=GoalStatus.ACTIVE,
            metadata={"record": "goal"},
        ),
        created_by="architect",
    )
    work_item = await create_work_item_with_audit(
        stores.work_items,
        WorkItem(
            company_id=company.company_id,
            title="Verify use-case boundary",
            goal_id=goal.goal_id,
            metadata={"record": "work_item"},
        ),
        created_by="architect",
    )
    decision = await create_decision_with_audit(
        stores.decisions,
        Decision(
            company_id=company.company_id,
            title="Return Pydantic records",
            rationale="Application callers should not receive ORM rows.",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            metadata={"record": "decision"},
        ),
        created_by="architect",
    )
    artifact = await create_artifact_with_audit(
        stores.artifacts,
        Artifact(
            company_id=company.company_id,
            artifact_type=ArtifactType.REPORT,
            title="Boundary evidence",
            uri="urn:wisdoverse-cell:control-plane:domain-record-test",
            goal_id=goal.goal_id,
            work_item_id=work_item.work_item_id,
            metadata={"record": "artifact"},
        ),
        created_by="architect",
    )

    companies = await list_companies(stores.companies, search="Domain Records")
    goals = await list_goals(stores.goals, company_id=company.company_id)
    work_items = await list_work_items(
        stores.work_items,
        company_id=company.company_id,
    )
    decisions = await list_decisions(stores.decisions, company_id=company.company_id)
    artifacts = await list_artifacts(stores.artifacts, company_id=company.company_id)

    assert isinstance(company, CompanyContext)
    assert isinstance(companies[0], CompanyContext)
    assert isinstance(goals[0], Goal)
    assert isinstance(work_items[0], WorkItem)
    assert isinstance(decisions[0], Decision)
    assert isinstance(artifacts[0], Artifact)

    assert not hasattr(company, "metadata_json")
    assert not hasattr(goal, "metadata_json")
    assert not hasattr(work_item, "metadata_json")
    assert not hasattr(decision, "metadata_json")
    assert not hasattr(artifact, "metadata_json")

    assert company.metadata == {"layer": "application"}
    assert goal.metadata == {"record": "goal"}
    assert work_item.metadata == {"record": "work_item"}
    assert decision.metadata == {"record": "decision"}
    assert artifact.metadata == {"record": "artifact"}

    payload = _row_to_dict(goal)

    assert payload["goal_id"] == goal.goal_id
    assert payload["status"] == GoalStatus.ACTIVE.value
    assert payload["metadata"] == {"record": "goal"}
    assert "metadata_json" not in payload
