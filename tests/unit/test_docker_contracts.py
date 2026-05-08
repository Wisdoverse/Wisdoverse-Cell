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
    "sync-module": "sync-module",
    "analysis-module": "analysis-module",
    "pjm-agent": "pjm-agent",
    "chat-agent": "chat-agent",
    "qa-agent": "qa-agent",
    "dev-agent": "dev-agent",
    "evolution-module": "evolution-module",
}

RUNTIME_DB_USERS = {
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
    assert "FROM runtime-base AS evolution-module" in dockerfile
    assert "FROM sync-module AS sync-agent" not in dockerfile
    assert "FROM analysis-module AS analysis-agent" not in dockerfile
    assert "FROM evolution-module AS evolution-agent" not in dockerfile
    assert "shared.capabilities.evolution.app.main:app" in dockerfile

    assert "  evolution-module:" in compose
    assert "target: evolution-module" in compose
    assert "${EVOLUTION_MODULE_PORT:-8016}:8016" in compose


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


def test_rust_gateway_is_default_and_only_gateway_runtime() -> None:
    """The canonical gateway runtime must be Rust with no Go rollback overlay."""
    app = Path("docker/compose/docker-compose.app.yml").read_text(encoding="utf-8")
    root_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    prod_shadow = Path(
        "docker/compose/docker-compose.rust-gateway-prod-shadow.yml"
    ).read_text(encoding="utf-8")
    shadow = Path("docker/compose/docker-compose.rust-gateway-shadow.yml").read_text(
        encoding="utf-8"
    )
    env_example = Path(".env.example").read_text(encoding="utf-8")

    app_gateway = _compose_service_block(app, "gateway")
    assert "dockerfile: rust/gateway/Dockerfile" in app_gateway
    assert "image: ${REGISTRY:-}projectcell/rust-gateway:${VERSION:-latest}" in app_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in app_gateway
    assert "image: ${REGISTRY:-}projectcell/gateway:${VERSION:-latest}" not in app_gateway
    assert "context: ../../gateway" not in app_gateway

    root_gateway = _compose_service_block(root_compose, "gateway")
    assert "dockerfile: rust/gateway/Dockerfile" in root_gateway
    assert "image: ${REGISTRY:-}projectcell/rust-gateway:${VERSION:-latest}" in root_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in root_gateway

    prod_compose = Path("docker/compose/docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    prod_gateway = _compose_service_block(prod_compose, "gateway")
    assert "image: ${REGISTRY}projectcell/rust-gateway:${VERSION}" in prod_gateway
    assert "build: !reset null" in prod_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in prod_gateway

    root_prod = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    root_prod_gateway = _compose_service_block(root_prod, "gateway")
    assert "image: ${REGISTRY}projectcell/rust-gateway:${VERSION}" in root_prod_gateway
    assert "build: !reset null" in root_prod_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in root_prod_gateway

    assert not Path("gateway").exists()
    assert not Path("docker/compose/docker-compose.go-gateway-legacy.yml").exists()
    assert not Path("docker/compose/docker-compose.go-gateway-legacy-prod.yml").exists()

    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "COMPOSE_RUST_GATEWAY_PROD" in makefile
    assert "COMPOSE_RUST_GATEWAY_PROD_SHADOW" in makefile
    assert "COMPOSE_GO_GATEWAY_LEGACY" not in makefile
    assert "COMPOSE_GO_GATEWAY_LEGACY_PROD" not in makefile
    assert "RUST_GATEWAY_LOCAL_EVIDENCE_REPORT ?=" in makefile
    assert "rust-gateway-prod-gate:" in makefile
    assert "rust-gateway-local-shadow-gate:" in makefile
    assert "RUST_GATEWAY_PROD_ALLOW_LOCAL_URLS=true" in makefile
    assert "rust-gateway-prod-shadow-check:" in makefile
    assert "rust-gateway-prod-shadow-config:" in makefile
    assert "rust-gateway-prod-cutover-config:" in makefile
    assert "rust_gateway_prod_shadow_preflight.py" in makefile
    assert "RUST_GATEWAY_PROD_EVIDENCE_REPORT ?=" in makefile
    assert "up-prod-rust-gateway-shadow: rust-gateway-prod-shadow-config" in makefile
    assert (
        "up-prod-rust-gateway: rust-gateway-prod-cutover-config rust-gateway-prod-gate"
        in makefile
    )
    assert "up-dev-go-gateway-legacy:" not in makefile
    assert "up-prod-go-gateway-legacy:" not in makefile
    assert "$(COMPOSE_GO_GATEWAY_LEGACY_PROD)" not in makefile

    prod_shadow_runtime = _compose_service_block(prod_shadow, "rust-gateway-shadow")
    assert "image: ${REGISTRY}projectcell/rust-gateway:${VERSION}" in prod_shadow_runtime
    assert "build: !reset null" in prod_shadow_runtime
    assert "GATEWAY_IMPLEMENTATION: rust-shadow" in prod_shadow_runtime
    assert "RUST_GATEWAY_SHADOW_HOST is required" in prod_shadow_runtime
    assert "traefik.http.routers.rust-gateway-shadow.rule" in prod_shadow_runtime
    assert "traefik.http.routers.rust-gateway-shadow.entrypoints=websecure" in prod_shadow_runtime
    assert "traefik.http.routers.rust-gateway-shadow.tls=true" in prod_shadow_runtime
    assert (
        "traefik.http.routers.rust-gateway-shadow.tls.certresolver=letsencrypt"
        in prod_shadow_runtime
    )
    assert "ports:" not in prod_shadow_runtime

    shadow_gateway = _compose_service_block(shadow, "gateway")
    assert "${GATEWAY_PORT:-8080}:8080" in shadow_gateway
    assert "replicas: 1" in shadow_gateway
    assert "image:" not in shadow_gateway
    assert "GATEWAY_IMPLEMENTATION:" not in shadow_gateway

    shadow_runtime = _compose_service_block(shadow, "rust-gateway-shadow")
    assert "image: ${REGISTRY:-}projectcell/rust-gateway:${VERSION:-latest}" in shadow_runtime
    assert "GATEWAY_IMPLEMENTATION: rust-shadow" in shadow_runtime
    assert "${RUST_GATEWAY_SHADOW_PORT:-18080}:8080" in shadow_runtime
    assert "external: false" in shadow
    assert "RUST_GATEWAY_SHADOW_PORT=18080" in env_example
    assert "RUST_GATEWAY_LOCAL_EVIDENCE_REPORT=" in env_example
    assert "GATEWAY_HOST=" in env_example
    assert "HTTPS_PORT=443" in env_example
    assert "TRAEFIK_ACME_EMAIL=" in env_example

    proxy_compose = Path("docker/compose/docker-compose.proxy.yml").read_text(
        encoding="utf-8"
    )
    assert "image: traefik:v3.6" in proxy_compose
    prod_gateway = _compose_service_block(prod_compose, "gateway")
    assert "GATEWAY_HOST is required" in prod_gateway
    assert "traefik.http.routers.gateway.rule=Host(`${GATEWAY_HOST:?" in prod_gateway
    assert "PathPrefix(`/`)" in prod_gateway
    assert "traefik.http.routers.gateway.entrypoints=websecure" in prod_gateway
    assert "traefik.http.routers.gateway.tls=true" in prod_gateway
    assert "traefik.http.routers.gateway.tls.certresolver=letsencrypt" in prod_gateway
    prod_traefik_service = _compose_service_block(prod_compose, "traefik")
    assert "--entrypoints.websecure.address=:443" in prod_traefik_service
    assert "--providers.file.directory=/etc/traefik/dynamic" in prod_traefik_service
    assert "--certificatesresolvers.letsencrypt.acme.email=${TRAEFIK_ACME_EMAIL:?" in prod_traefik_service
    assert "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json" in prod_traefik_service
    assert (
        "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
        in prod_traefik_service
    )
    assert "TRAEFIK_ACME_EMAIL is required" in prod_traefik_service
    assert "${HTTPS_PORT:-443}:443" in prod_compose
    assert "traefik_letsencrypt:/letsencrypt" in prod_compose
    assert "/etc/traefik/traefik.yml" not in prod_traefik_service


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


def test_docker_init_script_creates_compose_runtime_db_users() -> None:
    """Clean Docker databases must contain every per-runtime DB user used by Compose."""
    init_sh = Path("docker/init-scripts/02-agent-users.sh").read_text(encoding="utf-8")
    init_sql = Path("docker/init-scripts/02-agent-users.sql").read_text(encoding="utf-8")
    for db_user in RUNTIME_DB_USERS:
        assert f'create_or_update_role "{db_user}"' in init_sh
        assert f"TO {db_user}" in init_sql


def test_production_compose_requires_runtime_db_passwords() -> None:
    """Production overlays must not fall back to local-dev runtime DB passwords."""
    prod_files = [
        Path("docker-compose.prod.yml"),
        Path("docker/compose/docker-compose.prod.yml"),
    ]
    required_vars = {
        "CHAT_AGENT_DB_PASSWORD",
        "PM_AGENT_DB_PASSWORD",
        "SYNC_MODULE_DB_PASSWORD",
        "ANALYSIS_MODULE_DB_PASSWORD",
        "QA_AGENT_DB_PASSWORD",
        "DEV_AGENT_DB_PASSWORD",
        "EVOLUTION_MODULE_DB_PASSWORD",
    }
    for compose_path in prod_files:
        compose = compose_path.read_text(encoding="utf-8")
        for var_name in required_vars:
            assert f"${{{var_name}:?{var_name} is required}}" in compose
