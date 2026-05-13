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

PYTHON_RUNTIME_ROLES = {
    "ai-core": "agents.requirement_manager.app.main:app",
    "sync-module": "shared.capabilities.sync.app.main:app",
    "analysis-module": "shared.capabilities.analysis.app.main:app",
    "pjm-agent": "agents.pjm_agent.app.main:app",
    "chat-agent": "services.gateways.user_interaction.app.main:app",
    "qa-agent": "agents.qa_agent.app.main:app",
    "dev-agent": "agents.dev_agent.app.main:app",
    "evolution-module": "shared.capabilities.evolution.app.main:app",
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
    """Per-package requirements files must include LiteLLM when their runtime uses LLMGateway."""
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
            "does not install litellm for the unified Docker runtime image"
        )


def test_unified_agents_image_dispatches_every_role() -> None:
    """The platform Dockerfile + entrypoint must reach every agent and capability."""
    dockerfile = Path("docker/Dockerfile.agents").read_text(encoding="utf-8")
    entrypoint = Path("docker/agents-entrypoint.sh").read_text(encoding="utf-8")

    # Single platform image: one runtime stage, no per-role builder/runtime stages.
    assert "AS runtime" in dockerfile
    assert "AS builder" in dockerfile
    assert 'pip install -i "$PIP_INDEX_URL"' not in dockerfile
    assert 'if [ -n "$PIP_INDEX_URL" ]' in dockerfile
    assert "FROM builder-base AS evolution-builder" not in dockerfile
    assert "FROM runtime-base AS evolution-module" not in dockerfile

    # Every role appears in the dispatcher and points at the right ASGI app.
    assert "cell-supervisor.py" in dockerfile
    assert "cell)" in entrypoint
    assert "wisdoverse-cell-supervisor" in entrypoint
    supervisor = Path("docker/cell-supervisor.py").read_text(encoding="utf-8")
    assert "bootstrap_control_plane_tables()" in supervisor
    assert "CELL_BOOTSTRAP_CONTROL_PLANE" in supervisor
    assert '"--no-control-socket"' in supervisor
    for role, app_path in PYTHON_RUNTIME_ROLES.items():
        assert role in entrypoint, f"entrypoint missing dispatch case for {role}"
        assert app_path in entrypoint, (
            f"entrypoint dispatcher does not bind {role} to {app_path}"
        )


def test_default_compose_exposes_cell_runtime_instead_of_split_agents() -> None:
    """The default root Compose file must present Cell as the Docker runtime boundary."""
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    cell = _compose_service_block(compose, "cell")
    assert "wisdoverse/cell-agents:" in cell
    assert 'command: ["cell"]' in cell
    assert "ports:" not in cell
    for internal_port in ("8000", "50051", "8010", "8011", "8012", "8013", "8014", "8015", "8016"):
        assert f'- "{internal_port}"' in cell

    gateway = _compose_service_block(compose, "gateway")
    assert "ports:" not in gateway
    assert 'expose:\n      - "8080"' in gateway
    assert "GATEWAY_GRPC_AI_SERVICE_ADDR: cell:50051" in gateway
    assert "GATEWAY_FEISHU_CHAT_AGENT_ADDR: cell:8013" in gateway
    assert "GATEWAY_FEISHU_PM_AGENT_ADDR: cell:8012" in gateway
    assert "cell:" in gateway

    for role in PYTHON_RUNTIME_ROLES:
        block = _compose_service_block(compose, role)
        assert 'profiles: ["split-agents"]' in block, (
            f"{role} must not start in the default Cell compose topology"
        )
        assert "ports:" not in block, f"{role} must not publish host ports"


def test_development_override_only_publishes_infrastructure_ports() -> None:
    """Local Docker can expose infra for tools without exposing agent/module ports."""
    override = Path("docker-compose.override.yml").read_text(encoding="utf-8")

    for service in ("postgres", "redis", "milvus"):
        block = _compose_service_block(override, service)
        assert "ports:" in block, f"{service} should be reachable from local tools"

    assert "${POSTGRES_HOST_PORT:-15432}:5432" in override
    assert "${REDIS_HOST_PORT:-16379}:6379" in override

    for service in ("cell", "gateway"):
        block = _compose_service_block(override, service)
        assert "ports:" not in block, f"{service} should stay behind Traefik"

    assert "backend:\n    internal: false" in override

    root_compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    root_backend = root_compose.split("  backend:", 1)[1].split("  frontend:", 1)[0]
    assert "driver: bridge" in root_backend
    assert "internal: true" in root_backend
    milvus = _compose_service_block(root_compose, "milvus")
    assert "DEPLOY_MODE: STANDALONE" in milvus
    assert 'ETCD_USE_EMBED: "true"' in milvus


def test_compose_topologies_share_unified_agents_image() -> None:
    """Every Python service in every Compose topology must share the platform image and dispatch its role."""
    compose_path = Path("docker/compose/docker-compose.app.yml")
    compose = compose_path.read_text(encoding="utf-8")
    for role in PYTHON_RUNTIME_ROLES:
        assert f"  {role}:" in compose, f"{compose_path} is missing {role}"
        block = _compose_service_block(compose, role)
        assert (
            "wisdoverse/cell-agents:" in block
        ), f"{compose_path} does not point {role} at the unified platform image"
        assert (
            f'- {role}' in block or f'"{role}"' in block
        ), f"{compose_path} does not dispatch {role} via command"


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
    assert "image: ${REGISTRY:-}wisdoverse/cell-rust-gateway:${VERSION:-latest}" in app_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in app_gateway
    assert "image: ${REGISTRY:-}wisdoverse/cell-gateway:${VERSION:-latest}" not in app_gateway
    assert "context: ../../gateway" not in app_gateway

    root_gateway = _compose_service_block(root_compose, "gateway")
    assert "dockerfile: rust/gateway/Dockerfile" in root_gateway
    assert "image: ${REGISTRY:-}wisdoverse/cell-rust-gateway:${VERSION:-latest}" in root_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in root_gateway

    prod_compose = Path("docker/compose/docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )
    prod_gateway = _compose_service_block(prod_compose, "gateway")
    assert "image: ${REGISTRY}wisdoverse/cell-rust-gateway:${VERSION}" in prod_gateway
    assert "build: !reset null" in prod_gateway
    assert "GATEWAY_IMPLEMENTATION: rust" in prod_gateway

    root_prod = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    root_prod_gateway = _compose_service_block(root_prod, "gateway")
    assert "image: ${REGISTRY}wisdoverse/cell-rust-gateway:${VERSION}" in root_prod_gateway
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
    assert "image: ${REGISTRY}wisdoverse/cell-rust-gateway:${VERSION}" in prod_shadow_runtime
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
    assert "image: ${REGISTRY:-}wisdoverse/cell-rust-gateway:${VERSION:-latest}" in shadow_runtime
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


def test_production_overrides_share_unified_agents_image() -> None:
    """Production Compose overlays must point every Python service at the unified image and disable local builds."""
    root_prod = Path("docker-compose.prod.yml").read_text(encoding="utf-8")
    root_cell = _compose_service_block(root_prod, "cell")
    assert "image: ${REGISTRY}wisdoverse/cell-agents:${VERSION}" in root_cell
    assert 'command: ["cell"]' in root_cell
    assert "build: !reset null" in root_cell

    compose_path = Path("docker/compose/docker-compose.prod.yml")
    compose = compose_path.read_text(encoding="utf-8")
    for role in PYTHON_RUNTIME_ROLES:
        assert f"  {role}:" in compose, f"{compose_path} is missing {role}"
        assert (
            "image: ${REGISTRY}wisdoverse/cell-agents:${VERSION}" in compose
        ), f"{compose_path} does not pin the unified agents image"
        block = _compose_service_block(compose, role)
        assert "build: !reset null" in block, (
            f"{compose_path} must disable local build for {role} in production"
        )


def test_docker_init_script_creates_compose_runtime_db_users() -> None:
    """Clean Docker databases must contain every per-runtime DB user used by Compose."""
    init_sh = Path("docker/init-scripts/02-agent-users.sh").read_text(encoding="utf-8")
    init_sql = Path("docker/init-scripts/02-agent-users.sql").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "--host \"${POSTGRES_HOST}\"" in init_sh
    assert "current_database()" in init_sql
    assert "GRANT CONNECT ON DATABASE wisdoverse-cell" not in init_sql
    assert "GRANT USAGE, CREATE ON SCHEMA public" in init_sql
    assert "up: db-bootstrap" in makefile
    assert "up -d --wait postgres" in makefile
    assert "/docker-entrypoint-initdb.d/02-agent-users.sh" in makefile
    assert "/docker-entrypoint-initdb.d/02-agent-users.sql" in makefile

    for db_user in RUNTIME_DB_USERS:
        assert f'create_or_update_role "{db_user}"' in init_sh
        assert f"TO {db_user}" in init_sql


def test_runtime_apps_wire_db_manager_into_infra_health() -> None:
    """Runtime health checks must validate Postgres through the service DB manager."""
    app_paths = [
        Path("agents/pjm_agent/app/main.py"),
        Path("agents/qa_agent/app/main.py"),
        Path("shared/capabilities/sync/app/main.py"),
        Path("shared/capabilities/analysis/app/main.py"),
        Path("services/gateways/user_interaction/app/main.py"),
    ]
    for app_path in app_paths:
        source = app_path.read_text(encoding="utf-8")
        assert "from ..db.database import db_manager" in source
        assert "InfraHealthPlugin(db_manager=db_manager" in source or (
            "InfraHealthPlugin(\n"
            in source
            and "db_manager=db_manager" in source
        )


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
