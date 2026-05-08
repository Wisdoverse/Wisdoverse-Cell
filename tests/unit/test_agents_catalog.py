import ast
import re
from pathlib import Path

from shared.control_plane.agent_catalog import (
    ORGANIZATION_ROLE_TEMPLATES,
    RUNTIME_MODULES,
    create_organization_role,
    get_business_runtime_agents,
    get_managed_agent_catalog,
    get_organization_role_template,
    get_runtime_module,
    is_organization_role_template,
    is_runtime_module,
)
from shared.control_plane.models import AgentInteractionMode, AgentKind


def _service_agent_path(package_path: str) -> Path:
    return Path(*package_path.split(".")) / "service" / "agent.py"


def _base_agent_classes(tree: ast.Module) -> list[ast.ClassDef]:
    classes: list[ast.ClassDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {
            base.id
            for base in node.bases
            if isinstance(base, ast.Name)
        } | {
            base.attr
            for base in node.bases
            if isinstance(base, ast.Attribute)
        }
        if "BaseAgent" in base_names:
            classes.append(node)
    return classes


def _super_agent_id(class_def: ast.ClassDef) -> str | None:
    for node in ast.walk(class_def):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "__init__"
            and isinstance(node.func.value, ast.Call)
            and isinstance(node.func.value.func, ast.Name)
            and node.func.value.func.id == "super"
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg == "agent_id" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
    return None


def test_runtime_modules_keep_canonical_package_boundaries() -> None:
    expected_prefix_by_boundary = {
        "root_agent": "agents.",
        "gateway": "services.gateways.",
        "orchestration": "services.orchestration.",
        "capability": "shared.capabilities.",
    }
    root_business_packages = {
        "agents.requirement_manager",
        "agents.pjm_agent",
        "agents.qa_agent",
        "agents.dev_agent",
    }

    assert RUNTIME_MODULES
    for module in RUNTIME_MODULES:
        assert module.agent_kind != AgentKind.ORGANIZATION_ROLE
        assert module.runtime_boundary in expected_prefix_by_boundary
        if module.runtime_boundary == "root_agent":
            assert module.package_path in root_business_packages
        else:
            assert module.package_path.startswith(
                expected_prefix_by_boundary[module.runtime_boundary]
            )


def test_runtime_modules_use_shared_app_factory() -> None:
    for module in RUNTIME_MODULES:
        app_main = Path(*module.package_path.split(".")) / "app" / "main.py"

        assert app_main.exists(), f"{module.agent_id} is missing {app_main}"
        source = app_main.read_text()
        assert "create_agent_app" in source, (
            f"{module.agent_id} must use shared create_agent_app runtime factory"
        )


def test_runtime_modules_implement_base_agent_contract() -> None:
    for module in RUNTIME_MODULES:
        service_agent = _service_agent_path(module.package_path)
        assert service_agent.exists(), f"{module.agent_id} is missing {service_agent}"

        tree = ast.parse(service_agent.read_text())
        base_agent_classes = _base_agent_classes(tree)
        assert base_agent_classes, f"{module.agent_id} must define a BaseAgent subclass"

        matching_classes = [
            class_def
            for class_def in base_agent_classes
            if _super_agent_id(class_def) == module.agent_id
        ]
        assert matching_classes, (
            f"{module.agent_id} must pass its stable catalog ID to BaseAgent"
        )

        methods = {
            item.name
            for class_def in matching_classes
            for item in class_def.body
            if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef)
        }
        assert {"handle_event", "handle_request", "health_check"}.issubset(methods), (
            f"{module.agent_id} must implement handle_event, handle_request, and health_check"
        )


def test_runtime_modules_expose_event_contracts() -> None:
    modules = {module.agent_id: module for module in RUNTIME_MODULES}

    assert modules["chat-agent"].published_events == (
        "chat.pm-query",
        "coordinator.command",
        "sync.trigger",
    )
    assert "sync.trigger" in modules["sync-module"].subscribed_events
    assert modules["coordinator"].published_events == (
        "coordinator.response",
        "coordinator.dispatch",
        "pm.tasks-ready-for-dev",
        "qa.run-requested",
    )
    assert "qa.run-requested" in modules["dev-agent"].published_events
    assert "qa.run-requested" in modules["qa-agent"].subscribed_events


def test_organization_roles_are_control_plane_templates_not_packages() -> None:
    role_ids = {template.agent_id for template in ORGANIZATION_ROLE_TEMPLATES}

    assert {"ceo", "cto", "cpo", "coo"}.issubset(role_ids)
    assert all(
        template.agent_kind == AgentKind.ORGANIZATION_ROLE
        and template.interaction_mode == AgentInteractionMode.ROUTED
        for template in ORGANIZATION_ROLE_TEMPLATES
    )
    assert not any((Path("agents") / role_id).exists() for role_id in role_ids)


def test_catalog_distinguishes_runtime_modules_from_role_agents() -> None:
    assert is_runtime_module("requirement-manager")
    assert get_runtime_module("requirement-manager") is not None
    assert not is_organization_role_template("requirement-manager")

    assert is_organization_role_template("cto")
    assert get_organization_role_template("cto") is not None
    assert not is_runtime_module("cto")


def test_capability_module_legacy_agent_ids_resolve_to_canonical_modules() -> None:
    assert get_runtime_module("sync-agent") == get_runtime_module("sync-module")
    assert get_runtime_module("analysis-agent") == get_runtime_module("analysis-module")
    assert get_runtime_module("evolution-agent") == get_runtime_module("evolution-module")


def test_managed_catalog_exposes_root_role_templates_and_runtime_modules() -> None:
    catalog = get_managed_agent_catalog()
    entries_by_id = {entry.agent_id: entry for entry in catalog}

    assert len(entries_by_id) == len(catalog)
    assert {template.agent_id for template in ORGANIZATION_ROLE_TEMPLATES}.issubset(
        entries_by_id
    )
    assert {module.agent_id for module in RUNTIME_MODULES}.issubset(entries_by_id)

    cto = entries_by_id["cto"]
    assert cto.catalog_group == "organization_role_template"
    assert cto.package_path is None
    assert cto.runtime_boundary is None
    assert cto.implemented is False
    assert cto.business_agent is True
    assert cto.frontend_managed is True
    assert cto.root_catalog_managed is True

    requirement_manager = entries_by_id["requirement-manager"]
    assert requirement_manager.catalog_group == "runtime_module"
    assert requirement_manager.package_path == "agents.requirement_manager"
    assert requirement_manager.runtime_boundary == "root_agent"
    assert requirement_manager.subscribed_events
    assert requirement_manager.published_events
    assert requirement_manager.implemented is True
    assert requirement_manager.business_agent is True
    assert requirement_manager.frontend_managed is True
    assert requirement_manager.root_catalog_managed is False


def test_business_runtime_agents_are_real_implemented_agents() -> None:
    business_agent_ids = {module.agent_id for module in get_business_runtime_agents()}

    assert business_agent_ids == {
        "requirement-manager",
        "pjm-agent",
        "qa-agent",
        "dev-agent",
    }
    assert all(
        module.agent_kind == AgentKind.BUSINESS_RUNTIME_AGENT
        and module.implemented
        and module.business_agent
        and module.runtime_boundary == "root_agent"
        for module in get_business_runtime_agents()
    )


def test_channel_gateway_is_an_implemented_gateway_not_business_agent() -> None:
    channel = get_runtime_module("channel-gateway")

    assert channel is not None
    assert channel.package_path == "services.gateways.channel"
    assert channel.runtime_boundary == "gateway"
    assert channel.agent_kind == AgentKind.INTEGRATION_GATEWAY
    assert channel.implemented is True
    assert channel.business_agent is False


def test_role_template_creates_control_plane_agent_role() -> None:
    role = create_organization_role(
        "cto",
        company_id="company_1",
        capabilities=["Architecture decisions"],
        subscribed_events=["work_item.created"],
        published_events=["architecture.decision-proposed"],
        created_by="test",
    )

    assert role.company_id == "company_1"
    assert role.agent_id == "cto"
    assert role.display_name == "CTO"
    assert role.agent_kind == AgentKind.ORGANIZATION_ROLE
    assert role.interaction_mode == AgentInteractionMode.ROUTED
    assert role.adapter_type == "builtin"
    assert role.context_sources == ["control_plane"]
    assert role.capabilities == ["Architecture decisions"]
    assert role.subscribed_events == ["work_item.created"]
    assert role.published_events == ["architecture.decision-proposed"]
    assert role.created_by == "test"


def test_unknown_role_template_is_rejected() -> None:
    try:
        create_organization_role("requirement-manager", company_id="company_1")
    except KeyError as exc:
        assert "Unknown organization role agent" in str(exc)
    else:
        raise AssertionError("expected unknown organization-role template to fail")


def test_frontend_registry_matches_runtime_catalog() -> None:
    registry = Path("frontend/src/entities/agent/model/registry.ts").read_text()

    for module in RUNTIME_MODULES:
        key = (
            module.agent_id
            if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", module.agent_id)
            else f'"{module.agent_id}"'
        )
        match = re.search(rf"{re.escape(key)}:\s*\{{(?P<body>.*?)\n  \}},", registry, re.S)
        assert match, f"{module.agent_id} is missing from frontend AGENT_REGISTRY"

        body = match.group("body")
        assert f'agentKind: "{module.agent_kind.value}"' in body
        assert f'interactionMode: "{module.interaction_mode.value}"' in body
        assert f'runtimeBoundary: "{module.runtime_boundary}"' in body
        for event_type in module.subscribed_events:
            assert f'"{event_type}"' in body
        for event_type in module.published_events:
            assert f'"{event_type}"' in body


def test_frontend_builtin_registry_excludes_role_templates() -> None:
    registry = Path("frontend/src/entities/agent/model/registry.ts").read_text()

    for template in ORGANIZATION_ROLE_TEMPLATES:
        assert f'agentId: "{template.agent_id}"' in registry
        assert f'role: "{template.role}"' in registry
        assert f'title: "{template.title}"' in registry
        assert f'domain: "{template.domain}"' in registry
        assert f'"{template.agent_id}":' not in registry
