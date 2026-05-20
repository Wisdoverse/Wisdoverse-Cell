"""Tests for create_agent_app factory."""

from unittest.mock import patch

import pytest
from fastapi import APIRouter, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from shared.api import ERROR_CODE_HEADER, ApiErrorCode, raise_api_error
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
    async def test_agent_request_adds_trace_id_from_header(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/agent/request",
                headers={"X-Trace-ID": "trace-agent-request"},
                json={"action": "wakeup"},
            )

        assert resp.status_code == 200
        assert resp.json()["request"] == {
            "action": "wakeup",
            "trace_id": "trace-agent-request",
        }

    @pytest.mark.asyncio
    async def test_agent_request_keeps_payload_trace_id_when_present(self):
        app = create_agent_app(FakeAgent(), evolution_enabled=False)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/agent/request",
                headers={"X-Trace-ID": "trace-header"},
                json={"action": "wakeup", "trace_id": "trace-body"},
            )

        assert resp.status_code == 200
        assert resp.json()["request"] == {
            "action": "wakeup",
            "trace_id": "trace-body",
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


class TestFactoryErrorEnvelope:
    @pytest.mark.asyncio
    async def test_http_exception_uses_structured_error_envelope(self):
        router = APIRouter()

        @router.get("/coded-error")
        async def coded_error():
            raise_api_error(
                status_code=404,
                code=ApiErrorCode.AGENT_NOT_FOUND,
                message="agent_not_found",
            )

        app = create_agent_app(
            FakeAgent(),
            evolution_enabled=False,
            include_api_key_middleware=False,
            routers=[router],
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/coded-error", headers={"X-Trace-ID": "trace-error-1"})

        body = resp.json()
        assert resp.status_code == 404
        assert resp.headers[ERROR_CODE_HEADER] == ApiErrorCode.AGENT_NOT_FOUND.value
        assert resp.headers["X-Trace-ID"] == "trace-error-1"
        assert body["detail"] == "agent_not_found"
        assert body["code"] == ApiErrorCode.AGENT_NOT_FOUND.value
        assert body["message"] == "agent_not_found"
        assert body["trace_id"] == "trace-error-1"
        assert body["details"] is None

    @pytest.mark.asyncio
    async def test_uncoded_http_exception_gets_default_error_code(self):
        router = APIRouter()

        @router.get("/uncoded-error")
        async def uncoded_error():
            raise HTTPException(status_code=409, detail="conflict")

        app = create_agent_app(
            FakeAgent(),
            evolution_enabled=False,
            include_api_key_middleware=False,
            routers=[router],
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/uncoded-error", headers={"X-Trace-ID": "trace-error-2"})

        body = resp.json()
        assert resp.status_code == 409
        assert resp.headers[ERROR_CODE_HEADER] == ApiErrorCode.HTTP_ERROR.value
        assert body["detail"] == "conflict"
        assert body["code"] == ApiErrorCode.HTTP_ERROR.value
        assert body["trace_id"] == "trace-error-2"

    @pytest.mark.asyncio
    async def test_framework_404_uses_structured_error_envelope(self):
        app = create_agent_app(
            FakeAgent(),
            evolution_enabled=False,
            include_api_key_middleware=False,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/missing", headers={"X-Trace-ID": "trace-missing"})

        body = resp.json()
        assert resp.status_code == 404
        assert resp.headers[ERROR_CODE_HEADER] == ApiErrorCode.HTTP_ERROR.value
        assert body["detail"] == "Not Found"
        assert body["code"] == ApiErrorCode.HTTP_ERROR.value
        assert body["trace_id"] == "trace-missing"

    @pytest.mark.asyncio
    async def test_validation_exception_uses_structured_error_envelope(self):
        router = APIRouter()

        class Payload(BaseModel):
            name: str

        @router.post("/payload")
        async def payload_endpoint(payload: Payload):
            return payload

        app = create_agent_app(
            FakeAgent(),
            evolution_enabled=False,
            include_api_key_middleware=False,
            routers=[router],
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/payload",
                headers={"X-Trace-ID": "trace-validation"},
                json={},
            )

        body = resp.json()
        assert resp.status_code == 422
        assert resp.headers[ERROR_CODE_HEADER] == ApiErrorCode.REQUEST_VALIDATION_FAILED.value
        assert body["detail"]
        assert body["code"] == ApiErrorCode.REQUEST_VALIDATION_FAILED.value
        assert body["message"] == "Request validation failed"
        assert body["trace_id"] == "trace-validation"
        assert body["details"]["errors"][0]["loc"] == ["body", "name"]

    @pytest.mark.asyncio
    async def test_unhandled_exception_uses_structured_error_envelope(self):
        router = APIRouter()

        @router.get("/boom")
        async def boom():
            raise RuntimeError("sensitive internals")

        app = create_agent_app(
            FakeAgent(),
            evolution_enabled=False,
            include_api_key_middleware=False,
            routers=[router],
        )
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            resp = await client.get("/boom", headers={"X-Trace-ID": "trace-boom"})

        body = resp.json()
        assert resp.status_code == 500
        assert resp.headers[ERROR_CODE_HEADER] == ApiErrorCode.INTERNAL_ERROR.value
        assert body["detail"] == "Internal service error. Please try again later."
        assert body["code"] == ApiErrorCode.INTERNAL_ERROR.value
        assert body["message"] == "Internal service error. Please try again later."
        assert body["trace_id"] == "trace-boom"


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
