"""Per-runtime standalone startup tests.

Stage 4 pre-condition #4 in-process proof per
docs/architecture/migration-plan.md ("Non-prod deployment proves
the split"). The full operational proof — a runtime container in
staging for two weeks — requires real infrastructure. This test
suite covers the structural half: each runtime's FastAPI app
imports independently of the others and exposes the standard
`create_agent_app()` surface (`/health`, `/health/ready`,
`/openapi.json`).

If a runtime's app cannot import or define routes without its
sibling runtimes' state, it cannot be split — these tests would
catch that regression before a staging deploy hits it.

Lifespan startup is NOT exercised here because the agent runtimes
connect to Postgres/Redis on boot and the unit-test gate has no
infrastructure. Lifespan execution is covered by
`scripts/split_deploy_smoke.sh` (run via `make split-deploy-<runtime>`),
which boots each runtime in a Compose service and polls /ready.
"""

from __future__ import annotations

import importlib
import os

import pytest


def _import_app(module_path: str):
    """Import an agent's `app/main.py` and return its `app` symbol."""
    os.environ.setdefault("CONTROL_PLANE_ENABLED", "false")
    module = importlib.import_module(module_path)
    return module.app


@pytest.fixture(autouse=True)
def _disable_control_plane(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each runtime is tested in isolation; control plane is off."""
    monkeypatch.setenv("CONTROL_PLANE_ENABLED", "false")


@pytest.mark.parametrize(
    "module_path",
    [
        "agents.qa_agent.app.main",
        "agents.pjm_agent.app.main",
        "agents.dev_agent.app.main",
        "agents.requirement_manager.app.main",
    ],
)
def test_runtime_app_imports_standalone(module_path: str) -> None:
    """Each runtime's `app/main.py` imports without requiring the
    bundled `cell` topology. A failure here means the runtime cannot
    be deployed independently."""
    app = _import_app(module_path)
    assert app is not None
    # FastAPI app exposes routes, including the standard health endpoints.
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/health" in paths
    assert "/health/ready" in paths


@pytest.mark.parametrize(
    "module_path",
    [
        "agents.qa_agent.app.main",
        "agents.pjm_agent.app.main",
        "agents.dev_agent.app.main",
        "agents.requirement_manager.app.main",
    ],
)
def test_runtime_openapi_schema_is_reachable(module_path: str) -> None:
    """Each runtime exposes /openapi.json — the contract surface the
    `docs/api/openapi/<runtime>-v1.json` snapshots capture."""
    app = _import_app(module_path)
    schema = app.openapi()
    assert isinstance(schema, dict)
    assert "paths" in schema
    assert len(schema["paths"]) >= 1


@pytest.mark.parametrize(
    "module_path",
    [
        "agents.qa_agent.app.main",
        "agents.pjm_agent.app.main",
        "agents.dev_agent.app.main",
        "agents.requirement_manager.app.main",
    ],
)
def test_runtime_app_has_standard_health_endpoints(module_path: str) -> None:
    """Each runtime exposes the canonical health surface from
    `create_agent_app()`: `/health`, `/health/ready`, `/health/startup`,
    `/status`."""
    app = _import_app(module_path)
    paths = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/health/startup" in paths
    assert "/status" in paths


@pytest.mark.parametrize(
    "module_path,expected_prefix",
    [
        ("agents.qa_agent.app.main", "agents.qa_agent"),
        ("agents.pjm_agent.app.main", "agents.pjm_agent"),
        ("agents.dev_agent.app.main", "agents.dev_agent"),
        ("agents.requirement_manager.app.main", "agents.requirement_manager"),
    ],
)
def test_runtime_app_subprocess_import_is_isolated(
    module_path: str, expected_prefix: str
) -> None:
    """In a fresh subprocess, importing one runtime must not pull in
    any sibling runtime's modules.

    Subprocess isolation defeats the shared-pytest-process sys.modules
    bleed-over. Skipped in environments where invoking python -c
    fails (sandboxed CI runners that disable subprocess).
    """
    import subprocess
    import sys

    script = (
        "import os, sys\n"
        "os.environ['CONTROL_PLANE_ENABLED'] = 'false'\n"
        f"import {module_path}\n"
        "foreign = sorted(\n"
        "    m for m in sys.modules\n"
        f"    if m.startswith('agents.') and not m.startswith({expected_prefix!r})\n"
        ")\n"
        "if foreign:\n"
        "    print('FOREIGN:', foreign)\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{module_path} pulled in cross-runtime modules in fresh subprocess. "
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
