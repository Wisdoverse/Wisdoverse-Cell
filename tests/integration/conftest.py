"""
Integration Test Configuration

Provides fixtures for managing services during integration tests.

Usage modes:
1. CI: Services started by CI script (INTEGRATION_TEST=1)
2. Docker Compose: Services in containers (DOCKER_INTEGRATION=1)
3. Local Development: Fixtures start services as subprocesses
"""
import os
import signal
import subprocess
import time
from typing import Generator

import pytest
import requests


def _wait_for_service(url: str, timeout: int = 60) -> bool:
    """Wait for a service to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{url}/health", timeout=5)
            if resp.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return False


def _is_ci_mode() -> bool:
    """Check if running in CI mode where services are pre-started."""
    return (
        os.environ.get("INTEGRATION_TEST") == "1" or
        os.environ.get("DOCKER_INTEGRATION") == "1" or
        os.environ.get("CI") is not None
    )


@pytest.fixture(scope="session")
def ai_core_process() -> Generator[subprocess.Popen | None, None, None]:
    """
    Start the requirement manager agent as a subprocess for integration tests.

    In CI mode, services are started by the CI script, so this fixture
    yields None. For local development, it starts the requirements service.
    """
    if _is_ci_mode():
        yield None
        return

    # Local development: start requirement manager agent
    ai_core_url = os.environ.get("AI_CORE_URL", "http://localhost:8000")

    # Check if already running
    try:
        requests.get(f"{ai_core_url}/health", timeout=2)
        print("Requirements capability already running, skipping subprocess start")
        yield None
        return
    except requests.exceptions.RequestException:
        pass

    # Start requirement manager agent
    env = os.environ.copy()
    env.update({
        "POSTGRES_HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "POSTGRES_PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "POSTGRES_DB": os.environ.get("POSTGRES_DB", "projectcell_test"),
        "POSTGRES_USER": os.environ.get("POSTGRES_USER", "test"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD", "test"),
        "REDIS_HOST": os.environ.get("REDIS_HOST", "localhost"),
        "REDIS_PORT": os.environ.get("REDIS_PORT", "6379"),
    })

    proc = subprocess.Popen(
        [
            "python", "-m", "uvicorn",
            "agents.requirement_manager.app.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for startup
    if not _wait_for_service(ai_core_url, timeout=60):
        proc.terminate()
        proc.wait()
        pytest.fail("Requirements capability failed to start within 60 seconds")

    yield proc

    # Cleanup
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def gateway_process(ai_core_process) -> Generator[subprocess.Popen | None, None, None]:
    """
    Start Gateway as subprocess for integration tests.

    In CI mode, services are started by the CI script, so this fixture
    yields None. For local development, it starts the Gateway server.

    Depends on ai_core_process to ensure the requirement manager agent is started first.
    """
    if _is_ci_mode():
        yield None
        return

    gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8080")

    # Check if already running
    try:
        requests.get(f"{gateway_url}/health", timeout=2)
        print("Gateway already running, skipping subprocess start")
        yield None
        return
    except requests.exceptions.RequestException:
        pass

    # Find Rust gateway binary
    gateway_paths = [
        "/tmp/gateway",  # CI build location
        "./rust/target/debug/projectcell-rust-gateway",  # Local debug build
        "./rust/target/release/projectcell-rust-gateway",  # Local release build
    ]

    gateway_bin = None
    for path in gateway_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            gateway_bin = path
            break

    if not gateway_bin:
        pytest.skip(
            "Gateway binary not found. Build with: "
            "cargo build --manifest-path rust/Cargo.toml -p projectcell-rust-gateway"
        )

    # Start Gateway
    env = os.environ.copy()
    env.update({
        "HTTP_PORT": "8080",
        "AI_CORE_GRPC_ADDR": os.environ.get("AI_CORE_GRPC_ADDR", "localhost:50051"),
        "REDIS_ADDR": os.environ.get("REDIS_ADDR", "localhost:6379"),
    })

    proc = subprocess.Popen(
        [gateway_bin],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for startup
    if not _wait_for_service(gateway_url, timeout=30):
        proc.terminate()
        proc.wait()
        pytest.fail("Gateway failed to start within 30 seconds")

    yield proc

    # Cleanup
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def integration_services(ai_core_process, gateway_process):
    """
    Ensure all integration services are running.

    Use this fixture in tests that need both the requirement manager agent and Gateway.
    """
    ai_core_url = os.environ.get("AI_CORE_URL", "http://localhost:8000")
    gateway_url = os.environ.get("GATEWAY_URL", "http://localhost:8080")

    # Final verification
    assert _wait_for_service(ai_core_url, timeout=5), "Requirements capability not available"
    assert _wait_for_service(gateway_url, timeout=5), "Gateway not available"

    return {
        "ai_core_url": ai_core_url,
        "gateway_url": gateway_url,
    }
