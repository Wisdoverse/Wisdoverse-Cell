from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.requirement_manager.api import webui
from agents.requirement_manager.api.webui import router
from shared.config import settings
from shared.control_plane.models import (
    AgentRole,
    AgentRun,
    AgentRunStatus,
    ApprovalCategory,
    ApprovalRequest,
    ApprovalStatus,
    CompanyContext,
)
from shared.control_plane.repository import ControlPlaneRepository
from shared.control_plane.tables import control_plane_metadata

aiosqlite = pytest.importorskip("aiosqlite", reason="aiosqlite not installed")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


async def _install_control_plane_manager(monkeypatch, seed=None):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    if seed is not None:
        async with session_factory() as session:
            repo = ControlPlaneRepository(session)
            await seed(repo)
            await session.commit()

    @asynccontextmanager
    async def session_provider():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    class TestControlPlaneManager:
        def session(self):
            return session_provider()

    monkeypatch.setattr(webui, "control_plane_db_manager", TestControlPlaneManager())
    return engine


async def _seed_runtime_records(repo: ControlPlaneRepository) -> None:
    company_id = settings.control_plane_company_id
    await repo.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )
    await repo.create_agent_role(
        AgentRole(
            company_id=company_id,
            agent_id="requirement-manager",
            display_name="Requirement Manager",
            role="requirement_manager",
            domain="product",
            status="active",
        )
    )
    await repo.create_agent_role(
        AgentRole(
            company_id=company_id,
            agent_id="qa-agent",
            display_name="QA Agent",
            role="qa",
            domain="quality",
            status="paused",
        )
    )
    await repo.create_agent_run(
        AgentRun(
            company_id=company_id,
            agent_id="requirement-manager",
            status=AgentRunStatus.RUNNING,
        )
    )


@pytest.mark.asyncio
async def test_list_agent_runtime_statuses_uses_control_plane_records(monkeypatch) -> None:
    engine = await _install_control_plane_manager(monkeypatch, _seed_runtime_records)
    app = FastAPI()
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents")

    body = response.json()
    assert response.status_code == 200
    assert body["total"] == 2
    requirement_manager = next(
        agent for agent in body["agents"] if agent["agent_id"] == "requirement-manager"
    )
    assert requirement_manager["status"] == "running"
    assert requirement_manager["task_count"] == 1
    assert {"status", "health", "task_count", "pending_count", "error_count"} <= set(
        body["agents"][0]
    )

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_paused_agent_role_reports_stopped(monkeypatch) -> None:
    engine = await _install_control_plane_manager(monkeypatch, _seed_runtime_records)
    app = FastAPI()
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/agents/qa-agent/status")

    assert response.status_code == 200
    assert response.json()["status"] == "stopped"
    assert response.json()["health"] == 0

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)
    await engine.dispose()


async def _seed_approval_records(repo: ControlPlaneRepository) -> None:
    company_id = settings.control_plane_company_id
    await repo.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )
    await repo.request_approval(
        ApprovalRequest(
            company_id=company_id,
            category=ApprovalCategory.TECHNICAL,
            status=ApprovalStatus.PENDING,
            requested_by="dev-agent",
            source_agent_id="dev-agent",
            proposed_action="Deploy operator surface",
            reason="Needs production release",
            risk="UI regression",
            rollback_note="Revert the release",
            affected_resources=["frontend"],
            metadata={"urgency": "urgent"},
        )
    )


@pytest.mark.asyncio
async def test_list_approvals_returns_control_plane_records(monkeypatch) -> None:
    engine = await _install_control_plane_manager(monkeypatch, _seed_approval_records)
    app = FastAPI()
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/approvals?status=pending")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["approvals"][0]["title"] == "Deploy operator surface"
    assert body["approvals"][0]["urgency"] == "urgent"

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)
    await engine.dispose()


def test_webui_readiness_returns_monitor_checks() -> None:
    response = _client().get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"healthy", "degraded", "unhealthy"}
    assert {"postgres", "redis", "milvus", "nats"} <= set(body["checks"])


@pytest.mark.asyncio
async def test_agent_prompt_config_round_trips_through_webui_api(monkeypatch) -> None:
    engine = await _install_control_plane_manager(monkeypatch, _seed_runtime_records)

    app = FastAPI()
    app.include_router(router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        saved = await client.put(
            "/api/v1/agents/requirement-manager/prompt-config",
            json={"system_prompt": "Own requirement intake.", "updated_by": "webui"},
        )
        fetched = await client.get(
            "/api/v1/agents/requirement-manager/prompt-config",
        )

    assert saved.status_code == 200
    assert saved.json()["agent_id"] == "requirement-manager"
    assert saved.json()["system_prompt"] == "Own requirement intake."
    assert fetched.status_code == 200
    assert fetched.json()["system_prompt"] == saved.json()["system_prompt"]

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)
    await engine.dispose()
