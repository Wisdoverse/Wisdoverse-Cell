"""HTTP acceptance for portable company-template import and export."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.control_plane.api_routes.company_templates import create_company_template_router
from shared.control_plane.models import (
    AgentRole,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    Goal,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.unit_of_work import ControlPlaneUnitOfWork


def _app(db_session: AsyncSession) -> FastAPI:
    app = FastAPI()

    async def get_uow() -> AsyncGenerator[ControlPlaneUnitOfWork, None]:
        uow = ControlPlaneUnitOfWork(db_session)
        try:
            yield uow
        except Exception:
            if not uow.completed:
                await uow.rollback()
            raise
        finally:
            if not uow.completed:
                await uow.rollback()

    app.include_router(create_company_template_router(get_uow=get_uow))
    return app


async def _seed_export_company(db_session: AsyncSession) -> CompanyContext:
    stores = ControlPlaneStores(db_session)
    company = await stores.companies.create_company(
        CompanyContext(
            company_id="cmp_template_source",
            name="Portable Source",
            mission="Run a repeatable company",
            metadata={
                "provider_account_id": "must-not-export",
                "playbooks": [
                    {
                        "key": "reporting",
                        "title": "Prepare reports",
                        "steps": [{"role_key": "role-001", "action": "Review the report"}],
                    }
                ],
            },
        )
    )
    await stores.goals.create_goal(
        Goal(
            company_id=company.company_id,
            title="Run reporting",
            description="Deliver a reviewed report",
            owner_agent_id="private-agent-id",
        )
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="private-manager-id",
            display_name="Manager",
            role="manager",
        )
    )
    budget = await stores.budgets.create_budget_policy(
        BudgetPolicy(
            company_id=company.company_id,
            scope=BudgetScope.AGENT,
            scope_id="private-agent-id",
            period=BudgetPeriod.MONTHLY,
            limit_usd=75.0,
            warning_threshold=0.65,
            model_allowlist=["model-sample"],
        )
    )
    await stores.agent_registry.create_agent_role(
        AgentRole(
            company_id=company.company_id,
            agent_id="private-agent-id",
            display_name="Reporter",
            role="analyst",
            title="Reporting analyst",
            reports_to_agent_id="private-manager-id",
            budget_policy_id=budget.budget_id,
            responsibilities=["Prepare reports"],
            permissions=["reports:read"],
            adapter_type="http",
            adapter_config={"base_url": "http://10.0.0.7/private"},
            metadata={"skill_references": ["skill:reporting-v1"], "private": "excluded"},
        )
    )
    await db_session.flush()
    return company


@pytest.mark.asyncio
async def test_template_export_import_creates_paused_unprivileged_records(
    db_session: AsyncSession,
) -> None:
    source = await _seed_export_company(db_session)
    await db_session.commit()
    app = _app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        exported = await client.get(f"/companies/{source.company_id}/template")
        assert exported.status_code == 200
        payload = exported.json()
        assert payload["company"] == {
            "name": "Portable Source",
            "mission": "Run a repeatable company",
        }
        assert payload["playbooks"][0]["key"] == "reporting"
        assert payload["roles"][0]["reports_to_key"] == "role-002"
        assert payload["goals"][0]["owner_role_key"] == "role-001"
        assert payload["roles"][0]["budget_key"] == payload["budgets"][0]["local_key"]
        assert payload["budgets"][0]["scope"] == "agent"
        assert payload["budgets"][0]["scope_key"] == "role-001"
        serialized = str(payload)
        for private_value in (
            source.company_id,
            "private-agent-id",
            "10.0.0.7",
            "provider_account_id",
            "must-not-export",
        ):
            assert private_value not in serialized

        payload["company"]["name"] = "Portable Copy"
        imported = await client.post(
            "/company-templates/import",
            json={"template": payload, "permissions_reviewed": True},
        )

    assert imported.status_code == 201
    result = imported.json()
    assert result["company_id"] != source.company_id
    assert set(result["goal_ids"]) == {payload["goals"][0]["local_key"]}
    assert set(result["role_ids"]) == {role["local_key"] for role in payload["roles"]}

    stores = ControlPlaneStores(db_session)
    imported_company = await stores.companies.get_company(result["company_id"])
    assert imported_company is not None
    assert imported_company.metadata == {
        "playbooks": payload["playbooks"],
        "template_import": True,
    }
    created_roles = await stores.agent_registry.list_agent_roles(
        company_id=result["company_id"],
        limit=200,
    )
    created_role = next(
        role
        for role in created_roles
        if role.role_id == result["role_ids"][payload["roles"][0]["local_key"]]
    )
    assert created_role is not None
    assert created_role.status == "paused"
    assert created_role.adapter_type == "builtin"
    assert created_role.adapter_config == {}
    assert created_role.permissions == []
    assert created_role.metadata["template_import"]["permissions_reviewed"] is True
    assert created_role.metadata["template_import"]["requested_permissions"] == ["reports:read"]
    assert created_role.budget_policy_id is not None
    assert created_role.reports_to_agent_id is not None
    assert created_role.agent_id == "private-agent-id" or created_role.agent_id.startswith("agent_")
    imported_budgets = await stores.budgets.list_budget_policies(
        company_id=result["company_id"], limit=100
    )
    assert len(imported_budgets) == 1
    imported_budget = imported_budgets[0]
    assert imported_budget.status == "paused"
    assert imported_budget.company_id == result["company_id"]
    assert imported_budget.scope == BudgetScope.AGENT
    assert imported_budget.scope_id == created_role.agent_id
    assert imported_budget.limit_usd == 75.0
    assert imported_budget.warning_threshold == 0.65
    assert imported_budget.metadata["template_import"]["paused_for_operator_review"] is True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        round_trip = await client.get(f"/companies/{result['company_id']}/template")
    assert round_trip.status_code == 200
    assert round_trip.json()["budgets"] == payload["budgets"]
    assert round_trip.json()["roles"] == payload["roles"]
    assert round_trip.json()["goals"] == payload["goals"]


@pytest.mark.asyncio
async def test_template_import_requires_permission_review_and_rejects_name_collision(
    db_session: AsyncSession,
) -> None:
    source = await _seed_export_company(db_session)
    await db_session.commit()
    app = _app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        template = (await client.get(f"/companies/{source.company_id}/template")).json()
        blocked = await client.post(
            "/company-templates/import",
            json={"template": template, "permissions_reviewed": False},
        )
        collision = await client.post(
            "/company-templates/import",
            json={"template": template, "permissions_reviewed": True},
        )

    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "company_template_permissions_review_required"
    assert collision.status_code == 409
    assert collision.json()["detail"] == "company_template_name_collision"


@pytest.mark.asyncio
async def test_template_import_rejects_invalid_refs_and_unsupported_top_level_input(
    db_session: AsyncSession,
) -> None:
    app = _app(db_session)
    template = {
        "schema_version": "1.0",
        "company": {"name": "New Portable Company", "mission": ""},
        "goals": [],
        "roles": [],
        "playbooks": [],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unsupported = await client.post(
            "/company-templates/import",
            json={
                "template": template,
                "permissions_reviewed": True,
                "database_url": "postgres://private",
            },
        )
        invalid = await client.post(
            "/company-templates/import",
            json={
                "template": {
                    **template,
                    "goals": [{"local_key": "g1", "title": "Goal", "parent_key": "missing"}],
                },
                "permissions_reviewed": True,
            },
        )

    assert unsupported.status_code == 422
    assert unsupported.json()["detail"] == "invalid_company_template"
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "invalid_company_template"
    assert "postgres://private" not in str(unsupported.json())
