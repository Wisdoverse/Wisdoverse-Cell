"""Synthetic company reuse acceptance over isolated PostgreSQL and real API routes."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.control_plane.api import create_control_plane_router
from shared.control_plane.knowledge_models import KnowledgeTombstoneTable
from shared.control_plane.models import (
    AgentRole,
    Artifact,
    BudgetPeriod,
    BudgetPolicy,
    BudgetScope,
    CompanyContext,
    Goal,
)
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import control_plane_metadata

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _postgres_session() -> AsyncIterator[AsyncSession]:
    if not DATABASE_URL.startswith(("postgresql+asyncpg://", "postgresql://")):
        pytest.skip("TEST_DATABASE_URL must provide disposable PostgreSQL")

    schema = "company_reuse_test_" + uuid4().hex
    admin = create_async_engine(DATABASE_URL)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
        async with sessions() as session:
            yield session
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _token(actor_id: str, company_id: str, scopes: list[str], role_ids: list[str] = ()) -> str:
    token = f"synthetic-token-{actor_id}"
    entries = json.loads(settings.control_plane_operators_json or "[]")
    entries.append(
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "actor_id": actor_id,
            "companies": [company_id],
            "scopes": scopes,
            "role_ids": role_ids,
        }
    )
    settings.control_plane_operators_json = json.dumps(entries)
    return token


def _app(session: AsyncSession) -> FastAPI:
    @asynccontextmanager
    async def session_provider():
        yield session
        await session.flush()

    app = FastAPI()
    app.include_router(create_control_plane_router(session_provider=session_provider))
    return app


async def test_synthetic_company_template_and_knowledge_reuse_acceptance(monkeypatch):
    """Exercise portability and the knowledge lifecycle as one synthetic reuse flow."""
    async with _postgres_session() as session:
        monkeypatch.setattr(settings, "control_plane_operators_json", "")
        stores = ControlPlaneStores(session)
        source = await stores.companies.create_company(
            CompanyContext(
                company_id="cmp_reuse_source",
                name="Synthetic Reporting Cell",
                mission="Produce reviewed operating reports",
                metadata={
                    "provider_account_id": "synthetic-private-account",
                    "integration_secret": "synthetic-secret-do-not-export",
                    "playbooks": [
                        {
                            "key": "monthly-report",
                            "title": "Prepare monthly report",
                            "steps": [{"role_key": "role-001", "action": "review report"}],
                        }
                    ],
                },
            )
        )
        parent = await stores.agent_registry.create_agent_role(
            AgentRole(
                company_id=source.company_id,
                agent_id="synthetic-manager-private-id",
                display_name="Reporting Lead",
                role="manager",
                title="Reporting lead",
                responsibilities=["Review reports"],
                permissions=["reports:approve"],
                adapter_type="http",
                adapter_config={"base_url": "https://synthetic.invalid/private"},
                metadata={"api_token": "synthetic-role-token"},
            )
        )
        budget = await stores.budgets.create_budget_policy(
            BudgetPolicy(
                company_id=source.company_id,
                scope=BudgetScope.AGENT,
                scope_id="synthetic-analyst-private-id",
                period=BudgetPeriod.MONTHLY,
                limit_usd=42.0,
                warning_threshold=0.7,
                model_allowlist=["synthetic-model"],
            )
        )
        child = await stores.agent_registry.create_agent_role(
            AgentRole(
                company_id=source.company_id,
                agent_id="synthetic-analyst-private-id",
                display_name="Report Analyst",
                role="analyst",
                title="Monthly analyst",
                reports_to_agent_id=parent.agent_id,
                budget_policy_id=budget.budget_id,
                responsibilities=["Prepare monthly report"],
                permissions=["reports:read"],
                adapter_type="http",
                adapter_config={"authorization": "Bearer synthetic-role-token"},
                metadata={"skill_references": ["skill:monthly-report-v1"]},
            )
        )
        await stores.goals.create_goal(
            Goal(
                company_id=source.company_id,
                title="Deliver monthly report",
                description="Produce a reviewed report artifact",
                owner_agent_id=child.agent_id,
            )
        )
        await session.commit()

        app = _app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            exported_response = await client.get(
                f"/api/v1/control-plane/companies/{source.company_id}/template",
                headers={
                    "X-Control-Plane-Operator-Token": _token(
                        "template-exporter", source.company_id, ["control-plane:read"]
                    )
                },
            )
            assert exported_response.status_code == 200, exported_response.text
            template = exported_response.json()
            assert template["company"]["name"] == "Synthetic Reporting Cell"
            assert template["playbooks"][0]["key"] == "monthly-report"
            role_by_key = {role["local_key"]: role for role in template["roles"]}
            assert len(role_by_key) == 2
            imported_child = next(role for role in template["roles"] if role["role"] == "analyst")
            imported_parent = next(role for role in template["roles"] if role["role"] == "manager")
            assert imported_child["reports_to_key"] == imported_parent["local_key"]
            assert imported_child["budget_key"] is not None
            assert template["goals"][0]["owner_role_key"] == imported_child["local_key"]
            serialized = json.dumps(template)
            for secret in (
                source.company_id,
                "synthetic-manager-private-id",
                "synthetic-analyst-private-id",
                "synthetic-private-account",
                "synthetic-secret-do-not-export",
                "synthetic-role-token",
                "synthetic.invalid",
                "provider_account_id",
            ):
                assert secret not in serialized

            template["company"]["name"] = "Synthetic Reporting Copy"
            importer_token = _token(
                "template-importer", "*", ["template:import", "company:directory"]
            )
            imported_response = await client.post(
                "/api/v1/control-plane/company-templates/import",
                headers={"X-Control-Plane-Operator-Token": importer_token},
                json={"template": template, "permissions_reviewed": True},
            )
            assert imported_response.status_code == 201, imported_response.text
            result = imported_response.json()
            target_company_id = result["company_id"]
            assert target_company_id != source.company_id

            target_roles = await stores.agent_registry.list_agent_roles(
                company_id=target_company_id, limit=20
            )
            assert len(target_roles) == 2
            imported_child_record = next(role for role in target_roles if role.role == "analyst")
            imported_parent_record = next(role for role in target_roles if role.role == "manager")
            assert imported_child_record.reports_to_agent_id == imported_parent_record.agent_id
            assert imported_child_record.status == imported_parent_record.status == "paused"
            assert imported_child_record.adapter_type == imported_parent_record.adapter_type == "builtin"
            assert imported_child_record.adapter_config == imported_parent_record.adapter_config == {}
            assert imported_child_record.permissions == imported_parent_record.permissions == []
            assert imported_child_record.budget_policy_id is not None
            imported_budgets = await stores.budgets.list_budget_policies(
                company_id=target_company_id, limit=20
            )
            assert len(imported_budgets) == 1
            assert imported_budgets[0].status == "paused"

            artifact = await stores.artifacts.create_artifact(
                Artifact(
                    artifact_id="art_synthetic_reuse",
                    company_id=target_company_id,
                    title="Synthetic accepted report",
                    uri="artifact://synthetic/monthly-report",
                    content_hash="sha256:" + "a" * 64,
                )
            )
            await session.commit()
            owner_token = _token(
                "reuse-owner",
                target_company_id,
                ["knowledge:write", "knowledge:read", "knowledge:delete"],
            )
            reader_token = _token(
                "reuse-reader",
                target_company_id,
                ["knowledge:read"],
                [imported_child_record.role_id],
            )
            outsider_token = _token("reuse-outsider", target_company_id, ["knowledge:read"])
            owner_headers = {"X-Control-Plane-Operator-Token": owner_token}
            reader_headers = {"X-Control-Plane-Operator-Token": reader_token}
            outsider_headers = {"X-Control-Plane-Operator-Token": outsider_token}

            published_response = await client.post(
                "/api/v1/control-plane/knowledge",
                headers=owner_headers,
                json={
                    "company_id": target_company_id,
                    "source_artifact_id": artifact.artifact_id,
                    "reader_role_ids": [imported_child_record.role_id],
                    "retention_until": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                },
            )
            assert published_response.status_code == 201, published_response.text
            knowledge = published_response.json()
            knowledge_id = knowledge["knowledge_id"]

            allowed = await client.get(
                f"/api/v1/control-plane/knowledge/{knowledge_id}",
                headers=reader_headers,
                params={"company_id": target_company_id},
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["source_artifact"] == {
                "artifact_id": artifact.artifact_id,
                "company_id": target_company_id,
                "uri": artifact.uri,
                "content_hash": artifact.content_hash,
            }
            denied = await client.get(
                f"/api/v1/control-plane/knowledge/{knowledge_id}",
                headers=outsider_headers,
                params={"company_id": target_company_id},
            )
            assert denied.status_code == 403

            revision = await client.post(
                f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
                headers=owner_headers,
                json={
                    "company_id": target_company_id,
                    "source_artifact_id": artifact.artifact_id,
                    "reader_role_ids": [],
                    "expected_version": 1,
                },
            )
            assert revision.status_code == 200, revision.text
            assert revision.json()["version"] == 2
            stale_revision = await client.post(
                f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
                headers=owner_headers,
                json={
                    "company_id": target_company_id,
                    "source_artifact_id": artifact.artifact_id,
                    "reader_role_ids": [],
                    "expected_version": 1,
                },
            )
            assert stale_revision.status_code == 409
            revoked = await client.get(
                f"/api/v1/control-plane/knowledge/{knowledge_id}",
                headers=reader_headers,
                params={"company_id": target_company_id},
            )
            assert revoked.status_code == 403

            expired_response = await client.post(
                "/api/v1/control-plane/knowledge",
                headers=owner_headers,
                json={
                    "company_id": target_company_id,
                    "source_artifact_id": artifact.artifact_id,
                    "retention_until": (datetime.now(UTC) - timedelta(seconds=2)).isoformat(),
                },
            )
            assert expired_response.status_code == 201, expired_response.text
            expired_id = expired_response.json()["knowledge_id"]
            expired_read = await client.get(
                f"/api/v1/control-plane/knowledge/{expired_id}",
                headers=owner_headers,
                params={"company_id": target_company_id},
            )
            assert expired_read.status_code == 404

            deleted = await client.delete(
                f"/api/v1/control-plane/knowledge/{knowledge_id}",
                headers=owner_headers,
                params={"company_id": target_company_id},
            )
            assert deleted.status_code == 200, deleted.text
            hidden = await client.get(
                f"/api/v1/control-plane/knowledge/{knowledge_id}",
                headers=owner_headers,
                params={"company_id": target_company_id},
            )
            assert hidden.status_code == 404

        assert await session.get(KnowledgeTombstoneTable, knowledge_id) is not None
        audits = await stores.audit_events.list_audit_events(
            company_id=target_company_id,
            target_type="knowledge",
            target_id=knowledge_id,
        )
        assert {event.action for event in audits} == {
            "knowledge.published",
            "knowledge.revised",
            "knowledge.deleted",
        }
