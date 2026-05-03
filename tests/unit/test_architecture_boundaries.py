"""Repository architecture boundary checks."""
from __future__ import annotations

import ast
from pathlib import Path

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


def test_sync_core_does_not_read_global_settings() -> None:
    root = Path("shared/capabilities/sync/core")
    for path in _python_files(root):
        for module in _imported_modules(path):
            assert module != "shared.config", (
                f"{path} imports global settings; inject explicit sync config"
            )


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
