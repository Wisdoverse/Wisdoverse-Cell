"""
Integration Tests - PMAgent API

Tests pjm_agent HTTP endpoints with httpx.AsyncClient.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from shared.api import ApiErrorCode


@pytest.fixture
def mock_agent():
    """Mock PMAgent instance."""
    agent = MagicMock()
    agent.agent_id = "pjm-agent-test"
    agent._db_manager = None
    agent._event_bus = MagicMock()
    agent._config = MagicMock()
    agent._config.members = []
    agent.handle_request = AsyncMock()
    agent.approve_decomposition = AsyncMock()
    agent.reject_decomposition = AsyncMock()
    return agent


@pytest.fixture
def test_app(mock_agent):
    """Create a test app without starting lifespan."""
    with patch("agents.pjm_agent.api.pm.get_agent", return_value=mock_agent):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from agents.pjm_agent.api.pm import router as pm_router

        app = FastAPI()
        app.include_router(pm_router)

        @app.get("/health")
        async def health():
            return {"status": "alive", "agent": mock_agent.agent_id}

        @app.get("/health/ready")
        async def readiness():
            checks = {"database": False, "scheduler": False, "config_loaded": False}
            try:
                if mock_agent._db_manager:
                    checks["database"] = True
            except Exception:
                pass
            checks["scheduler"] = False
            checks["config_loaded"] = (
                len(mock_agent._config.members) > 0 if mock_agent._config else False
            )
            all_ok = checks["database"] and checks["scheduler"]
            return JSONResponse(
                status_code=200 if all_ok else 503,
                content={"status": "ready" if all_ok else "degraded", "checks": checks},
            )

        yield app


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """GET /health returns alive."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"
    assert data["agent"] == "pjm-agent-test"


@pytest.mark.asyncio
async def test_readiness_endpoint(test_app, mock_agent):
    """GET /health/ready returns readiness state."""
    mock_agent._db_manager = MagicMock()
    mock_agent._event_bus = MagicMock()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    # scheduler is False, so all_ok is False and returns 503.
    assert resp.status_code == 503
    data = resp.json()
    assert "checks" in data


@pytest.mark.asyncio
async def test_readiness_degraded(test_app, mock_agent):
    """Database unavailability returns degraded."""
    mock_agent._db_manager = None
    mock_agent._event_bus = None

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"


@pytest.mark.asyncio
async def test_config_endpoint(test_app, mock_agent):
    """GET /api/v1/pm/config returns PM configuration."""
    mock_agent.handle_request.return_value = {
        "members": [{"name": "Alice"}],
        "projects": [{"name": "P1"}],
        "rules": [],
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["members"] == [{"name": "Alice"}]
    assert data["projects"] == [{"name": "P1"}]
    mock_agent.handle_request.assert_called_once_with({"action": "config"})


@pytest.mark.asyncio
async def test_alerts_endpoint(test_app, mock_agent):
    """GET /api/v1/pm/alerts returns alert list."""
    mock_agent.handle_request.return_value = {
        "alerts": [
            {"type": "deadline", "task": "T1", "message": "已逾期 2 天", "severity": "critical"},
        ]
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["type"] == "deadline"
    mock_agent.handle_request.assert_called_once_with({"action": "alerts"})


@pytest.mark.asyncio
async def test_config_endpoint_error(test_app, mock_agent):
    """Configuration retrieval failure returns 500."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/config")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to get PM configuration. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_CONFIG_FAILED.value


@pytest.mark.asyncio
async def test_config_refresh_error_sets_error_code(test_app, mock_agent):
    """Configuration refresh failures expose a stable PM API error code."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/pm/config/refresh")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to refresh PM configuration. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_CONFIG_REFRESH_FAILED.value


@pytest.mark.asyncio
async def test_alerts_endpoint_error_sets_error_code(test_app, mock_agent):
    """Alert list failures expose a stable PM API error code."""
    mock_agent.handle_request.side_effect = Exception("bitable error")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/alerts")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to get PM alerts. Please retry later."
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_ALERTS_FAILED.value


@pytest.mark.asyncio
async def test_alerts_endpoint_empty(test_app, mock_agent):
    """No alerts returns an empty list."""
    mock_agent.handle_request.return_value = {"alerts": []}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["alerts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "expected_request", "expected_status", "expected_detail", "expected_code"),
    [
        (
            "/api/v1/pm/report/daily",
            {"action": "daily_report"},
            500,
            "Failed to generate daily report. Please retry later.",
            ApiErrorCode.PM_DAILY_REPORT_FAILED.value,
        ),
        (
            "/api/v1/pm/report/weekly",
            {"action": "weekly_report"},
            500,
            "Failed to generate weekly report. Please retry later.",
            ApiErrorCode.PM_WEEKLY_REPORT_FAILED.value,
        ),
        (
            "/api/v1/pm/decompose/123/retry",
            {"action": "retry_decompose", "wp_id": 123},
            400,
            "Failed to retry decomposition. Please retry later.",
            ApiErrorCode.PM_DECOMPOSITION_RETRY_FAILED.value,
        ),
    ],
)
async def test_result_errors_do_not_expose_internal_details(
    test_app,
    mock_agent,
    path,
    expected_request,
    expected_status,
    expected_detail,
    expected_code,
):
    """Agent result errors are logged server-side and sanitized for callers."""
    mock_agent.handle_request.return_value = {"error": "Traceback: database password is exposed"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(path)

    assert resp.status_code == expected_status
    assert resp.json()["detail"] == expected_detail
    assert resp.headers["x-error-code"] == expected_code
    assert "Traceback" not in resp.json()["detail"]
    assert "database password" not in resp.json()["detail"]
    mock_agent.handle_request.assert_awaited_once_with(expected_request)


@pytest.mark.asyncio
async def test_get_decomposition_not_found_sets_error_code(test_app, mock_agent):
    """GET /api/v1/pm/decompose/{wp_id} exposes a stable not-found code."""
    mock_agent.handle_request.return_value = {}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/pm/decompose/123")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Record not found"
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_DECOMPOSITION_NOT_FOUND.value
    mock_agent.handle_request.assert_awaited_once_with(
        {"action": "get_decompose", "wp_id": 123}
    )


@pytest.mark.asyncio
async def test_approve_decomposition_forwards_operator(test_app, mock_agent):
    """POST /api/v1/pm/decompose/{wp_id}/approve preserves the operator identity."""
    mock_agent.approve_decomposition.return_value = {
        "subject": "Split feature",
        "story_count": 1,
        "task_count": 3,
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/approve",
            json={"operator": "alice"},
        )

    assert resp.status_code == 200
    assert resp.json()["action"] == "approve"
    mock_agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="alice",
    )


@pytest.mark.asyncio
async def test_approve_decomposition_unavailable_sets_error_code(test_app, mock_agent):
    """Unavailable approval records keep legacy status/detail plus stable code."""
    mock_agent.approve_decomposition.return_value = None

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/approve",
            json={"operator": "alice"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Record not found or status is not pending"
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_DECOMPOSITION_UNAVAILABLE.value
    mock_agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="alice",
    )


@pytest.mark.asyncio
async def test_approve_decomposition_surfaces_approval_error(test_app, mock_agent):
    """Approval errors must not be converted into success responses."""
    mock_agent.approve_decomposition.return_value = {
        "error": "approved_by required for control-plane approval",
        "wp_id": 123,
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/approve",
            json={},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "approved_by required for control-plane approval"
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_DECOMPOSITION_FORBIDDEN.value
    mock_agent.approve_decomposition.assert_awaited_once_with(
        123,
        approved_by="",
    )


@pytest.mark.asyncio
async def test_reject_decomposition_forwards_reason(test_app, mock_agent):
    """POST /api/v1/pm/decompose/{wp_id}/reject preserves the rejection reason."""
    mock_agent.reject_decomposition.return_value = {"subject": "Split feature"}

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/reject",
            json={"operator": "alice", "reason": "not useful"},
        )

    assert resp.status_code == 200
    assert resp.json()["action"] == "reject"
    mock_agent.reject_decomposition.assert_awaited_once_with(
        123,
        rejected_by="alice",
        reason="not useful",
    )


@pytest.mark.asyncio
async def test_reject_decomposition_unavailable_sets_error_code(test_app, mock_agent):
    """Unavailable rejection records keep legacy status/detail plus stable code."""
    mock_agent.reject_decomposition.return_value = None

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/reject",
            json={"operator": "alice", "reason": "not useful"},
        )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Record not found or status is not pending"
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_DECOMPOSITION_UNAVAILABLE.value
    mock_agent.reject_decomposition.assert_awaited_once_with(
        123,
        rejected_by="alice",
        reason="not useful",
    )


@pytest.mark.asyncio
async def test_reject_decomposition_surfaces_approval_error(test_app, mock_agent):
    """Rejection approval errors must not be converted into success responses."""
    mock_agent.reject_decomposition.return_value = {
        "error": "rejected_by required for control-plane rejection",
        "wp_id": 123,
    }

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/pm/decompose/123/reject",
            json={"reason": "not useful"},
        )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "rejected_by required for control-plane rejection"
    assert resp.headers["x-error-code"] == ApiErrorCode.PM_DECOMPOSITION_FORBIDDEN.value
    mock_agent.reject_decomposition.assert_awaited_once_with(
        123,
        rejected_by="",
        reason="not useful",
    )
