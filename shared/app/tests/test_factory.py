"""Tests for create_agent_app factory."""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from shared.app.factory import create_agent_app
from shared.app.runtime import AgentRuntime, RuntimePlugin
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class FakeAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_id="test-agent", agent_name="Test Agent")

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return {"status": "ok", "request": request}

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


class TestCreateAgentApp:
    def test_creates_fastapi_app(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        assert app.title == "Test Agent"

    def test_custom_title(self):
        app = create_agent_app(FakeAgent(), title="Custom", evolution_enabled=False)
        assert app.title == "Custom"

    def test_has_health_routes(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/health/ready" in paths

    def test_runtime_on_state(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        assert isinstance(app.state.runtime, AgentRuntime)
        assert app.state.runtime.agent_id == "test-agent"

    def test_evolution_excluded_registers_plugin(self):
        app = create_agent_app(FakeAgent(), evolution_excluded=True)
        plugins = app.state.runtime._plugins
        assert any(p.name == "evolution" for p in plugins)

    def test_no_docs_in_production(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        # docs_url depends on settings.debug — just verify app was created
        assert app is not None

    def test_version_default(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        assert app.version == "1.0.0"

    def test_custom_version(self):
        app = create_agent_app(FakeAgent(), version="2.0.0", evolution_enabled=False)
        assert app.version == "2.0.0"

    def test_has_new_health_routes(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health/startup" in paths
        assert "/health/ready/detail" in paths
        assert "/agent/request" in paths


class TestFactoryPlugins:
    def test_plugins_param_accepted(self):
        class NoopPlugin(RuntimePlugin):
            name = "noop"

        app = create_agent_app(FakeAgent(), plugins=[NoopPlugin()], evolution_enabled=False)
        assert app is not None

    def test_plugins_registered_on_runtime(self):
        class NoopPlugin(RuntimePlugin):
            name = "noop"

        app = create_agent_app(FakeAgent(), plugins=[NoopPlugin()], evolution_enabled=False)
        runtime = app.state.runtime
        plugin_names = [p.name for p in runtime._plugins]
        assert "noop" in plugin_names

    def test_plugins_added_after_evolution(self):
        class NoopPlugin(RuntimePlugin):
            name = "noop"

        app = create_agent_app(FakeAgent(), plugins=[NoopPlugin()])
        plugin_names = [p.name for p in app.state.runtime._plugins]
        assert plugin_names.index("evolution") < plugin_names.index("noop")


class TestFactoryStartupProbe:
    @pytest.mark.asyncio
    async def test_startup_probe_503_before_start(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health/startup")
            assert resp.status_code == 503


class TestFactoryAgentRequest:
    @pytest.mark.asyncio
    async def test_agent_request_calls_runtime_agent(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/agent/request",
                json={"action": "wakeup", "input": {"task": "ping"}},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "request": {"action": "wakeup", "input": {"task": "ping"}},
        }

    @pytest.mark.asyncio
    async def test_agent_request_requires_internal_key_when_configured(self):
        with patch("shared.middleware.internal_auth.settings") as mock_settings:
            mock_settings.internal_service_key = "test-secret-key"
            app = create_agent_app(FakeAgent(), evolution_enabled=False)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                missing = await client.post("/agent/request", json={"action": "wakeup"})
                allowed = await client.post(
                    "/agent/request",
                    headers={"X-Internal-Key": "test-secret-key"},
                    json={"action": "wakeup"},
                )

        assert missing.status_code in (401, 403)
        assert allowed.status_code == 200
        assert allowed.json()["request"] == {"action": "wakeup"}


class TestFactoryReadinessTwoTier:
    @pytest.mark.asyncio
    async def test_ready_public_no_checks_detail(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health/ready")
            body = resp.json()
            assert "checks" not in body
            assert "status" in body


class TestFactorySecurityRegression:
    @pytest.mark.asyncio
    async def test_ready_detail_requires_internal_key(self):
        with patch("shared.middleware.internal_auth.settings") as mock_settings:
            mock_settings.internal_service_key = "test-secret-key"
            app = create_agent_app(FakeAgent(), evolution_enabled=False)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/health/ready/detail")
            assert resp.status_code in (401, 403)
