"""Tests for WebUI prompt-config compatibility endpoints."""

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.requirement_manager.api import webui
from agents.requirement_manager.api.webui import router
from shared.control_plane.tables import control_plane_metadata

aiosqlite = pytest.importorskip("aiosqlite", reason="aiosqlite not installed")


@pytest.mark.asyncio
async def test_agent_prompt_config_round_trips_through_webui_api(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

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
        missing = await client.put(
            "/api/v1/agents/not-a-real-agent/prompt-config",
            json={"system_prompt": "Nope"},
        )

    assert saved.status_code == 200
    assert saved.json()["agent_id"] == "requirement-manager"
    assert saved.json()["system_prompt"] == "Own requirement intake."
    assert fetched.status_code == 200
    assert fetched.json()["system_prompt"] == saved.json()["system_prompt"]
    assert missing.status_code == 404
    assert missing.headers["x-error-code"] == "agent.not_found"

    async with engine.begin() as conn:
        await conn.run_sync(control_plane_metadata.drop_all)
    await engine.dispose()
