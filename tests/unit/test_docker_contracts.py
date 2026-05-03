"""Static checks for Docker runtime dependency contracts."""

import ast
from pathlib import Path

RUNTIME_REQUIREMENTS = {
    Path("agents/requirement_manager"): Path("agents/requirement_manager/requirements.txt"),
    Path("agents/pjm_agent"): Path("agents/pjm_agent/requirements.txt"),
    Path("agents/dev_agent"): Path("agents/dev_agent/requirements.txt"),
    Path("services/gateways/user_interaction"): Path(
        "services/gateways/user_interaction/requirements.txt"
    ),
    Path("shared/capabilities/analysis"): Path("shared/capabilities/analysis/requirements.txt"),
    Path("shared/capabilities/evolution"): Path("shared/capabilities/evolution/requirements.txt"),
}

PYTHON_RUNTIME_TARGETS = {
    "ai-core": "ai-core",
    "sync-agent": "sync-agent",
    "analysis-agent": "analysis-agent",
    "pjm-agent": "pjm-agent",
    "chat-agent": "chat-agent",
    "qa-agent": "qa-agent",
    "dev-agent": "dev-agent",
    "evolution-agent": "evolution-agent",
}

AGENT_DB_USERS = {
    "chat_agent",
    "pjm_agent",
    "sync_agent",
    "analysis_agent",
    "qa_agent",
    "dev_agent",
    "evolution_agent",
}


def _imports_llm_gateway(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "shared.infra.llm_gateway":
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "shared.infra.llm_gateway":
                    return True
    return False


def _compose_service_block(compose: str, service: str) -> str:
    lines = compose.splitlines()
    start = next(i for i, line in enumerate(lines) if line == f"  {service}:")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("  ") and not lines[i].startswith("    "):
            end = i
            break
    return "\n".join(lines[start:end])


def test_docker_runtime_units_that_use_llm_gateway_install_litellm() -> None:
    """Canonical Docker targets must include LiteLLM when their runtime uses LLMGateway."""
    for root, requirements_path in RUNTIME_REQUIREMENTS.items():
        uses_llm_gateway = any(
            _imports_llm_gateway(path)
            for path in root.rglob("*.py")
            if "tests" not in path.parts and "__pycache__" not in path.parts
        )
        if not uses_llm_gateway:
            continue

        requirements = requirements_path.read_text(encoding="utf-8")
        assert "litellm" in requirements.lower(), (
            f"{root} imports shared.infra.llm_gateway but {requirements_path} "
            "does not install litellm for its Docker runtime target"
        )


def test_evolution_capability_has_docker_runtime_boundary() -> None:
    """The evolution support capability must be independently deployable."""
    dockerfile = Path("docker/Dockerfile.agents").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "FROM builder-base AS evolution-builder" in dockerfile
    assert "FROM runtime-base AS evolution-agent" in dockerfile
    assert "shared.capabilities.evolution.app.main:app" in dockerfile

    assert "  evolution-agent:" in compose
    assert "target: evolution-agent" in compose
    assert "${EVOLUTION_AGENT_PORT:-8016}:8016" in compose


def test_compose_topologies_include_python_runtime_targets() -> None:
    """Root and layered Compose topologies must cover every Python runtime target."""
    compose_files = [
        Path("docker-compose.yml"),
        Path("docker/compose/docker-compose.app.yml"),
    ]
    for compose_path in compose_files:
        compose = compose_path.read_text(encoding="utf-8")
        for service, target in PYTHON_RUNTIME_TARGETS.items():
            assert f"  {service}:" in compose, f"{compose_path} is missing {service}"
            assert f"target: {target}" in compose, (
                f"{compose_path} is missing Docker target {target} for {service}"
            )


def test_production_overrides_use_prebuilt_python_runtime_images() -> None:
    """Production Compose overlays must not rebuild Python runtime services."""
    prod_files = [
        Path("docker-compose.prod.yml"),
        Path("docker/compose/docker-compose.prod.yml"),
    ]
    for compose_path in prod_files:
        compose = compose_path.read_text(encoding="utf-8")
        for service in PYTHON_RUNTIME_TARGETS:
            assert f"  {service}:" in compose, f"{compose_path} is missing {service}"
            assert f"image: ${{REGISTRY}}projectcell/{service}:${{VERSION}}" in compose
            service_block = _compose_service_block(compose, service)
            assert "build: !reset null" in service_block, (
                f"{compose_path} must disable local build for {service} in production"
            )


def test_docker_init_script_creates_compose_agent_db_users() -> None:
    """Clean Docker databases must contain every per-agent DB user used by Compose."""
    init_sql = Path("docker/init-scripts/02-agent-users.sql").read_text(encoding="utf-8")
    for db_user in AGENT_DB_USERS:
        assert f"CREATE ROLE {db_user}" in init_sql
        assert f"TO {db_user}" in init_sql
