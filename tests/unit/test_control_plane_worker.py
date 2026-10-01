"""Tests for the HTTP-only heartbeat scheduler worker."""

import asyncio
import os
import stat
from pathlib import Path

import httpx
import pytest

from services.orchestration.control_plane_worker.main import (
    ENDPOINT,
    HeartbeatWorker,
    WorkerConfig,
    backoff_delay,
    health_is_fresh,
    write_health_timestamp,
)


def worker_config(health_file: Path, **updates) -> WorkerConfig:
    values = {
        "base_url": "http://control-plane.test",
        "company_id": "cmp_test",
        "interval_seconds": 300,
        "timeout_seconds": 10,
        "internal_key": "internal-test-secret",
        "operator_token": "operator-test-secret",
        "health_file": health_file,
    }
    values.update(updates)
    return WorkerConfig(**values)


@pytest.mark.public
def test_run_once_posts_scheduler_contract_with_both_auth_headers(tmp_path):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"total": 0, "results": []})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            worker = HeartbeatWorker(worker_config(tmp_path / "health"), client)
            assert await worker.run_once() == 0

    asyncio.run(scenario())
    request = seen["request"]
    assert request.method == "POST"
    assert request.url.path == ENDPOINT
    assert request.read() == b'{"company_id":"cmp_test","limit":500}'
    assert request.headers["X-Internal-Key"] == "internal-test-secret"
    assert request.headers["X-Control-Plane-Operator-Token"] == "operator-test-secret"
    health_file = tmp_path / "health"
    assert health_file.exists()
    assert stat.S_IMODE(health_file.stat().st_mode) == 0o600


@pytest.mark.public
def test_retry_uses_bounded_exponential_backoff_and_stops_without_sleep(tmp_path):
    assert backoff_delay(1, jitter=1.0) == 1
    assert backoff_delay(3, jitter=1.2) == pytest.approx(4.8)
    assert backoff_delay(20, jitter=1.2) == 300

    async def scenario():
        stop = asyncio.Event()

        def handler(_request):
            stop.set()
            return httpx.Response(503)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await HeartbeatWorker(worker_config(tmp_path / "health"), client).run(stop)

    asyncio.run(scenario())
    assert not (tmp_path / "health").exists()


@pytest.mark.public
def test_shutdown_waits_for_active_http_call_to_drain(tmp_path):
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        stop = asyncio.Event()

        async def handler(_request):
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"total": 1, "results": []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            task = asyncio.create_task(
                HeartbeatWorker(worker_config(tmp_path / "health"), client).run(stop)
            )
            await entered.wait()
            stop.set()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            await asyncio.wait_for(task, timeout=1)
        assert (tmp_path / "health").exists()

    asyncio.run(scenario())


@pytest.mark.public
def test_healthcheck_requires_recent_private_timestamp(tmp_path):
    path = tmp_path / "health"
    write_health_timestamp(path)
    assert health_is_fresh(path, max_age_seconds=10)
    assert not health_is_fresh(path, max_age_seconds=10, now=path.stat().st_mtime + 11)
    os.chmod(path, 0o644)
    assert not health_is_fresh(path, max_age_seconds=10)


@pytest.mark.public
def test_environment_configuration_requires_secrets_and_valid_bounds(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTROL_PLANE_COMPANY_ID", "cmp_test")
    monkeypatch.setenv("CONTROL_PLANE_WORKER_INTERNAL_KEY", "test-internal-key")
    monkeypatch.setenv("CONTROL_PLANE_WORKER_OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setenv("CONTROL_PLANE_WORKER_HEALTH_FILE", str(tmp_path / "health"))
    assert WorkerConfig.from_env().company_id == "cmp_test"

    monkeypatch.delenv("CONTROL_PLANE_WORKER_OPERATOR_TOKEN")
    with pytest.raises(ValueError, match="both worker credentials"):
        WorkerConfig.from_env()


@pytest.mark.public
def test_worker_logs_do_not_include_credentials(caplog, tmp_path):
    async def scenario():
        stop = asyncio.Event()

        def handler(_request):
            stop.set()
            return httpx.Response(503, text="body includes secret")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await HeartbeatWorker(worker_config(tmp_path / "health"), client).run(stop)

    asyncio.run(scenario())
    assert "internal-test-secret" not in caplog.text
    assert "operator-test-secret" not in caplog.text
    assert "body includes secret" not in caplog.text
