from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.requirement_manager.api import admin
from agents.requirement_manager.core.admin_circuit_breaker import (
    CircuitBreakerAdminUseCase,
)


class _FakeCircuitBreakerGateway:
    def __init__(self, stats: dict) -> None:
        self._stats = stats
        self.reset_called = False

    def get_circuit_breaker_stats(self) -> dict:
        return self._stats

    def reset_circuit_breaker(self) -> None:
        self.reset_called = True


def _client(stats: dict | None = None) -> TestClient:
    app = FastAPI()
    if stats is not None:
        gateway = _FakeCircuitBreakerGateway(stats)
        app.dependency_overrides[admin.get_circuit_breaker_admin_use_case] = (
            lambda: CircuitBreakerAdminUseCase(gateway=gateway)
        )
    app.include_router(admin.router)
    return TestClient(app)


def test_circuit_breaker_accepts_llm_gateway_stats_shape() -> None:
    response = _client(
        {
            "state": "closed",
            "failure_count": 0,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": None,
        },
    ).get("/api/v1/admin/circuit-breaker")

    assert response.status_code == 200
    assert response.json()["failures"] == 0


def test_circuit_breaker_formats_epoch_last_failure_time() -> None:
    response = _client(
        {
            "state": "open",
            "failure_count": 5,
            "failure_threshold": 5,
            "recovery_timeout": 60,
            "last_failure_time": 1_767_225_600.0,
        },
    ).get("/api/v1/admin/circuit-breaker")

    assert response.status_code == 200
    body = response.json()
    assert body["failures"] == 5
    assert body["last_failure_time"] == "2026-01-01T00:00:00+00:00"
