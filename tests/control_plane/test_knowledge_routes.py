"""HTTP-level authorization and lifecycle coverage for company knowledge."""

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.control_plane.api import create_control_plane_router
from shared.control_plane.knowledge_models import KnowledgeTombstoneTable
from shared.control_plane.models import AgentRole, Artifact, CompanyContext
from shared.control_plane.store_factory import ControlPlaneStores
from shared.control_plane.tables import AgentRoleTable


def _session_provider(db_session: AsyncSession):
    @asynccontextmanager
    async def provider():
        yield db_session
        await db_session.flush()

    return provider


def _token(
    actor_id: str, companies: list[str], scopes: list[str], role_ids: list[str] | None = None
) -> str:
    token = f"token-for-{actor_id}"
    entries = json.loads(settings.control_plane_operators_json or "[]")
    entries.append(
        {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "actor_id": actor_id,
            "companies": companies,
            "scopes": scopes,
            "role_ids": role_ids or [],
        }
    )
    settings.control_plane_operators_json = json.dumps(entries)
    return token


@pytest.mark.asyncio
async def test_knowledge_routes_enforce_scopes_owner_acl_versions_and_tombstones(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "control_plane_operators_json", "")
    stores = ControlPlaneStores(db_session)
    await stores.companies.create_company(
        CompanyContext(company_id="cmp_knowledge", name="Knowledge Cell")
    )
    await stores.companies.create_company(CompanyContext(company_id="cmp_other", name="Other Cell"))
    artifact = await stores.artifacts.create_artifact(
        Artifact(
            artifact_id="art_knowledge",
            company_id="cmp_knowledge",
            title="Source evidence",
            uri="s3://company/evidence",
            content_hash="sha256:abc123",
        )
    )
    role = AgentRole(
        company_id="cmp_knowledge",
        agent_id="knowledge-reader",
        display_name="Reader",
        role="reader",
        role_id="role_knowledge_reader",
    )
    from shared.control_plane.tables import AgentRoleTable

    db_session.add(
        AgentRoleTable(
            role_id=role.role_id,
            company_id=role.company_id,
            agent_id=role.agent_id,
            display_name=role.display_name,
            role=role.role,
        )
    )
    await db_session.flush()
    await db_session.commit()

    publish_scopes = ["knowledge:write", "knowledge:read", "knowledge:delete"]
    owner_token = _token("owner", ["cmp_knowledge"], publish_scopes)
    reader_token = _token(
        "reader", ["cmp_knowledge"], ["knowledge:read"], ["role_knowledge_reader"]
    )
    outsider_token = _token("outsider", ["cmp_knowledge"], ["knowledge:read"])
    other_company_token = _token("other-company", ["cmp_other"], publish_scopes)

    app = FastAPI()
    app.include_router(create_control_plane_router(session_provider=_session_provider(db_session)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_response = await client.post(
            "/api/v1/control-plane/knowledge",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json={
                "company_id": "cmp_knowledge",
                "source_artifact_id": artifact.artifact_id,
                "reader_role_ids": [role.role_id],
            },
        )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        knowledge_id = created["knowledge_id"]

        source_response = await client.get(
            f"/api/v1/control-plane/knowledge/{knowledge_id}",
            headers={"X-Control-Plane-Operator-Token": reader_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert source_response.status_code == 200, source_response.text
        assert source_response.json()["source_artifact"] == {
            "artifact_id": artifact.artifact_id,
            "company_id": "cmp_knowledge",
            "uri": "s3://company/evidence",
            "content_hash": "sha256:abc123",
        }

        denied_read = await client.get(
            f"/api/v1/control-plane/knowledge/{knowledge_id}",
            headers={"X-Control-Plane-Operator-Token": outsider_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert denied_read.status_code == 403
        cross_company = await client.get(
            f"/api/v1/control-plane/knowledge/{knowledge_id}",
            headers={"X-Control-Plane-Operator-Token": other_company_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert cross_company.status_code == 403

        revision_body = {
            "company_id": "cmp_knowledge",
            "source_artifact_id": artifact.artifact_id,
            "reader_role_ids": [],
            "expected_version": 1,
        }
        nonowner_revision = await client.post(
            f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
            headers={
                "X-Control-Plane-Operator-Token": _token(
                    "writer", ["cmp_knowledge"], ["knowledge:write"]
                )
            },
            json=revision_body,
        )
        assert nonowner_revision.status_code == 403

        other_artifact = await stores.artifacts.create_artifact(
            Artifact(
                artifact_id="art_knowledge_other",
                company_id="cmp_knowledge",
                title="Different evidence",
                uri="s3://company/different",
            )
        )
        provenance_change = await client.post(
            f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json={**revision_body, "source_artifact_id": other_artifact.artifact_id},
        )
        assert provenance_change.status_code == 400

        revised = await client.post(
            f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json={**revision_body, "reader_role_ids": [role.role_id]},
        )
        assert revised.status_code == 200
        stale = await client.post(
            f"/api/v1/control-plane/knowledge/{knowledge_id}/publish",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json=revision_body,
        )
        assert stale.status_code == 409

        deleted = await client.delete(
            f"/api/v1/control-plane/knowledge/{knowledge_id}",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert deleted.status_code == 200
        hidden = await client.get(
            f"/api/v1/control-plane/knowledge/{knowledge_id}",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert hidden.status_code == 404
        assert await db_session.get(KnowledgeTombstoneTable, knowledge_id) is not None
        audits = await stores.audit_events.list_audit_events(
            company_id="cmp_knowledge", target_type="knowledge", target_id=knowledge_id
        )
        assert {event.action for event in audits} == {
            "knowledge.published",
            "knowledge.revised",
            "knowledge.deleted",
        }


@pytest.mark.asyncio
async def test_knowledge_routes_reject_expired_records_and_foreign_reader_roles(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "control_plane_operators_json", "")
    stores = ControlPlaneStores(db_session)
    await stores.companies.create_company(
        CompanyContext(company_id="cmp_knowledge", name="Knowledge Cell")
    )
    await stores.companies.create_company(CompanyContext(company_id="cmp_other", name="Other Cell"))
    artifact = await stores.artifacts.create_artifact(
        Artifact(
            artifact_id="art_knowledge",
            company_id="cmp_knowledge",
            title="Evidence",
            uri="s3://company/evidence",
        )
    )
    db_session.add(
        AgentRoleTable(
            role_id="role_other",
            company_id="cmp_other",
            agent_id="other-reader",
            display_name="Other reader",
            role="reader",
        )
    )
    await db_session.flush()
    await db_session.commit()
    owner_token = _token("owner", ["cmp_knowledge"], ["knowledge:write", "knowledge:read"])
    app = FastAPI()
    app.include_router(create_control_plane_router(session_provider=_session_provider(db_session)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        foreign_role = await client.post(
            "/api/v1/control-plane/knowledge",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json={
                "company_id": "cmp_knowledge",
                "source_artifact_id": artifact.artifact_id,
                "reader_role_ids": ["role_other"],
            },
        )
        assert foreign_role.status_code == 400
        expired = await client.post(
            "/api/v1/control-plane/knowledge",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            json={
                "company_id": "cmp_knowledge",
                "source_artifact_id": artifact.artifact_id,
                "retention_until": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            },
        )
        assert expired.status_code == 201
        hidden = await client.get(
            f"/api/v1/control-plane/knowledge/{expired.json()['knowledge_id']}",
            headers={"X-Control-Plane-Operator-Token": owner_token},
            params={"company_id": "cmp_knowledge"},
        )
        assert hidden.status_code == 404
