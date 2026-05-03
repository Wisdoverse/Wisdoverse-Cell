"""Repository architecture boundary checks."""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from shared.messaging.outbound.models.events import ChannelEventTypes
from shared.schemas.event import EventTypes

AGENT_ROOTS = {
    "dev_agent",
    "pjm_agent",
    "qa_agent",
    "requirement_manager",
}


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if "tests" not in path.parts
        and not path.name.endswith("_pb2.py")
        and not path.name.endswith("_pb2_grpc.py")
    ]


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_agents_do_not_import_other_agent_internals() -> None:
    for agent_root in AGENT_ROOTS:
        root = Path("agents") / agent_root
        if not root.exists():
            continue
        for path in _python_files(root):
            for module in _imported_modules(path):
                if not module.startswith("agents."):
                    continue
                parts = module.split(".")
                if len(parts) < 2 or parts[1] == agent_root:
                    continue
                raise AssertionError(f"{path} imports cross-agent module {module}")


def test_services_and_shared_code_do_not_import_agent_internals() -> None:
    roots = [Path("services"), Path("shared/capabilities"), Path("shared/control_plane")]
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            for module in _imported_modules(path):
                if module.startswith("agents."):
                    raise AssertionError(f"{path} imports agent module {module}")


def test_runtime_code_does_not_import_llm_provider_sdks_directly() -> None:
    roots = [Path("agents"), Path("services"), Path("shared")]
    provider_modules = (
        "anthropic",
        "openai",
        "google.generativeai",
        "vertexai",
        "cohere",
        "mistralai",
        "groq",
    )
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if "tests" in path.parts:
                continue
            for module in _imported_modules(path):
                assert not any(
                    module == provider or module.startswith(f"{provider}.")
                    for provider in provider_modules
                ), (
                    f"{path} imports provider SDK module {module}; use LLMGateway"
                )


def test_runtime_code_uses_canonical_shared_paths() -> None:
    roots = [Path("agents"), Path("services"), Path("shared")]
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path.parts[:2] == ("shared", "services"):
                continue
            for module in _imported_modules(path):
                assert not module.startswith("shared.services"), (
                    f"{path} imports deprecated module {module}; use canonical shared paths"
                )


def test_runtime_code_uses_core_channel_abstractions() -> None:
    roots = [Path("agents"), Path("services"), Path("shared")]
    compat_paths = {
        Path("shared/integrations/channels/__init__.py"),
        Path("shared/integrations/channels/base.py"),
        Path("shared/integrations/channels/registry.py"),
        Path("shared/integrations/channels/types.py"),
    }
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path in compat_paths or path.parts[:2] == ("shared", "services"):
                continue
            for module in _imported_modules(path):
                assert not module.startswith("shared.integrations.channels"), (
                    f"{path} imports channel abstractions from {module}; "
                    "use shared.core.channels"
                )


def test_runtime_code_uses_core_id_contracts() -> None:
    roots = [Path("agents"), Path("services"), Path("shared")]
    compat_path = Path("shared/utils/id_generator.py")
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path == compat_path:
                continue
            for module in _imported_modules(path):
                assert module != "shared.utils.id_generator", (
                    f"{path} imports ID contracts from shared.utils; "
                    "use shared.core.ids"
                )


def test_shared_utils_stays_foundational() -> None:
    """shared/utils must not grow business logic or cross-boundary imports."""
    root = Path("shared/utils")
    allowed_files = {
        root / "__init__.py",
        root / "id_generator.py",
        root / "logger.py",
    }
    forbidden_import_prefixes = (
        "agents.",
        "services.",
        "shared.capabilities.",
        "shared.control_plane.",
        "shared.integrations.",
        "shared.messaging.",
    )

    for path in _python_files(root):
        assert path in allowed_files, (
            f"{path} is not a foundational utility; put it in shared/core, "
            "shared/infra, shared/integrations, or an owning feature boundary"
        )
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_import_prefixes), (
                f"{path} imports {module}; shared/utils must not depend on "
                "business or infrastructure boundaries"
            )


def test_feishu_card_renderers_live_in_shared_integrations() -> None:
    """Old local Feishu card modules must stay compatibility-only shims."""
    shim_paths = [
        Path("agents/requirement_manager/adapters/feishu_cards.py"),
        Path("agents/requirement_manager/integrations/feishu/cards/requirement.py"),
        Path("agents/pjm_agent/adapters/feishu_cards.py"),
        Path("services/gateways/user_interaction/adapters/feishu_cards.py"),
    ]
    for path in shim_paths:
        tree = ast.parse(path.read_text())
        class_names = [
            node.name for node in tree.body if isinstance(node, ast.ClassDef)
        ]
        assert not class_names, (
            f"{path} defines Feishu card classes {class_names}; "
            "put concrete card renderers in shared/integrations/feishu/cards"
        )
        for module in _imported_modules(path):
            assert module.startswith("shared.integrations.feishu.cards"), (
                f"{path} imports {module}; compatibility shims should only "
                "re-export shared Feishu card implementations"
            )


def test_qa_core_uses_card_renderer_port_for_feishu_payloads() -> None:
    """QA core must not construct concrete Feishu card payloads directly."""
    path = Path("agents/qa_agent/core/notifier.py")
    text = path.read_text()

    assert '"msg_type": "interactive"' not in text
    assert "shared.integrations.feishu" not in text
    assert ".card_ports" in text


def test_user_interaction_routes_do_not_build_feishu_cards_directly() -> None:
    """Gateway route/service code should use the shared Feishu card renderer."""
    roots = [
        Path("services/gateways/user_interaction/api"),
        Path("services/gateways/user_interaction/core"),
        Path("services/gateways/user_interaction/service"),
    ]
    for root in roots:
        for path in _python_files(root):
            for module in _imported_modules(path):
                assert module != "shared.integrations.feishu.cards.builder", (
                    f"{path} imports {module}; route/service layers should use "
                    "shared.integrations.feishu.cards.tools"
                )
            text = path.read_text()
            assert "CardBuilder(" not in text, (
                f"{path} constructs Feishu cards directly; use "
                "FeishuToolCardRenderer"
            )


def test_sync_core_does_not_read_global_settings() -> None:
    root = Path("shared/capabilities/sync/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit sync config"
            )


def test_analysis_core_does_not_read_global_settings() -> None:
    root = Path("shared/capabilities/analysis/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit analysis config"
            )


def test_qa_core_does_not_read_global_settings() -> None:
    root = Path("agents/qa_agent/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit QA config"
            )


def test_dev_core_does_not_read_global_settings() -> None:
    root = Path("agents/dev_agent/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit dev config"
            )


def test_pjm_core_does_not_read_global_settings() -> None:
    root = Path("agents/pjm_agent/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit PJM config"
            )


def test_pjm_app_mounted_routes_do_not_duplicate_http_contracts() -> None:
    """Mounted PJM routers must not duplicate the same HTTP method and path."""
    app_path = Path("agents/pjm_agent/app/main.py")
    app_tree = ast.parse(app_path.read_text())
    router_imports: dict[str, Path] = {}

    for node in ast.walk(app_tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != 2 or not node.module or not node.module.startswith("api."):
            continue
        module_path = Path("agents/pjm_agent") / f"{node.module.replace('.', '/')}.py"
        for alias in node.names:
            if alias.name == "router":
                router_imports[alias.asname or alias.name] = module_path

    mounted_router_aliases: set[str] = set()
    for node in ast.walk(app_tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "create_agent_app"):
            continue
        for keyword in node.keywords:
            if keyword.arg != "routers" or not isinstance(keyword.value, ast.List):
                continue
            for item in keyword.value.elts:
                if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Name):
                    mounted_router_aliases.add(item.elts[0].id)

    routes: list[tuple[str, str]] = []
    for alias in mounted_router_aliases:
        router_path = router_imports[alias]
        tree = ast.parse(router_path.read_text())
        prefix = ""
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "router" for target in node.targets):
                continue
            call = node.value
            if not isinstance(call, ast.Call):
                continue
            for keyword in call.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    prefix = str(keyword.value.value)

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue
                if not (
                    isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "router"
                ):
                    continue
                if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                    continue
                routes.append((decorator.func.attr.upper(), prefix + str(decorator.args[0].value)))

    duplicates = [
        (method, path)
        for (method, path), count in Counter(routes).items()
        if count > 1
    ]
    assert duplicates == []


def test_agent_core_does_not_import_platform_adapters_directly() -> None:
    for agent_root in AGENT_ROOTS:
        root = Path("agents") / agent_root / "core"
        if not root.exists():
            continue
        for path in _python_files(root):
            for module in _imported_modules(path):
                assert not module.startswith("shared.integrations"), (
                    f"{path} imports platform adapter module {module}; "
                    "inject a port or agent-local adapter"
                )


def test_agent_service_does_not_import_agent_local_integrations_directly() -> None:
    for agent_root in AGENT_ROOTS:
        root = Path("agents") / agent_root / "service"
        if not root.exists():
            continue
        for path in _python_files(root):
            for module in _imported_modules(path):
                assert not module.startswith(f"agents.{agent_root}.integrations"), (
                    f"{path} imports agent-local integration module {module}; "
                    "inject an agent-local adapter or port"
                )


def test_gateway_core_does_not_import_platform_adapters_directly() -> None:
    gateway_roots = [Path("services/gateways")]
    for gateway_root in gateway_roots:
        if not gateway_root.exists():
            continue
        for core_root in gateway_root.glob("*/core"):
            for path in _python_files(core_root):
                for module in _imported_modules(path):
                    assert not module.startswith("shared.integrations"), (
                        f"{path} imports platform adapter module {module}; "
                        "inject a port or gateway-local adapter"
                    )


def test_user_interaction_chat_and_daily_tasks_do_not_read_global_settings() -> None:
    paths = [
        Path("services/gateways/user_interaction/core/chat_service.py"),
        Path("services/gateways/user_interaction/core/daily_tasks.py"),
        Path("services/gateways/user_interaction/core/tools.py"),
    ]
    for path in paths:
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit gateway config"
            )


def test_frontend_routes_are_thin() -> None:
    route_root = Path("frontend/src/app/[locale]/(app)")
    forbidden = [
        "useState",
        "useMemo",
        "useCallback",
        "MOCK_",
        "@/lib/hooks",
    ]
    for path in route_root.rglob("page.tsx"):
        source = path.read_text()
        line_count = len(source.splitlines())
        assert line_count <= 20, f"{path} has {line_count} lines"
        for token in forbidden:
            assert token not in source, f"{path} contains {token}"


def test_frontend_domain_hooks_are_imported_from_entities() -> None:
    frontend_root = Path("frontend/src")
    for path in frontend_root.rglob("*.ts*"):
        if path.parts[-3:-1] == ("lib", "hooks"):
            continue
        if "__tests__" in path.parts:
            continue
        source = path.read_text()
        assert "@/lib/hooks" not in source, f"{path} imports legacy hooks"


def test_frontend_fsd_dependency_direction() -> None:
    forbidden_by_root = {
        Path("frontend/src/entities"): ("@/features", "@/widgets"),
        Path("frontend/src/features"): ("@/widgets",),
    }
    for root, forbidden_imports in forbidden_by_root.items():
        if not root.exists():
            continue
        for path in root.rglob("*.ts*"):
            if "__tests__" in path.parts:
                continue
            source = path.read_text()
            for import_path in forbidden_imports:
                assert import_path not in source, (
                    f"{path} violates FSD dependency direction with {import_path}"
                )


def test_frontend_route_pages_compose_widgets_only() -> None:
    route_root = Path("frontend/src/app/[locale]/(app)")
    allowed_internal_imports = ("@/widgets",)
    for path in route_root.rglob("page.tsx"):
        source = path.read_text()
        for line in source.splitlines():
            if not line.startswith("import ") or '"@/' not in line:
                continue
            assert any(token in line for token in allowed_internal_imports), (
                f"{path} route page imports non-widget dependency: {line}"
            )


def test_event_catalog_uses_canonical_runtime_event_names() -> None:
    catalog = Path("docs/guides/event-catalog.md").read_text()
    expected = {
        EventTypes.PM_DECOMPOSITION_FAILED,
        EventTypes.PM_APPROVAL_TIMEOUT,
        EventTypes.PM_PRD_READY,
        EventTypes.PM_TASKS_READY_FOR_DEV,
        EventTypes.QA_RUN_REQUESTED,
        EventTypes.QA_ACCEPTANCE_COMPLETED,
        EventTypes.QA_GATE_FAILED,
        EventTypes.COORDINATOR_COMMAND,
        EventTypes.COORDINATOR_RESPONSE,
        EventTypes.COORDINATOR_DISPATCH,
        EventTypes.TASK_NOTIFICATION,
        EventTypes.TASK_PROGRESS,
        EventTypes.A2A_TASK_SUBMITTED,
        EventTypes.A2A_TASK_WORKING,
        EventTypes.A2A_TASK_INPUT_REQUIRED,
        EventTypes.A2A_TASK_COMPLETED,
        EventTypes.A2A_TASK_FAILED,
        EventTypes.A2A_TASK_CANCELED,
        EventTypes.A2A_TASK_ERROR,
        "channel.message.outbound",
        "channel.message.delivered",
    }
    stale = {
        "pm.decomposition_failed",
        "pm.approval_timeout",
        "qa.acceptance_completed",
        "qa.acceptance_failed",
    }

    for event_type in expected:
        assert event_type in catalog
    for event_type in stale:
        assert event_type not in catalog


def test_event_catalog_documents_channel_gateway_event_names() -> None:
    catalog = Path("docs/guides/event-catalog.md").read_text()
    channel_event_types = {
        value
        for name, value in vars(ChannelEventTypes).items()
        if name.isupper() and isinstance(value, str)
    }

    for event_type in channel_event_types:
        assert event_type in catalog


def test_api_reference_documents_current_qa_stats_endpoint() -> None:
    api_reference = Path("docs/guides/api-reference.md").read_text()

    assert "/api/v1/qa/stats" in api_reference
    assert "/api/v1/qa/status" not in api_reference


def test_api_reference_does_not_duplicate_pjm_decomposition_routes() -> None:
    api_reference = Path("docs/guides/api-reference.md").read_text()
    pjm_decomposition_rows = [
        line
        for line in api_reference.splitlines()
        if "| `/api/v1/pm/decompose/{wp_id}" in line
    ]
    method_paths = [
        tuple(cell.strip(" `") for cell in line.split("|")[1:3])
        for line in pjm_decomposition_rows
    ]

    assert len(method_paths) == len(set(method_paths))
    assert "Alternate decomposition router path" not in api_reference
