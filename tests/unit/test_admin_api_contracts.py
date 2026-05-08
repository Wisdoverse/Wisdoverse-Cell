from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.requirement_manager.api import admin


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    return TestClient(app)


def test_circuit_breaker_accepts_llm_gateway_stats_shape(monkeypatch) -> None:
    monkeypatch.setattr(
        admin.llm_gateway,
        "get_circuit_breaker_stats",
        lambda: {
            "state": "closed",
            "failure_count": 0,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": None,
        },
    )

    response = _client().get("/api/v1/admin/circuit-breaker")

    assert response.status_code == 200
    assert response.json()["failures"] == 0


def test_circuit_breaker_formats_epoch_last_failure_time(monkeypatch) -> None:
    monkeypatch.setattr(
        admin.llm_gateway,
        "get_circuit_breaker_stats",
        lambda: {
            "state": "open",
            "failure_count": 5,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": 1_767_225_600.0,
        },
    )

    response = _client().get("/api/v1/admin/circuit-breaker")

    assert response.status_code == 200
    body = response.json()
    assert body["failures"] == 5
    assert body["last_failure_time"] == "2026-01-01T00:00:00+00:00"
