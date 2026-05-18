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


def _function_source(source: str, function_name: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            if node.name == function_name:
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"function not found: {function_name}")


def _direct_http_exception_raises(path: Path) -> list[int]:
    tree = ast.parse(path.read_text())
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        call = node.exc
        if not isinstance(call, ast.Call):
            continue
        if isinstance(call.func, ast.Name) and call.func.id == "HTTPException":
            lines.append(node.lineno)
    return lines


def _assert_documented_outbox_delivery_gap(doc_source: str) -> None:
    required_fragments = (
        "Requirement events",
        "PJM decomposition API events",
        "QA acceptance events",
        "Sync lifecycle/decomposition handoff events",
        "user-interaction sync trigger commands",
        "PJM service notifications",
        "Dev result-collection callback events",
        "channel gateway events",
        "analysis report/risk/quality events",
        "coordinator dispatch/handoff events",
        "evolution proposal events",
        "durable outboxes and runtime dispatchers",
    )
    for fragment in required_fragments:
        assert fragment in doc_source


def test_runtime_result_events_prefer_agent_outbox_hook() -> None:
    runtime_source = Path("shared/app/runtime.py").read_text()
    assert "publish_event_via_outbox" in runtime_source
    assert "await self._publish_result_event(bus, out_event)" in runtime_source

    outbox_runtime_paths = (
        Path("agents/requirement_manager/service/agent.py"),
        Path("agents/pjm_agent/service/agent.py"),
        Path("agents/dev_agent/service/agent.py"),
        Path("agents/qa_agent/service/agent.py"),
        Path("shared/capabilities/sync/service/agent.py"),
        Path("shared/capabilities/analysis/service/agent.py"),
        Path("shared/capabilities/evolution/service/agent.py"),
        Path("services/gateways/user_interaction/service/agent.py"),
        Path("services/gateways/channel/service/agent.py"),
        Path("services/orchestration/coordinator/service/agent.py"),
    )
    for path in outbox_runtime_paths:
        assert "async def publish_event_via_outbox" in path.read_text(), (
            f"{path} must expose the runtime outbox publish hook"
        )


def test_backend_http_errors_go_through_shared_api_contract() -> None:
    """Runtime code should not bypass shared API error-code helpers."""
    allowed_paths = {Path("shared/api/errors.py")}
    roots = [Path("agents"), Path("services"), Path("shared")]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path in allowed_paths:
                continue
            for line_no in _direct_http_exception_raises(path):
                offenders.append(f"{path}:{line_no}")

    assert offenders == []


def test_unknown_action_errors_use_shared_request_result_contract() -> None:
    """Agent request handlers should not return unversioned unknown-action errors."""
    allowed_paths = {Path("shared/app/request_result.py")}
    roots = [Path("agents"), Path("services"), Path("shared")]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path in allowed_paths:
                continue
            source = path.read_text()
            if '{"error": "unknown action"' in source:
                offenders.append(str(path))

    assert offenders == []


def test_agent_request_entrypoints_do_not_return_bare_error_dicts() -> None:
    """Public agent request entrypoints should include stable error codes."""
    entrypoint_paths = (
        Path("agents/dev_agent/service/agent.py"),
        Path("agents/pjm_agent/service/agent.py"),
        Path("agents/qa_agent/service/agent.py"),
        Path("shared/capabilities/analysis/service/agent.py"),
        Path("shared/capabilities/sync/service/agent.py"),
        Path("services/gateways/user_interaction/service/agent.py"),
        Path("services/orchestration/coordinator/service/agent.py"),
    )
    offenders = [
        str(path)
        for path in entrypoint_paths
        if 'return {"error":' in path.read_text()
    ]

    assert offenders == []


def test_request_result_contract_lives_in_shared_core() -> None:
    """Runtime code should depend on core request-result helpers, not app re-exports."""
    core_source = Path("shared/core/request_result.py").read_text()
    app_source = Path("shared/app/request_result.py").read_text()

    assert "def request_error(" in core_source
    assert "def unknown_action_error(" in core_source
    assert "from shared.core.request_result import" in app_source

    forbidden_imports = (
        "from shared.app import request_error",
        "from shared.app import unknown_action_error",
        "from shared.app import UNKNOWN_ACTION_ERROR_CODE",
    )
    roots = [Path("agents"), Path("services"), Path("shared")]
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path == Path("shared/app/request_result.py"):
                continue
            source = path.read_text()
            for forbidden in forbidden_imports:
                if forbidden in source:
                    offenders.append(f"{path}: {forbidden}")

    assert offenders == []


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


def test_app_entrypoints_use_runtime_public_started_property() -> None:
    roots = [
        Path("agents"),
        Path("services"),
        Path("shared/capabilities"),
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("app/main.py"):
            source = path.read_text()
            assert "runtime._started" not in source, (
                f"{path} reads AgentRuntime private startup state; use runtime.is_started"
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


def test_event_publisher_port_lives_in_shared_core() -> None:
    """Core/application code should depend on the shared event publisher port."""
    core_source = Path("shared/core/event_publisher.py").read_text()
    infra_source = Path("shared/infra/event_publisher.py").read_text()

    assert "class EventPublisher(Protocol)" in core_source
    assert "from shared.core.event_publisher import EventPublisher" in infra_source
    assert "class EventPublisher(Protocol)" not in infra_source

    source_paths = (
        Path("agents/qa_agent/core/notifier.py"),
        Path("agents/pjm_agent/core/decomposition_orchestrator.py"),
        Path("shared/capabilities/sync/core/openproject_sync.py"),
        Path("shared/capabilities/sync/core/engine.py"),
        Path("shared/protocols/bridge/event_bridge.py"),
        Path("shared/infra/budget_events.py"),
    )
    for path in source_paths:
        source = path.read_text()
        assert "from shared.infra.event_publisher import EventPublisher" not in source
        assert "EventPublisher" in source

    assert "class QAEventPublisherPort" not in source_paths[0].read_text()
    assert "class PJMEventPublisherPort" not in source_paths[1].read_text()
    assert "class SyncEventPublisherPort" not in source_paths[2].read_text()


def test_dev_agent_repository_uses_core_lifecycle_policy() -> None:
    """Dev persistence must not own or import DTO-level lifecycle rules."""
    repository_path = Path("agents/dev_agent/db/repository.py")
    assert "core.task_lifecycle" in _imported_modules(repository_path)

    for path in _python_files(Path("agents/dev_agent/db")):
        for module in _imported_modules(path):
            assert module not in {
                "models.schemas",
                "agents.dev_agent.models.schemas",
            }, (
                f"{path} imports {module}; task lifecycle rules belong in "
                "agents.dev_agent.core.task_lifecycle"
            )


def test_dev_agent_core_uses_repository_ports() -> None:
    """Dev core use cases must depend on repository ports, not DB adapters."""
    port_path = Path("agents/dev_agent/core/repositories.py")
    result_collector_path = Path("agents/dev_agent/core/result_collector.py")
    service_source = Path("agents/dev_agent/service/agent.py").read_text()
    adapter_source = Path("agents/dev_agent/db/task_store.py").read_text()

    assert port_path.exists()
    port_source = port_path.read_text()
    assert "class DevTaskRepositoryPort(Protocol)" in port_source
    assert "create_task" in port_source
    assert "get_by_mr_iid" in port_source
    assert "class DevWorkflowLogRepositoryPort(Protocol)" in port_source
    assert "class SqlAlchemyDevTaskStore" in adapter_source
    assert "DevTaskRepository" in adapter_source
    assert "from ..db.repository import DevTaskRepository" not in service_source
    assert "DevTaskRepository(" not in service_source
    assert "SqlAlchemyDevTaskStore(session)" in service_source
    assert "repositories" in _imported_modules(result_collector_path)

    app_source = Path("agents/dev_agent/app/main.py").read_text()
    assert "from ..db.repository import" not in app_source
    assert "DevTaskRepository(session)" not in app_source
    assert "DevWorkflowLogRepository(session)" not in app_source
    assert "SqlAlchemyDevTaskStore(session)" in app_source
    assert "SqlAlchemyDevWorkflowLogStore(session)" in app_source

    for path in _python_files(Path("agents/dev_agent/core")):
        for module in _imported_modules(path):
            assert not module.startswith("agents.dev_agent.db"), (
                f"{path} imports {module}; core use cases should depend on "
                "agents.dev_agent.core.repository ports"
            )
            assert module != "agents.dev_agent.db.repository", (
                f"{path} imports concrete repository {module}; use core ports"
            )


def test_sync_mapping_api_delegates_to_query_use_case() -> None:
    """Sync HTTP routes should not own mapping repository queries."""
    api_source = Path("shared/capabilities/sync/api/sync.py").read_text()
    dependency_source = Path("shared/capabilities/sync/api/dependencies.py").read_text()
    query_source = Path("shared/capabilities/sync/core/mapping_queries.py").read_text()

    assert "get_sync_mapping_query_service" in api_source
    assert "SyncMappingQueryService" in api_source
    assert "SyncMappingRepository" not in api_source
    assert "from ..db.repository import" not in api_source
    assert "SyncMappingRepository" in dependency_source
    assert "class SyncMappingQueryService" in query_source


def test_sync_feishu_bitable_engine_uses_persistence_ports() -> None:
    """Sync core engines should route persistence through explicit ports."""
    feishu_source = Path(
        "shared/capabilities/sync/core/feishu_bitable_sync.py"
    ).read_text()
    openproject_source = Path(
        "shared/capabilities/sync/core/openproject_sync.py"
    ).read_text()
    engine_source = Path("shared/capabilities/sync/core/engine.py").read_text()
    locking_source = Path("shared/capabilities/sync/core/locking.py").read_text()
    ports_source = Path("shared/capabilities/sync/core/sync_ports.py").read_text()
    adapter_source = Path("shared/capabilities/sync/db/sync_stores.py").read_text()
    service_source = Path("shared/capabilities/sync/service/agent.py").read_text()

    assert "from ..db.database import" not in feishu_source
    assert "from ..db.repository import" not in feishu_source
    assert "from ..db.database import" not in openproject_source
    assert "from ..db.repository import" not in openproject_source
    assert "from ..db.database import" not in engine_source
    assert "from ..db.repository import" not in engine_source
    assert "from ..db.database import" not in locking_source
    assert "from ..db.repository import SyncLockRepository" not in locking_source
    assert "class FeishuBitableSyncStore" in ports_source
    assert "class OpenProjectSyncStore" in ports_source
    assert "class SyncLockStore" in ports_source
    assert "SqlAlchemyFeishuBitableSyncStore" in adapter_source
    assert "SqlAlchemyOpenProjectSyncStore" in adapter_source
    assert "SqlAlchemySyncLockStore" in adapter_source
    assert "feishu_bitable_store=SqlAlchemyFeishuBitableSyncStore" in service_source
    assert "openproject_store=SqlAlchemyOpenProjectSyncStore" in service_source
    assert "lock_store=SqlAlchemySyncLockStore" in service_source


def test_user_interaction_daily_progress_api_delegates_to_query_use_case() -> None:
    """Daily-progress HTTP route should not own repository query logic."""
    api_source = Path("services/gateways/user_interaction/api/daily_progress.py").read_text()
    dependency_source = Path(
        "services/gateways/user_interaction/api/dependencies.py"
    ).read_text()
    query_source = Path(
        "services/gateways/user_interaction/core/daily_progress_queries.py"
    ).read_text()

    assert "get_daily_progress_query_service" in api_source
    assert "DailyProgressQueryService" in api_source
    assert "DailyProgressRepository" not in api_source
    assert "db_manager" not in api_source
    assert "from ..db.repository import" not in api_source
    assert "results = []" not in api_source
    assert "for e in entries" not in api_source
    assert "list_progress_response" in api_source
    assert "DailyProgressRepository" not in dependency_source
    assert "AsyncSession" not in dependency_source
    assert "get_db" not in dependency_source
    assert "SqlAlchemyDailyProgressQueryStore" in dependency_source
    assert "class DailyProgressQueryService" in query_source
    assert "def to_response_dict" in query_source
    assert "async def list_progress_response" in query_source


def test_user_interaction_webhook_delegates_intake_to_core_use_case() -> None:
    """Feishu webhook API should not own message parsing or cache contracts."""
    api_source = Path("services/gateways/user_interaction/api/webhook.py").read_text()
    core_source = Path(
        "services/gateways/user_interaction/core/webhook_intake.py"
    ).read_text()

    assert "class FeishuWebhookIntakeUseCase" in core_source
    assert "class WebhookCachePort(Protocol)" in core_source
    assert "class FeishuUserDirectoryPort(Protocol)" in core_source
    assert "def extract_message_event" in core_source
    assert "def extract_text" in core_source
    assert "async def resolve_user_name" in core_source
    assert "user_info_cache_key" in core_source
    assert "chat:dedup:" in core_source

    assert "FeishuWebhookIntakeUseCase" in api_source
    assert "_webhook_intake.extract_message_event(body)" in api_source
    assert "_webhook_intake.extract_text(incoming)" in api_source
    assert "_webhook_intake.resolve_user_name(" in api_source
    assert "import hashlib" not in api_source
    assert 'message.get("message_type"' not in api_source
    assert "sender_id" not in api_source
    assert "chat:user_info:" not in api_source
    assert "chat:dedup:" not in api_source
    assert 'json.loads(message.get("content", "{}"))' not in api_source


def test_user_interaction_webhook_process_message_delegates_to_core_use_case() -> None:
    """Feishu webhook API should not own agent calls or Feishu reply delivery."""
    api_source = Path("services/gateways/user_interaction/api/webhook.py").read_text()
    core_source = Path(
        "services/gateways/user_interaction/core/webhook_processing.py"
    ).read_text()
    process_source = _function_source(api_source, "_process_message")

    assert "class WebhookMessageProcessingUseCase" in core_source
    assert "class WebhookAgentPort(Protocol)" in core_source
    assert "class WebhookMessengerPort(Protocol)" in core_source
    assert "class WebhookProcessCommand" in core_source
    assert "async def process_message" in core_source
    assert "agent.handle_request(" in core_source
    assert "messenger.add_reaction" in core_source
    assert "messenger.send_message" in core_source
    assert "messenger.reply_message" in core_source

    assert "WebhookMessageProcessingUseCase" in api_source
    assert "_webhook_processing.process_message(" in process_source
    assert "WebhookProcessCommand(" in process_source
    assert "agent.handle_request(" not in process_source
    assert "client.add_reaction" not in process_source
    assert "client.send_message" not in process_source
    assert "client.reply_message" not in process_source
    assert "json.dumps(card" not in process_source
    assert "抱歉，处理消息时出现问题" not in process_source


def test_user_interaction_bitable_api_delegates_confirm_create_reject_to_core_use_case() -> None:
    """Bitable HTTP routes should not own confirmed write/reject orchestration."""
    api_source = Path("services/gateways/user_interaction/api/bitable.py").read_text()
    core_source = Path(
        "services/gateways/user_interaction/core/bitable_operations.py"
    ).read_text()

    assert "class BitableOperationUseCase" in core_source
    assert "class BitableConfirmCommand" in core_source
    assert "class BitableCreateCommand" in core_source
    assert "class BitableRejectCommand" in core_source
    assert "class BitableDenialTrackerPort(Protocol)" in core_source
    assert "class BitableOperationLogCommand" in core_source
    assert "def sanitize_fields" in core_source
    assert "async def resolve_duplex_links" in core_source
    assert "async def confirm_update" in core_source
    assert "async def create_record" in core_source
    assert "async def reject_operation" in core_source
    assert "bitable.update_record" in core_source
    assert "bitable.create_record" in core_source
    assert "record_denial" in core_source
    assert "build_bitable_rejection" in core_source

    assert "BitableOperationUseCase" in api_source
    assert "_bitable_operation_use_case.confirm_update(" in api_source
    assert "_bitable_operation_use_case.create_record(" in api_source
    assert "_bitable_operation_use_case.reject_operation(" in api_source
    assert "bitable_service.update_record" not in api_source
    assert "bitable_service.create_record" not in api_source
    assert "def _sanitize_fields" not in api_source
    assert "async def _resolve_duplex_links" not in api_source
    assert "_format_fields_display" not in api_source
    assert "pending.get(" not in api_source
    assert 'action = f"reject_' not in api_source
    assert "await tracker.record_denial" not in api_source
    assert "build_bitable_rejection" not in api_source


def test_requirement_admin_llm_usage_api_delegates_to_query_use_case() -> None:
    """Requirement admin HTTP route should not own LLM usage repository queries."""
    api_source = Path("agents/requirement_manager/api/admin.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    query_source = Path("agents/requirement_manager/core/llm_usage_queries.py").read_text()

    assert "get_llm_usage_query_service" in api_source
    assert "LLMUsageQueryService" in api_source
    assert "LLMUsageRepository" not in api_source
    assert "from ..db.repository import" not in api_source
    assert "LLMUsageRepository" in dependency_source
    assert "class LLMUsageQueryService" in query_source


def test_requirement_admin_circuit_breaker_delegates_to_use_case() -> None:
    """Requirement admin HTTP routes should not own LLM gateway operations."""
    api_source = Path("agents/requirement_manager/api/admin.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/admin_circuit_breaker.py"
    ).read_text()

    for function_name in ("get_circuit_breaker_status", "reset_circuit_breaker"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_circuit_breaker_admin_use_case" in function_source
        assert "CircuitBreakerAdminUseCase" in function_source
        assert "llm_gateway" not in function_source
        assert "get_circuit_breaker_stats" not in function_source
        assert "llm_gateway.reset_circuit_breaker" not in function_source

    assert "from shared.infra.llm_gateway import llm_gateway" not in api_source
    assert "get_circuit_breaker_admin_use_case" in dependency_source
    assert "CircuitBreakerAdminUseCase(gateway=llm_gateway)" in dependency_source
    assert "class CircuitBreakerAdminUseCase" in use_case_source


def test_requirement_messages_api_delegates_to_query_use_case() -> None:
    """Requirement messages HTTP route should not own message repository queries."""
    api_source = Path("agents/requirement_manager/api/messages.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    query_source = Path("agents/requirement_manager/core/message_queries.py").read_text()

    assert "get_message_query_service" in api_source
    assert "MessageQueryService" in api_source
    assert "MessageRepository" not in api_source
    assert "from agents.requirement_manager.db.repository" not in api_source
    assert "MessageRepository" in dependency_source
    assert "class MessageQueryService" in query_source


def test_requirement_context_api_delegates_to_query_use_case() -> None:
    """Requirement context HTTP route should not own repository query logic."""
    api_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    query_source = Path(
        "agents/requirement_manager/core/requirement_context_queries.py"
    ).read_text()
    context_source = api_source[
        api_source.index("async def get_requirement_context") :
        api_source.index("def _message_to_dict")
    ]

    assert "get_requirement_context_query_service" in context_source
    assert "RequirementContextQueryService" in context_source
    assert "RequirementRepository" not in context_source
    assert "MessageRepository" not in context_source
    assert "Depends(get_db)" not in context_source
    assert "RequirementRepository" in dependency_source
    assert "MessageRepository" in dependency_source
    assert "class RequirementContextQueryService" in query_source


def test_requirement_query_routes_delegate_to_query_use_case() -> None:
    """Requirement read-only HTTP routes should not own repository query logic."""
    api_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    query_source = Path("agents/requirement_manager/core/requirement_queries.py").read_text()

    function_names = (
        "list_requirements",
        "get_requirement",
        "search_requirements",
        "find_similar_requirements",
        "list_meetings",
        "get_stats",
        "get_enhanced_stats",
        "get_requirement_history",
        "get_requirement_diff",
    )
    for function_name in function_names:
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_requirement_query_service" in function_source
        assert "RequirementQueryService" in function_source
        assert "Repository(" not in function_source
        assert "Depends(get_db)" not in function_source
        assert "vector_store." not in function_source

    assert "get_requirement_query_service" in dependency_source
    assert "RequirementRepository" in dependency_source
    assert "MeetingRepository" in dependency_source
    assert "vector_store" in dependency_source
    assert "class RequirementQueryService" in query_source


def test_requirement_export_api_delegates_to_use_case() -> None:
    """Export HTTP routes should not own repository query or document assembly."""
    api_source = Path("agents/requirement_manager/api/export.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/export_use_cases.py"
    ).read_text()
    generator_source = Path("agents/requirement_manager/core/generator.py").read_text()

    assert "get_export_use_case" in api_source
    assert "ExportUseCase" in api_source
    assert "RequirementRepository" not in api_source
    assert "QuestionRepository" not in api_source
    assert "generator.generate" not in api_source
    assert "Depends(get_db)" not in api_source
    assert "RequirementRepository" in dependency_source
    assert "QuestionRepository" in dependency_source
    assert "DocumentGenerator(" in dependency_source
    assert "system_prompt_resolver=resolve_agent_system_prompt" in dependency_source
    assert "from shared.infra.llm_gateway import llm_gateway" not in generator_source
    assert "resolve_agent_system_prompt" not in generator_source
    assert "class DocumentGenerationLLM" in generator_source
    assert "class ExportUseCase" in use_case_source


def test_requirement_analysis_routes_delegate_to_use_case() -> None:
    """Requirement analysis HTTP routes should not own repository or analyzer logic."""
    api_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/requirement_analysis.py"
    ).read_text()
    analyzer_source = Path("agents/requirement_manager/core/analyzer.py").read_text()

    for function_name in ("analyze_requirement", "analyze_text"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_requirement_analysis_use_case" in function_source
        assert "RequirementAnalysisUseCase" in function_source
        assert "RequirementRepository(" not in function_source
        assert "analyzer.analyze" not in function_source
        assert "Depends(get_db)" not in function_source

    assert "get_requirement_analysis_use_case" in dependency_source
    assert "RequirementRepository" in dependency_source
    assert "RequirementAnalyzer(" in dependency_source
    assert "system_prompt_resolver=resolve_agent_system_prompt" in dependency_source
    assert "from shared.infra.llm_gateway import llm_gateway" not in analyzer_source
    assert "resolve_agent_system_prompt" not in analyzer_source
    assert "analyzer = RequirementAnalyzer" not in analyzer_source
    assert "class RequirementAnalysisLLM" in analyzer_source
    assert "class RequirementAnalysisUseCase" in use_case_source


def test_requirement_conflict_route_delegates_to_use_case() -> None:
    """Conflict-check route should not own comparator or vector-search wiring."""
    api_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    comparator_source = Path("agents/requirement_manager/core/comparator.py").read_text()
    use_case_source = Path("agents/requirement_manager/core/conflict_check.py").read_text()

    start = api_source.index("async def check_conflict")
    end = api_source.find("\n\n@router.", start)
    if end == -1:
        end = len(api_source)
    function_source = api_source[start:end]
    assert "get_requirement_conflict_check_use_case" in function_source
    assert "RequirementConflictCheckUseCase" in function_source
    assert "comparator.compare" not in function_source
    assert "vector_store" not in function_source
    assert "hash_identifier" not in function_source

    assert "get_requirement_conflict_check_use_case" in dependency_source
    assert "RequirementComparator(" in dependency_source
    assert "vector_search=vector_store" in dependency_source
    assert "llm=llm_gateway" in dependency_source
    assert "system_prompt_resolver=resolve_agent_system_prompt" in dependency_source
    assert "from ..db.vector_store import vector_store" in dependency_source
    assert "from ..db.vector_store import vector_store" not in comparator_source
    assert "from shared.infra.llm_gateway import llm_gateway" not in comparator_source
    assert "resolve_agent_system_prompt" not in comparator_source
    assert "_get_vector_store" not in comparator_source
    assert "class RequirementVectorSearch" in comparator_source
    assert "class RequirementConflictLLM" in comparator_source
    assert "class RequirementConflictCheckUseCase" in use_case_source


def test_requirement_extractor_uses_runtime_injected_llm() -> None:
    """Requirement extraction core should not own LLM gateway wiring."""
    extractor_source = Path("agents/requirement_manager/core/extractor.py").read_text()
    core_init_source = Path("agents/requirement_manager/core/__init__.py").read_text()
    agent_source = Path("agents/requirement_manager/service/agent.py").read_text()

    assert "from shared.infra.llm_gateway import llm_gateway" not in extractor_source
    assert "resolve_agent_system_prompt" not in extractor_source
    assert "extractor = RequirementExtractor" not in extractor_source
    assert "class RequirementExtractionLLM" in extractor_source
    assert "from .extractor import RequirementExtractor, extractor" not in core_init_source
    assert "requirement_extractor: Optional[RequirementExtractor]" in agent_source
    assert "RequirementExtractor(" in agent_source
    assert "system_prompt_resolver=resolve_agent_system_prompt" in agent_source
    assert "await self._extractor.extract(" in agent_source
    assert "await extractor.extract(" not in agent_source


def test_requirement_embedder_is_core_text_formatter_only() -> None:
    """Requirement core embedder must not own embedding infrastructure."""
    embedder_source = Path("agents/requirement_manager/core/embedder.py").read_text()
    core_init_source = Path("agents/requirement_manager/core/__init__.py").read_text()
    vector_source = Path("agents/requirement_manager/db/vector_store.py").read_text()

    assert "from shared.infra.embedder import" not in embedder_source
    assert "_shared_embedder" not in embedder_source
    assert "def embed_text(" not in embedder_source
    assert "def embed_batch(" not in embedder_source
    assert "embedder = RequirementEmbedder" not in embedder_source
    assert "from .embedder import RequirementEmbedder, embedder" not in core_init_source
    assert "requirement_embedder = RequirementEmbedder()" in vector_source
    assert "shared_embedder.embed" in vector_source


def test_requirement_ingest_api_delegates_to_use_case() -> None:
    """Ingest HTTP routes should not own dedupe or agent-ingest orchestration."""
    api_source = Path("agents/requirement_manager/api/ingest.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path("agents/requirement_manager/core/ingest_use_cases.py").read_text()

    assert "get_ingest_use_case" in api_source
    assert "IngestUseCase" in api_source
    assert "MeetingRepository" not in api_source
    assert "get_agent" not in api_source
    assert "datetime.fromisoformat" not in api_source
    assert "Depends(get_db)" not in api_source
    assert "MeetingRepository" in dependency_source
    assert "get_agent()" in dependency_source
    assert "class IngestUseCase" in use_case_source


def test_requirement_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """Requirement Manager direct agent requests should not own ingest branching."""
    service_source = Path("agents/requirement_manager/service/agent.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/request_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class RequirementRequestIngestAgent(Protocol)" in use_case_source
    assert "class RequirementManagerRequestUseCase" in use_case_source
    assert "async def _ingest" in use_case_source
    assert "datetime.fromisoformat" in use_case_source
    assert "meeting_date_must_be_iso_datetime" in use_case_source

    assert "RequirementManagerRequestUseCase" in service_source
    assert "def _request_use_case" in service_source
    assert "self._request_use_case().handle(request)" in handle_source
    assert 'if action == "ingest"' not in handle_source
    assert "datetime.fromisoformat" not in service_source
    assert "content_required" not in service_source


def test_requirement_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """Requirement Manager event handlers should live behind a core use case."""
    service_path = Path("agents/requirement_manager/service/agent.py")
    legacy_handler_path = Path("agents/requirement_manager/service/event_handlers.py")
    use_case_path = Path("agents/requirement_manager/core/event_use_cases.py")
    service_source = service_path.read_text()
    use_case_source = use_case_path.read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert not legacy_handler_path.exists()
    assert "SUBSCRIBED_EVENTS" in use_case_source
    assert "class RequirementEventIngestAgent(Protocol)" in use_case_source
    assert "class RequirementManagerEventUseCase" in use_case_source
    assert "EventTypes.MEETING_UPLOADED" in use_case_source
    assert "coordinator_dispatch_received" in use_case_source
    assert "hash_identifier(title)" in use_case_source
    assert "await self._agent.ingest_meeting(" in use_case_source

    assert "RequirementManagerEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert ".event_handlers" not in service_source
    assert "dispatch_event" not in service_source
    assert "agent._db_manager.session" not in use_case_source
    assert "async with agent._db_manager.session()" not in service_source


def test_requirement_feedback_api_delegates_to_use_case() -> None:
    """Feedback HTTP routes should not own agent calls or batch accounting."""
    api_source = Path("agents/requirement_manager/api/feedback.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/feedback_use_cases.py"
    ).read_text()

    assert "get_requirement_feedback_use_case" in api_source
    assert "RequirementFeedbackUseCase" in api_source
    assert "get_agent()" not in api_source
    assert "Depends(get_db)" not in api_source
    assert "sum(1 for" not in api_source
    assert "get_requirement_feedback_use_case" in dependency_source
    assert "get_agent()" in dependency_source
    assert "class RequirementFeedbackUseCase" in use_case_source


def test_requirement_mutation_routes_delegate_to_use_case() -> None:
    """Requirement mutation HTTP routes should delegate agent/session orchestration."""
    api_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    dependency_source = Path("agents/requirement_manager/api/dependencies.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/requirement_mutations.py"
    ).read_text()

    for function_name in ("update_requirement", "delete_requirement"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_requirement_mutation_use_case" in function_source
        assert "RequirementMutationUseCase" in function_source
        assert "get_agent()" not in function_source
        assert "Depends(get_db)" not in function_source

    assert "get_requirement_mutation_use_case" in dependency_source
    assert "get_agent()" in dependency_source
    assert "class RequirementMutationUseCase" in use_case_source


def test_webui_read_routes_delegate_to_query_use_case() -> None:
    """WebUI read compatibility routes should not own Control Plane query assembly."""
    api_source = Path("agents/requirement_manager/api/webui.py").read_text()
    query_source = Path("agents/requirement_manager/core/webui_queries.py").read_text()
    port_source = Path("agents/requirement_manager/core/webui_ports.py").read_text()
    adapter_source = Path(
        "agents/requirement_manager/db/webui_control_plane_store.py"
    ).read_text()

    for function_name in (
        "list_agent_runtime_statuses",
        "get_agent_runtime_status",
        "list_pending_approvals",
    ):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_webui_query_service" in function_source
        assert "WebUIQueryService" in function_source
        assert "ControlPlaneRepository" not in function_source
        assert "control_plane_db_manager.session" not in function_source

    assert "class WebUIQueryService" in query_source
    assert "WebUIControlPlaneQueryStore" in query_source
    assert "ControlPlaneRepository" not in query_source
    assert "control_plane_db_manager.session" not in query_source
    assert "class WebUIControlPlaneQueryStore(Protocol)" in port_source
    assert "SqlAlchemyWebUIControlPlaneStore" in adapter_source
    assert "ControlPlaneRepository" not in adapter_source
    assert "SqlAlchemyControlPlaneAgentRegistryStore" in adapter_source
    assert "SqlAlchemyControlPlaneAgentRunStore" in adapter_source
    assert "SqlAlchemyControlPlaneWorkItemStore" in adapter_source
    assert "SqlAlchemyControlPlaneApprovalStore" in adapter_source


def test_webui_prompt_config_routes_delegate_to_use_case() -> None:
    """WebUI prompt-config routes should not own Control Plane mutations."""
    api_source = Path("agents/requirement_manager/api/webui.py").read_text()
    use_case_source = Path(
        "agents/requirement_manager/core/webui_prompt_config.py"
    ).read_text()
    port_source = Path("agents/requirement_manager/core/webui_ports.py").read_text()
    adapter_source = Path(
        "agents/requirement_manager/db/webui_control_plane_store.py"
    ).read_text()

    for function_name in ("get_agent_prompt_config", "update_agent_prompt_config"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n@router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "get_webui_prompt_config_use_case" in function_source
        assert "WebUIPromptConfigUseCase" in function_source
        assert "ControlPlaneRepository" not in function_source
        assert "control_plane_db_manager.session" not in function_source
        assert "AuditEvent" not in function_source

    assert "class WebUIPromptConfigUseCase" in use_case_source
    assert "WebUIPromptConfigStore" in use_case_source
    assert "ControlPlaneRepository" not in use_case_source
    assert "AuditEvent" not in use_case_source
    assert "class WebUIPromptConfigStore(Protocol)" in port_source
    assert "ControlPlaneRepository" not in adapter_source
    assert "AuditEvent" not in adapter_source
    assert "SqlAlchemyControlPlanePromptConfigStore" in adapter_source
    assert "update_prompt_config_with_audit" in adapter_source


def test_requirement_repository_uses_core_lifecycle_policy() -> None:
    """Requirement persistence must not own lifecycle mutations."""
    repository_path = Path("agents/requirement_manager/db/repository.py")
    modules = _imported_modules(repository_path)
    source = repository_path.read_text()

    assert "core.requirement_lifecycle" in modules
    assert "RequirementStatus" not in source
    assert "vector_store" not in source
    assert ".add_history(" not in source


def test_requirement_skills_use_skill_store_port() -> None:
    """Business skills should not construct repositories or manage commits."""
    skill_paths = [
        Path("agents/requirement_manager/skills/confirm_requirement.py"),
        Path("agents/requirement_manager/skills/reject_requirement.py"),
        Path("agents/requirement_manager/skills/list_requirements.py"),
        Path("agents/requirement_manager/skills/batch_operations.py"),
        Path("agents/requirement_manager/skills/export.py"),
        Path("agents/requirement_manager/skills/stats.py"),
    ]
    port_source = Path("agents/requirement_manager/core/skill_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/skill_store.py").read_text()

    assert "class RequirementSkillStore(Protocol)" in port_source
    assert "SqlAlchemyRequirementSkillStore" in adapter_source
    assert "RequirementRepository" in adapter_source
    assert "MeetingRepository" in adapter_source

    for path in skill_paths:
        source = path.read_text()
        assert "RequirementRepository" not in source
        assert "MeetingRepository" not in source
        assert "context.db.commit" not in source
        assert "build_requirement_skill_store" in source


def test_requirement_routes_delegate_mutations_to_agent_boundary() -> None:
    """HTTP routes must not own requirement lifecycle or feedback learning."""
    source = Path("agents/requirement_manager/api/requirements.py").read_text()
    feedback_source = Path("agents/requirement_manager/api/feedback.py").read_text()

    assert ".add_history(" not in source
    assert "record_correction" not in source
    assert "FeedbackLearningService" not in source
    assert "session.commit" not in source
    assert "session.commit" not in feedback_source
    assert "QuestionRepository" not in feedback_source


def test_requirement_question_use_cases_use_persistence_port() -> None:
    """Question use cases should not directly construct SQLAlchemy repositories."""
    agent_source = Path("agents/requirement_manager/service/agent.py").read_text()
    port_source = Path("agents/requirement_manager/core/question_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/question_store.py").read_text()

    for function_name in ("answer_question", "list_open_questions"):
        function_source = _function_source(agent_source, function_name)
        assert "_get_question_store" in function_source
        assert "QuestionRepository(" not in function_source

    assert "class RequirementQuestionStore(Protocol)" in port_source
    assert "create_batch" in port_source
    assert "class SqlAlchemyRequirementQuestionStore" in adapter_source
    assert "QuestionRepository" in adapter_source
    assert "QuestionRepository" not in agent_source


def test_requirement_agent_uses_requirement_store_port() -> None:
    """Requirement application service should not construct the DB repository."""
    agent_source = Path("agents/requirement_manager/service/agent.py").read_text()
    port_source = Path("agents/requirement_manager/core/requirement_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/requirement_store.py").read_text()

    assert "class RequirementStore(Protocol)" in port_source
    assert "class SqlAlchemyRequirementStore" in adapter_source
    assert "RequirementRepository" in adapter_source
    assert "RequirementRepository" not in agent_source
    assert "_get_requirement_store" in agent_source


def test_requirement_agent_uses_meeting_and_message_store_ports() -> None:
    """Requirement agent should not construct meeting/message DB repositories."""
    agent_source = Path("agents/requirement_manager/service/agent.py").read_text()
    meeting_port_source = Path("agents/requirement_manager/core/meeting_ports.py").read_text()
    meeting_adapter_source = Path("agents/requirement_manager/db/meeting_store.py").read_text()
    message_port_source = Path("agents/requirement_manager/core/message_ports.py").read_text()
    message_adapter_source = Path("agents/requirement_manager/db/message_store.py").read_text()

    assert "class RequirementMeetingStore(Protocol)" in meeting_port_source
    assert "class SqlAlchemyRequirementMeetingStore" in meeting_adapter_source
    assert "MeetingRepository" in meeting_adapter_source
    assert "MeetingRepository" not in agent_source
    assert "_get_meeting_store" in agent_source

    assert "class RequirementMessageStore(Protocol)" in message_port_source
    assert "class SqlAlchemyRequirementMessageStore" in message_adapter_source
    assert "MessageRepository" in message_adapter_source
    assert "MessageRepository" not in agent_source
    assert "_get_message_store" in agent_source
    assert "from ..db.repository import" not in agent_source


def test_feishu_message_integration_uses_message_store_port() -> None:
    """Feishu integration should not directly construct chat-message repositories."""
    recorder_source = Path(
        "agents/requirement_manager/integrations/feishu/message_recorder.py"
    ).read_text()
    session_source = Path(
        "agents/requirement_manager/integrations/feishu/session_manager.py"
    ).read_text()
    port_source = Path("agents/requirement_manager/core/message_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/message_store.py").read_text()

    assert "async def create(" in port_source
    assert "get_by_feishu_message_id" in port_source
    assert "count_by_session" in port_source
    assert "MessageRepository" in adapter_source
    assert "MessageRepository" not in recorder_source
    assert "MessageRepository" not in session_source
    assert "SqlAlchemyRequirementMessageStore" in recorder_source
    assert "SqlAlchemyRequirementMessageStore" in session_source


def test_requirement_feedback_learning_uses_persistence_port() -> None:
    """Feedback-learning service should not directly construct repositories."""
    service_source = Path(
        "agents/requirement_manager/service/feedback_learning.py"
    ).read_text()
    port_source = Path("agents/requirement_manager/core/feedback_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/feedback_store.py").read_text()

    assert "class RequirementFeedbackStore(Protocol)" in port_source
    assert "class SqlAlchemyRequirementFeedbackStore" in adapter_source
    assert "FeedbackRepository" in adapter_source
    assert "FeedbackRepository" not in service_source
    assert "RequirementRepository" not in service_source
    assert "feedback_store" in service_source


def test_requirement_api_uses_shared_error_contract() -> None:
    """Requirement HTTP adapters use shared compatibility error codes."""
    requirements_source = Path("agents/requirement_manager/api/requirements.py").read_text()
    feedback_source = Path("agents/requirement_manager/api/feedback.py").read_text()
    messages_source = Path("agents/requirement_manager/api/messages.py").read_text()
    webui_source = Path("agents/requirement_manager/api/webui.py").read_text()

    assert "raise_requirement_not_found" in requirements_source
    assert "raise_requirement_not_found" in feedback_source
    assert "raise_question_not_found" in feedback_source
    assert "raise_session_not_found" in messages_source
    assert "raise_agent_not_found" in webui_source
    assert "HTTPException(status_code=404, detail=\"Requirement not found\")" not in (
        requirements_source + feedback_source + messages_source + webui_source
    )
    assert "HTTPException(status_code=404, detail=\"Session not found" not in messages_source
    assert "HTTPException(status_code=404, detail=\"agent_not_found\")" not in webui_source


def test_pjm_and_qa_api_use_shared_error_contracts() -> None:
    """QA and PJM HTTP adapters use shared compatibility error codes."""
    qa_source = Path("agents/qa_agent/api/qa.py").read_text()
    pm_source = Path("agents/pjm_agent/api/pm.py").read_text()
    decomposition_source = Path("agents/pjm_agent/api/decomposition.py").read_text()

    assert "raise_qa_run_not_found" in qa_source
    assert "raise_qa_run_timeout" in qa_source
    assert "raise_qa_run_failed" in qa_source
    assert "raise_qa_run_list_failed" in qa_source
    assert "raise_qa_run_detail_failed" in qa_source
    assert "raise_qa_stats_failed" in qa_source
    assert "raise_pm_decomposition_not_found" in pm_source
    assert "raise_pm_decomposition_unavailable" in pm_source
    assert "raise_pm_config_failed" in pm_source
    assert "raise_pm_config_refresh_failed" in pm_source
    assert "raise_pm_alerts_failed" in pm_source
    assert "raise_pm_decomposition_retry_failed" in pm_source
    assert "raise_pm_decomposition_forbidden" in pm_source
    assert "raise_pm_decomposition_not_found" in decomposition_source
    assert "raise_pm_decomposition_unavailable" in decomposition_source
    assert "raise_pm_decomposition_retry_failed" in decomposition_source
    assert "raise_pm_decomposition_forbidden" in decomposition_source

    assert (
        'HTTPException(status_code=404, detail="QA acceptance run not found")'
        not in qa_source
    )
    assert "from fastapi import APIRouter, HTTPException" not in qa_source
    assert "HTTPException(status_code=504" not in qa_source
    assert "HTTPException(status_code=500" not in qa_source
    assert 'HTTPException(status_code=404, detail="Record not found")' not in (
        pm_source + decomposition_source
    )
    assert "from fastapi import APIRouter, HTTPException" not in pm_source
    assert "from fastapi import APIRouter, HTTPException" not in decomposition_source
    assert "HTTPException(status_code=403" not in pm_source + decomposition_source
    assert "HTTPException(status_code=500" not in pm_source
    assert (
        'HTTPException(status_code=400, detail="Record not found or status is not pending")'
        not in pm_source
    )
    assert (
        'HTTPException(status_code=404, detail="Record not found or status is not pending")'
        not in decomposition_source
    )


def test_qa_api_delegates_to_application_use_case() -> None:
    """QA HTTP routes should not own acceptance request/result assembly."""
    api_source = Path("agents/qa_agent/api/qa.py").read_text()
    use_case_source = Path("agents/qa_agent/core/api_use_cases.py").read_text()

    assert "class QAApiAgentPort(Protocol)" in use_case_source
    assert "class QAApiUseCase" in use_case_source
    assert "QARunRequest(" in use_case_source
    assert "AcceptanceExecutionResult" in use_case_source
    assert "QARunListItem" not in api_source
    assert "QARunRequest(" not in api_source
    assert "status_map" not in api_source

    for function_name in (
        "trigger_run",
        "list_runs",
        "get_run_detail",
        "get_stats",
    ):
        function_source = _function_source(api_source, function_name)
        assert "get_agent()" not in function_source
        assert "agent.run_acceptance" not in function_source
        assert "agent.list_runs" not in function_source
        assert "agent.get_run" not in function_source
        assert "agent.get_stats" not in function_source
        assert "QAApiUseCase = Depends(get_qa_api_use_case)" in function_source


def test_qa_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """QA service shell should not own request action orchestration."""
    service_source = Path("agents/qa_agent/service/agent.py").read_text()
    use_case_source = Path("agents/qa_agent/core/request_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class QARequestUseCase" in use_case_source
    assert "class QARequestAgentPort(Protocol)" in use_case_source
    assert 'action == "run"' in use_case_source
    assert 'action == "list_runs"' in use_case_source
    assert 'action == "get_run"' in use_case_source
    assert 'action == "stats"' in use_case_source
    assert "QARunRequest(" in use_case_source
    assert "request_error(\"not found\", \"qa_run_not_found\")" in use_case_source
    assert "unknown_action_error()" in use_case_source

    assert "QARequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'action == "run"' not in handle_source
    assert 'action == "list_runs"' not in handle_source
    assert 'action == "get_run"' not in handle_source
    assert 'action == "stats"' not in handle_source
    assert "QARunRequest(" not in handle_source
    assert "request_error(\"not found\"" not in handle_source
    assert "unknown_action_error()" not in handle_source


def test_qa_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """QA service shell should not own event payload parsing."""
    service_source = Path("agents/qa_agent/service/agent.py").read_text()
    use_case_source = Path("agents/qa_agent/core/event_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class QAEventUseCase" in use_case_source
    assert "class QAEventRunnerPort(Protocol)" in use_case_source
    assert "EventTypes.CODE_COMMITTED" in use_case_source
    assert "EventTypes.QA_RUN_REQUESTED" in use_case_source
    assert "CodeCommittedPayload.model_validate(event.payload)" in use_case_source
    assert "QARunRequestedPayload.model_validate(event.payload)" in use_case_source
    assert "QARunRequest(" in use_case_source
    assert "coordinator_instruction_received" in use_case_source
    assert "trigger_event_id=event.event_id" in use_case_source

    assert "QAEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "if event.event_type == EventTypes.CODE_COMMITTED" not in handle_source
    assert "EventTypes.QA_RUN_REQUESTED" not in handle_source
    assert "CodeCommittedPayload" not in service_source
    assert "QARunRequestedPayload" not in service_source
    assert "_handle_code_committed" not in service_source
    assert "_handle_run_requested" not in service_source


def test_qa_agent_acceptance_execution_delegates_to_application_use_case() -> None:
    """QA service shell should not own acceptance execution orchestration."""
    service_source = Path("agents/qa_agent/service/agent.py").read_text()
    use_case_source = Path(
        "agents/qa_agent/core/acceptance_execution_use_cases.py"
    ).read_text()
    run_source = _function_source(service_source, "run_acceptance")

    assert "class QAAcceptanceExecutionUseCase" in use_case_source
    assert "class QAExecutionSessionManagerPort(Protocol)" in use_case_source
    assert "class QAAcceptanceRunnerPort(Protocol)" in use_case_source
    assert "class QANotifierPort(Protocol)" in use_case_source
    assert "async def run_acceptance" in use_case_source
    assert "await self._runner.run_json" in use_case_source
    assert "await store.save_execution_result" in use_case_source
    assert "build_acceptance_events(" in use_case_source
    assert "await self._stage_event(session, event)" in use_case_source
    assert "await self._notifier.notify_all" in use_case_source
    assert "self._run_store.get_by_trigger_event_id" in use_case_source
    assert "def derive_severity" in use_case_source
    assert "def result_from_run" in use_case_source

    assert "QAAcceptanceExecutionUseCase" in service_source
    assert "def _acceptance_execution_use_case" in service_source
    assert "return await self._acceptance_execution_use_case().run_acceptance" in (
        run_source
    )
    assert "AcceptanceSummary(" not in service_source
    assert "AcceptanceFinding(" not in service_source
    assert "await self._runner.run_json" not in service_source
    assert "store.save_execution_result" not in service_source
    assert "completed_payload = {" not in service_source
    assert "await self._notifier.notify_all" not in service_source
    assert "self._run_store.get_by_trigger_event_id" not in service_source


def test_pjm_api_delegates_to_application_use_case() -> None:
    """PJM HTTP routes should not own agent request/action orchestration."""
    api_source = Path("agents/pjm_agent/api/pm.py").read_text()
    use_case_source = Path("agents/pjm_agent/core/api_use_cases.py").read_text()

    assert "class PMApiAgentPort(Protocol)" in use_case_source
    assert "class PMApiUseCase" in use_case_source
    assert "PMDecompositionActionCommand" in use_case_source
    assert "agent.handle_request" not in api_source
    assert "agent.approve_decomposition" not in api_source
    assert "agent.reject_decomposition" not in api_source

    for function_name in (
        "get_config",
        "refresh_config",
        "get_alerts",
        "trigger_daily_report",
        "trigger_weekly_report",
        "retry_decomposition",
        "get_decomposition",
        "approve_decomposition",
        "reject_decomposition",
    ):
        function_source = _function_source(api_source, function_name)
        assert "get_agent()" not in function_source
        assert "agent.handle_request" not in function_source
        assert "agent.approve_decomposition" not in function_source
        assert "agent.reject_decomposition" not in function_source
        assert "PMApiUseCase = Depends(get_pm_api_use_case)" in function_source


def test_pjm_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """PJM service shell should not own request action orchestration."""
    service_source = Path("agents/pjm_agent/service/agent.py").read_text()
    use_case_source = Path("agents/pjm_agent/core/request_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class PJMRequestUseCase" in use_case_source
    assert "class PJMConfigPort(Protocol)" in use_case_source
    assert "class PJMAlertPort(Protocol)" in use_case_source
    assert "class PJMPushPort(Protocol)" in use_case_source
    assert "class PJMReportPort(Protocol)" in use_case_source
    assert "class PJMDecompositionRequestPort(Protocol)" in use_case_source
    assert 'action == "config"' in use_case_source
    assert 'action == "alerts"' in use_case_source
    assert 'action == "refresh_config"' in use_case_source
    assert 'action == "push_alerts"' in use_case_source
    assert 'action == "retry_decompose"' in use_case_source
    assert 'action == "get_decompose"' in use_case_source
    assert 'action == "daily_report"' in use_case_source
    assert 'action == "weekly_report"' in use_case_source
    assert 'action == "check_stale_approvals"' in use_case_source
    assert "unknown_action_error()" in use_case_source
    assert "request_error(\"report_failed\", \"report_failed\")" in use_case_source

    assert "PJMRequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'action == "config"' not in handle_source
    assert 'action == "alerts"' not in handle_source
    assert 'action == "retry_decompose"' not in handle_source
    assert 'action == "daily_report"' not in handle_source
    assert "unknown_action_error()" not in handle_source
    assert "request_error(\"report_failed\"" not in handle_source


def test_pjm_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """PJM service shell should not own event workflow branching."""
    service_source = Path("agents/pjm_agent/service/agent.py").read_text()
    use_case_source = Path("agents/pjm_agent/core/event_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class PJMEventUseCase" in use_case_source
    assert "class PJMEventConfigPort(Protocol)" in use_case_source
    assert "class PJMEventAlertPort(Protocol)" in use_case_source
    assert "class PJMEventPushPort(Protocol)" in use_case_source
    assert "class PJMDecompositionEventPort(Protocol)" in use_case_source
    assert "class PJMEventFactoryPort(Protocol)" in use_case_source
    assert "class PJMMetricsPort(Protocol)" in use_case_source
    assert "EventTypes.SYNC_COMPLETED" in use_case_source
    assert "EventTypes.ANALYSIS_RISK_DETECTED" in use_case_source
    assert "EventTypes.CHAT_PM_QUERY" in use_case_source
    assert "EventTypes.SYNC_TASK_NEEDS_DECOMPOSE" in use_case_source
    assert "EventTypes.COORDINATOR_DISPATCH" in use_case_source
    assert "pm_alert_check_failed" in use_case_source
    assert "pm_risks_push_failed" in use_case_source
    assert "chat_query_failed" in use_case_source
    assert "decomposition_failed_notify_failed" in use_case_source

    assert "PJMEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "if event.event_type == EventTypes.SYNC_COMPLETED" not in handle_source
    assert "if event.event_type == EventTypes.CHAT_PM_QUERY" not in handle_source
    assert "if event.event_type == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE" not in (
        handle_source
    )
    assert "_run_alerts" not in service_source
    assert "_handle_risks" not in service_source
    assert "_handle_chat_query" not in service_source
    assert "_handle_decompose" not in service_source


def test_pjm_decomposition_api_delegates_to_application_use_case() -> None:
    """PJM compatibility decomposition routes should reuse application use cases."""
    api_source = Path("agents/pjm_agent/api/decomposition.py").read_text()

    assert "PMApiUseCase" in api_source
    assert "PMDecompositionActionCommand" in api_source
    assert "agent.approve_decomposition" not in api_source
    assert "agent.reject_decomposition" not in api_source
    assert "agent._retry_decompose" not in api_source
    assert "agent._get_decompose" not in api_source

    for function_name in (
        "approve_decomposition",
        "reject_decomposition",
        "retry_decomposition",
        "get_decomposition",
    ):
        function_source = _function_source(api_source, function_name)
        assert "get_agent()" not in function_source
        assert "agent." not in function_source
        assert "PMApiUseCase = Depends(get_decomposition_api_use_case)" in (
            function_source
        )


def test_pjm_scheduler_delegates_to_application_use_case() -> None:
    """PJM scheduler should not own agent request/action orchestration."""
    app_source = Path("agents/pjm_agent/app/main.py").read_text()
    use_case_source = Path("agents/pjm_agent/core/scheduler_use_cases.py").read_text()

    assert "class PJMSchedulerAgentPort(Protocol)" in use_case_source
    assert "class PJMSchedulerUseCase" in use_case_source
    assert '{"action": "alerts"}' in use_case_source
    assert '{"action": action}' in use_case_source
    assert ".handle_request(" not in app_source
    assert "PJMSchedulerUseCase" in app_source

    hourly_source = _function_source(app_source, "_hourly_alerts")
    assert ".handle_request(" not in hourly_source
    assert "get_pjm_scheduler_use_case().run_hourly_alerts()" in hourly_source

    scheduled_source = _function_source(app_source, "_run_scheduled_action")
    assert ".handle_request(" not in scheduled_source
    assert "get_pjm_scheduler_use_case().run_scheduled_action(action)" in (
        scheduled_source
    )


def test_analysis_api_uses_shared_error_contracts() -> None:
    """Analysis HTTP adapters use shared compatibility error codes."""
    analysis_source = Path("shared/capabilities/analysis/api/analysis.py").read_text()

    assert "raise_analysis_daily_report_failed" in analysis_source
    assert "raise_analysis_weekly_report_failed" in analysis_source
    assert "raise_analysis_risk_check_failed" in analysis_source
    assert "from fastapi import APIRouter, HTTPException" not in analysis_source
    assert "HTTPException(status_code=500" not in analysis_source


def test_analysis_api_delegates_to_application_use_case() -> None:
    """Analysis HTTP routes should not own agent request/action orchestration."""
    api_source = Path("shared/capabilities/analysis/api/analysis.py").read_text()
    use_case_source = Path(
        "shared/capabilities/analysis/core/api_use_cases.py"
    ).read_text()

    assert "class AnalysisApiAgentPort(Protocol)" in use_case_source
    assert "class AnalysisApiUseCase" in use_case_source
    assert "AnalysisApiDailyReportFailedError" in use_case_source
    assert "agent.handle_request" not in api_source
    assert "risks = result.get" not in api_source

    for function_name in (
        "generate_daily",
        "generate_weekly",
        "check_risks",
    ):
        function_source = _function_source(api_source, function_name)
        assert "get_agent()" not in function_source
        assert "agent.handle_request" not in function_source
        assert "AnalysisApiUseCase = Depends(get_analysis_api_use_case)" in (
            function_source
        )


def test_analysis_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """Analysis service shell should not own request action orchestration."""
    service_source = Path(
        "shared/capabilities/analysis/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/analysis/core/request_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class AnalysisRequestUseCase" in use_case_source
    assert "class AnalysisReportGeneratorPort(Protocol)" in use_case_source
    assert "class AnalysisMilestoneCheckerPort(Protocol)" in use_case_source
    assert 'action == "daily_report"' in use_case_source
    assert 'action == "weekly_report"' in use_case_source
    assert 'action == "check_milestones"' in use_case_source
    assert "unknown_action_error()" in use_case_source

    assert "AnalysisRequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'action == "daily_report"' not in handle_source
    assert 'action == "weekly_report"' not in handle_source
    assert 'action == "check_milestones"' not in handle_source
    assert "self._daily.generate" not in handle_source
    assert "self._weekly.generate" not in handle_source
    assert "self._milestone.check" not in handle_source
    assert "unknown_action_error()" not in handle_source


def test_analysis_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """Analysis service shell should not own sync.completed event workflow."""
    service_source = Path(
        "shared/capabilities/analysis/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/analysis/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class AnalysisEventUseCase" in use_case_source
    assert "class AnalysisEventFactoryPort(Protocol)" in use_case_source
    assert "class AnalysisMetricsPort(Protocol)" in use_case_source
    assert "EventTypes.SYNC_COMPLETED" in use_case_source
    assert "REPORT_DAILY_GENERATED" in use_case_source
    assert "ANALYSIS_RISK_DETECTED" in use_case_source
    assert "ANALYSIS_QUALITY_EVALUATED" in use_case_source
    assert "REPORT_WEEKLY_GENERATED" in use_case_source
    assert "daily_report_failed" in use_case_source
    assert "milestone_check_failed" in use_case_source
    assert "quality_eval_failed" in use_case_source
    assert "weekly_report_failed" in use_case_source

    assert "AnalysisEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "EventTypes.SYNC_COMPLETED" not in handle_source
    assert "_on_sync_completed" not in service_source
    assert "REPORT_DAILY_GENERATED" not in handle_source
    assert "ANALYSIS_RISK_DETECTED" not in handle_source
    assert "self._daily.generate" not in service_source
    assert "self._milestone.check" not in service_source
    assert "self._quality.evaluate_all" not in service_source


def test_analysis_outbox_delivery_delegates_to_application_use_case() -> None:
    """Analysis service shell should not own outbox delivery branching."""
    service_source = Path(
        "shared/capabilities/analysis/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/analysis/core/outbox_delivery_use_cases.py"
    ).read_text()

    assert "class AnalysisOutboxDeliveryUseCase" in use_case_source
    assert "class AnalysisOutboxEventBusPort(Protocol)" in use_case_source
    assert "class AnalysisOutboxEventPublisherPort(Protocol)" in use_case_source
    assert "async def publish_pending_events" in use_case_source
    assert "async def publish_event_via_outbox" in use_case_source
    assert "def event_from_outbox" in use_case_source
    assert "async def publish_staged_event" in use_case_source
    assert "await self._event_bus.connect()" in use_case_source
    assert "await self._event_publisher.publish(event)" in use_case_source
    assert "analysis_outbox_publish_failed" in use_case_source

    assert "AnalysisOutboxDeliveryUseCase" in service_source
    assert "def _outbox_delivery_use_case" in service_source
    assert (
        "return await self._outbox_delivery_use_case().publish_pending_events"
        in _function_source(service_source, "publish_pending_analysis_events")
    )
    assert (
        "return await self._outbox_delivery_use_case().publish_event_via_outbox(event)"
        in _function_source(service_source, "publish_event_via_outbox")
    )
    staged_source = _function_source(service_source, "_publish_staged_analysis_event")
    assert "rows = await self._outbox_store.list_pending" not in service_source
    assert "await self._event_bus.connect()" not in staged_source
    assert "await self._event_publisher.publish(event)" not in staged_source
    assert "analysis_outbox_publish_failed" not in service_source


def test_sync_api_delegates_trigger_and_status_to_application_use_case() -> None:
    """Sync HTTP trigger/status routes should not own agent orchestration."""
    api_source = Path("shared/capabilities/sync/api/sync.py").read_text()
    use_case_source = Path("shared/capabilities/sync/core/api_use_cases.py").read_text()

    assert "class SyncApiAgentPort(Protocol)" in use_case_source
    assert "class SyncApiUseCase" in use_case_source
    assert "triggered_by=\"api\"" in use_case_source
    assert "agent.trigger_sync" not in api_source
    assert "agent.trigger_openproject_sync" not in api_source
    assert "agent.trigger_feishu_bitable_sync" not in api_source
    assert "agent.handle_request" not in api_source

    for function_name in (
        "trigger_sync",
        "trigger_openproject_sync",
        "trigger_feishu_bitable_sync",
        "sync_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "get_agent()" not in function_source
        assert "agent." not in function_source
        assert "SyncApiUseCase = Depends(get_sync_api_use_case)" in function_source


def test_sync_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """Sync service shell should not own request action orchestration."""
    service_source = Path("shared/capabilities/sync/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/sync/core/request_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class SyncRequestUseCase" in use_case_source
    assert "class SyncRequestAgentPort(Protocol)" in use_case_source
    assert 'action == "sync_now"' in use_case_source
    assert 'action == "sync_openproject"' in use_case_source
    assert 'action == "sync_feishu_bitable"' in use_case_source
    assert 'action == "status"' in use_case_source
    assert "unknown_action_error()" in use_case_source

    assert "SyncRequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'action == "sync_now"' not in handle_source
    assert 'action == "sync_openproject"' not in handle_source
    assert 'action == "sync_feishu_bitable"' not in handle_source
    assert 'action == "status"' not in handle_source
    assert "trigger_sync(triggered_by=\"manual\")" not in handle_source
    assert "trigger_openproject_sync(triggered_by=\"manual\")" not in handle_source
    assert "trigger_feishu_bitable_sync(triggered_by=\"manual\")" not in handle_source
    assert "unknown_action_error()" not in handle_source


def test_sync_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """Sync service shell should not own sync.trigger event parsing."""
    service_source = Path("shared/capabilities/sync/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/sync/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class SyncEventRunnerPort(Protocol)" in use_case_source
    assert "class SyncEventUseCase" in use_case_source
    assert "SyncTriggerPayload.model_validate(event.payload)" in use_case_source
    assert "sync_invalid_trigger_payload" in use_case_source
    assert "sync_unsupported_scope" in use_case_source
    assert "trigger_openproject_sync(" in use_case_source
    assert "trigger_feishu_bitable_sync(" in use_case_source
    assert "trigger_sync(" in use_case_source
    assert "def _normalize_sync_scope" in use_case_source

    assert "SyncEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "SyncTriggerPayload" not in service_source
    assert "ValidationError" not in service_source
    assert "sync_invalid_trigger_payload" not in handle_source
    assert "sync_unsupported_scope" not in handle_source
    assert "def _normalize_sync_scope" not in service_source


def test_sync_scope_execution_delegates_to_application_use_case() -> None:
    """Sync service shell should not own scoped lifecycle event orchestration."""
    service_source = Path("shared/capabilities/sync/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/sync/core/scope_execution_use_cases.py"
    ).read_text()
    run_source = _function_source(service_source, "_run_sync_scope")

    assert "class SyncScopeExecutionUseCase" in use_case_source
    assert "class SyncScopeEventFactoryPort(Protocol)" in use_case_source
    assert "class SyncScopeEventPublisherPort(Protocol)" in use_case_source
    assert "class SyncScopeMetricsPort(Protocol)" in use_case_source
    assert "async def run_scope" in use_case_source
    assert "EventTypes.SYNC_STARTED" in use_case_source
    assert "EventTypes.SYNC_COMPLETED" in use_case_source
    assert "EventTypes.SYNC_FAILED" in use_case_source
    assert "await self._event_publisher.publish_sync_event_via_outbox(event)" in (
        use_case_source
    )
    assert "def _sync_errors" in use_case_source
    assert "def _synced_count" in use_case_source

    assert "SyncScopeExecutionUseCase" in service_source
    assert "def _scope_execution_use_case" in service_source
    assert "return await self._scope_execution_use_case().run_scope" in run_source
    assert "async def publish_sync_event_via_outbox" in service_source
    assert "def record_sync_success" in service_source
    assert "def record_sync_failure" in service_source
    assert "EventTypes.SYNC_STARTED" not in run_source
    assert "EventTypes.SYNC_COMPLETED" not in run_source
    assert "EventTypes.SYNC_FAILED" not in run_source
    assert "result.get(\"op_to_feishu\"" not in service_source
    assert "SYNC_DURATION.observe(time.perf_counter()" not in service_source


def test_sync_scheduler_delegates_to_application_use_case() -> None:
    """Sync scheduler should not own agent trigger orchestration."""
    app_source = Path("shared/capabilities/sync/app/main.py").read_text()
    use_case_source = Path(
        "shared/capabilities/sync/core/scheduler_use_cases.py"
    ).read_text()

    assert "class SyncSchedulerAgentPort(Protocol)" in use_case_source
    assert "class SyncSchedulerUseCase" in use_case_source
    assert 'triggered_by="scheduler"' in use_case_source
    assert ".trigger_sync(" not in app_source
    assert "SyncSchedulerUseCase" in app_source

    function_source = _function_source(app_source, "_scheduled_sync")
    assert ".trigger_sync(" not in function_source
    assert "get_sync_scheduler_use_case().run_scheduled_sync()" in function_source


def test_evolution_app_api_delegates_to_application_use_case() -> None:
    """Evolution HTTP routes should not own agent request/action orchestration."""
    app_source = Path("shared/capabilities/evolution/app/main.py").read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/api_use_cases.py"
    ).read_text()

    assert "class EvolutionApiAgentPort(Protocol)" in use_case_source
    assert "class EvolutionApiUseCase" in use_case_source
    assert '{"action": "trigger_analysis", "days": days}' in use_case_source
    assert "agent.handle_request" not in app_source

    function_source = _function_source(app_source, "trigger_analysis")
    assert "agent.handle_request" not in function_source
    assert "EvolutionApiUseCase = Depends(get_evolution_api_use_case)" in (
        function_source
    )


def test_evolution_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """Evolution service shell should not own trigger-analysis orchestration."""
    service_source = Path(
        "shared/capabilities/evolution/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/request_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class EvolutionRequestUseCase" in use_case_source
    assert "class EvolutionAnalyzerPort(Protocol)" in use_case_source
    assert 'request.get("action") == "trigger_analysis"' in use_case_source
    assert "self._analyzer.analyze(days)" in use_case_source
    assert "self._attach_proposal_approval(proposal)" in use_case_source
    assert 'return {"status": "ok"}' in use_case_source

    assert "EvolutionRequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'request.get("action") == "trigger_analysis"' not in handle_source
    assert "self._analyzer.analyze" not in handle_source
    assert "self._attach_proposal_approval" not in handle_source
    assert 'return {"status": "ok"}' not in handle_source


def test_evolution_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """Evolution service shell should not own event workflow branching."""
    service_source = Path(
        "shared/capabilities/evolution/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class EvolutionEventUseCase" in use_case_source
    assert "class EvolutionApprovalServicePort(Protocol)" in use_case_source
    assert "class EvolutionPatternApprovalGatewayPort(Protocol)" in use_case_source
    assert "class EvolutionEventFactoryPort(Protocol)" in use_case_source
    assert "class EvolutionProposalApprovalPort(Protocol)" in use_case_source
    assert "EventTypes.EVOLUTION_CYCLE_TRIGGERED" in use_case_source
    assert "EventTypes.EVOLUTION_HUMAN_FEEDBACK" in use_case_source
    assert "EventTypes.EVOLUTION_PATTERN_APPROVED" in use_case_source
    assert "EVOLUTION_SKILL_PROPOSED" in use_case_source
    assert "EVOLUTION_PATTERN_PROPOSED" in use_case_source
    assert "evolution_feedback_resolver_required" in use_case_source
    assert "pattern_control_plane_resolver_required" in use_case_source
    assert "pattern_approval_processed" in use_case_source

    assert "EvolutionEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "if event.event_type == EventTypes.EVOLUTION_CYCLE_TRIGGERED" not in (
        handle_source
    )
    assert "EventTypes.EVOLUTION_HUMAN_FEEDBACK" not in handle_source
    assert "EventTypes.EVOLUTION_PATTERN_APPROVED" not in handle_source
    assert "_analyze_and_propose" not in service_source
    assert "_propose_collaboration_patterns" not in service_source
    assert "_process_feedback" not in service_source
    assert "_process_pattern_approval" not in service_source
    assert "ApprovalRequiredError" not in service_source


def test_evolution_outbox_delivery_delegates_to_application_use_case() -> None:
    """Evolution service shell should not own outbox delivery branching."""
    service_source = Path(
        "shared/capabilities/evolution/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/outbox_delivery_use_cases.py"
    ).read_text()

    assert "class EvolutionOutboxDeliveryUseCase" in use_case_source
    assert "class EvolutionOutboxEventBusPort(Protocol)" in use_case_source
    assert "class EvolutionOutboxEventPublisherPort(Protocol)" in use_case_source
    assert "async def publish_pending_events" in use_case_source
    assert "async def publish_event_via_outbox" in use_case_source
    assert "def event_from_outbox" in use_case_source
    assert "async def publish_staged_event" in use_case_source
    assert "await self._event_bus.connect()" in use_case_source
    assert "await self._event_publisher.publish(event)" in use_case_source
    assert "evolution_outbox_publish_failed" in use_case_source

    assert "EvolutionOutboxDeliveryUseCase" in service_source
    assert "def _outbox_delivery_use_case" in service_source
    assert (
        "return await self._outbox_delivery_use_case().publish_pending_events"
        in _function_source(service_source, "publish_pending_evolution_events")
    )
    assert (
        "return await self._outbox_delivery_use_case().publish_event_via_outbox(event)"
        in _function_source(service_source, "publish_event_via_outbox")
    )
    staged_source = _function_source(service_source, "_publish_staged_evolution_event")
    assert "rows = await self._outbox_store.list_pending" not in service_source
    assert "await self._event_bus.connect()" not in staged_source
    assert "await self._event_publisher.publish(event)" not in staged_source
    assert "evolution_outbox_publish_failed" not in service_source


def test_evolution_proposal_approval_delegates_to_application_use_case() -> None:
    """Evolution service shell should not own approval/proposal-record branching."""
    service_source = Path(
        "shared/capabilities/evolution/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/proposal_approval_use_cases.py"
    ).read_text()

    assert "class EvolutionProposalApprovalUseCase" in use_case_source
    assert "class EvolutionApprovalRequestPort(Protocol)" in use_case_source
    assert "ApprovalCategory.TECHNICAL" in use_case_source
    assert "async def attach_approval" in use_case_source
    assert "async def record_control_plane_proposal" in use_case_source
    assert "def infer_proposal_tier" in use_case_source
    assert "def proposal_scope" in use_case_source
    assert "evolution_approval_request_failed" in use_case_source
    assert "control_plane_company_ensure_failed" in use_case_source
    assert "control_plane_evolution_proposal_record_failed" in use_case_source

    attach_source = _function_source(service_source, "_attach_proposal_approval")
    assert "EvolutionProposalApprovalUseCase" in service_source
    assert "def _proposal_approval_use_case" in service_source
    assert "return await self._proposal_approval_use_case().attach_approval" in (
        attach_source
    )
    assert "ApprovalCategory.TECHNICAL" not in service_source
    assert "record_control_plane_proposal(" not in service_source
    assert "def _infer_proposal_tier" not in service_source
    assert "def _proposal_scope" not in service_source


def test_user_interaction_scheduler_delegates_to_application_use_case() -> None:
    """User Interaction scheduler should not own agent request/action orchestration."""
    app_source = Path("services/gateways/user_interaction/app/main.py").read_text()
    use_case_source = Path(
        "services/gateways/user_interaction/core/scheduler_use_cases.py"
    ).read_text()

    assert "class UserInteractionSchedulerAgentPort(Protocol)" in use_case_source
    assert "class UserInteractionSchedulerUseCase" in use_case_source
    assert '{"action": action}' in use_case_source
    assert ".handle_request(" not in app_source
    assert "UserInteractionSchedulerUseCase" in app_source

    function_source = _function_source(app_source, "_run_scheduled_action")
    assert ".handle_request(" not in function_source
    assert "get_scheduler_use_case().run_scheduled_action(action)" in function_source


def test_dev_api_uses_shared_error_contracts() -> None:
    """Dev HTTP adapters use shared compatibility error codes."""
    dev_source = Path("agents/dev_agent/api/dev.py").read_text()

    assert "raise_dev_agent_not_ready" in dev_source
    assert "from fastapi import APIRouter, HTTPException" not in dev_source
    assert "HTTPException(status_code=503" not in dev_source


def test_dev_api_delegates_to_application_use_case() -> None:
    """Dev HTTP routes should not own agent request/action orchestration."""
    api_source = Path("agents/dev_agent/api/dev.py").read_text()
    use_case_source = Path("agents/dev_agent/core/api_use_cases.py").read_text()

    assert "class DevApiAgentPort(Protocol)" in use_case_source
    assert "class DevApiUseCase" in use_case_source
    assert "DevWorkflowApprovalCommand" in use_case_source
    assert "agent.handle_request" not in api_source

    for function_name in (
        "list_tasks",
        "list_failed_tasks",
        "get_task_status",
        "retry_task",
        "cancel_workflow",
        "approve_workflow",
    ):
        function_source = _function_source(api_source, function_name)
        assert "_get_agent()" not in function_source
        assert "agent.handle_request" not in function_source
        assert "DevApiUseCase = Depends(get_dev_api_use_case)" in function_source


def test_dev_agent_request_dispatch_delegates_to_application_use_case() -> None:
    """Dev agent service should not own request action business branching."""
    service_source = Path("agents/dev_agent/service/agent.py").read_text()
    use_case_source = Path("agents/dev_agent/core/request_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class DevApprovalGatePort(Protocol)" in use_case_source
    assert "class DevWorkflowExecutorPort(Protocol)" in use_case_source
    assert "class DevRequestUseCase" in use_case_source
    assert "async def _approve_workflow" in use_case_source
    assert "WorkflowPlan.model_validate" in use_case_source
    assert "approve_workflow_control_plane_required" in use_case_source

    assert "_dispatch_action" not in service_source
    assert "DevRequestUseCase" in service_source
    assert "def _request_use_case" in service_source
    assert ".handle(request)" in handle_source
    assert "if action == \"get_task_status\"" not in handle_source
    assert "if action == \"approve_workflow\"" not in handle_source
    assert "WorkflowPlan.model_validate" not in service_source
    assert "approve_workflow_control_plane_required" not in service_source


def test_dev_agent_event_dispatch_delegates_to_application_use_case() -> None:
    """Dev agent service should not own inbound event workflow branching."""
    service_source = Path("agents/dev_agent/service/agent.py").read_text()
    use_case_source = Path("agents/dev_agent/core/event_use_cases.py").read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class DevEventUseCase" in use_case_source
    assert "class DevTaskSanitizerPort(Protocol)" in use_case_source
    assert "class DevRiskAssessorPort(Protocol)" in use_case_source
    assert "class DevResultCollectorPort(Protocol)" in use_case_source
    assert "class DevEventFactoryPort(Protocol)" in use_case_source
    assert "EventTypes.PM_TASKS_READY_FOR_DEV" in use_case_source
    assert "EventTypes.QA_ACCEPTANCE_COMPLETED" in use_case_source
    assert "TaskInput(" in use_case_source
    assert "RiskLevel.CRITICAL" in use_case_source
    assert "task_rejected_critical" in use_case_source
    assert "qa_result_received" in use_case_source
    assert "result_collector_not_available" in use_case_source

    assert "DevEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "if event.event_type == EventTypes.PM_TASKS_READY_FOR_DEV" not in (
        handle_source
    )
    assert "if event.event_type == EventTypes.QA_ACCEPTANCE_COMPLETED" not in (
        handle_source
    )
    assert "_handle_tasks_ready" not in service_source
    assert "_handle_qa_result" not in service_source
    assert "TaskInput(" not in service_source
    assert "task_rejected_critical" not in service_source
    assert "qa_result_received" not in service_source


def test_dev_agent_workflow_execution_delegates_to_application_use_case() -> None:
    """Dev service shell should not own task planning or AgentForge submission."""
    service_source = Path("agents/dev_agent/service/agent.py").read_text()
    use_case_source = Path(
        "agents/dev_agent/core/workflow_execution_use_cases.py"
    ).read_text()

    assert "class DevWorkflowExecutionUseCase" in use_case_source
    assert "class DevWorkflowPlannerPort(Protocol)" in use_case_source
    assert "class DevWorkflowValidatorPort(Protocol)" in use_case_source
    assert "class DevToolRouterPort(Protocol)" in use_case_source
    assert "class DevForgeWorkflowClientPort(Protocol)" in use_case_source
    assert "async def process_single_task" in use_case_source
    assert "async def plan_and_execute" in use_case_source
    assert "async def request_workflow_approval" in use_case_source
    assert "async def execute_workflow" in use_case_source
    assert "Workflow planning failed" in use_case_source
    assert "Start high-risk AgentForge workflow" in use_case_source
    assert "EventTypes.DEV_WORKFLOW_CREATED" in use_case_source

    assert "DevWorkflowExecutionUseCase" in service_source
    assert "def _workflow_execution_use_case" in service_source
    for function_name in (
        "_process_single_task",
        "_plan_and_execute",
        "_request_workflow_approval",
        "_execute_workflow",
    ):
        function_source = _function_source(service_source, function_name)
        assert "self._workflow_execution_use_case()" in function_source

    assert "await repo.create_task(" not in service_source
    assert "Workflow planning failed" not in service_source
    assert "for node in plan.nodes" not in service_source
    assert "Start high-risk AgentForge workflow" not in service_source
    assert "await self._forge.create_workflow(plan)" not in service_source
    assert "await self._forge.run_workflow(workflow_id)" not in service_source
    assert "workflow_started_at=datetime.now" not in service_source


def test_dev_scheduler_keeps_persistence_details_behind_ports() -> None:
    """Dev scheduler shell should not own SQL or ORM mutation details."""
    app_source = Path("agents/dev_agent/app/main.py").read_text()
    use_case_source = Path("agents/dev_agent/core/scheduler_use_cases.py").read_text()
    port_source = Path("agents/dev_agent/core/repositories.py").read_text()
    task_adapter_source = Path("agents/dev_agent/db/task_store.py").read_text()
    repository_source = Path("agents/dev_agent/db/repository.py").read_text()
    lock_source = Path("agents/dev_agent/db/reconcile_lock.py").read_text()

    assert "class DevSchedulerUseCase" in use_case_source
    assert "workflow_poll_interval" in use_case_source
    assert "_poll_interval" not in app_source
    assert "from sqlalchemy import text" not in app_source
    assert "session.execute(" not in app_source
    assert "session.flush(" not in app_source
    assert "pg_try_advisory_lock" not in app_source
    assert "pg_advisory_unlock" not in app_source

    assert "SqlAlchemyDevReconcileLock(session)" in app_source
    assert "repo.mark_polled(task.id, polled_at=now)" in app_source
    assert "_scheduler_use_case.poll_interval(elapsed)" in app_source
    assert "_scheduler_use_case.expire_stale_pending(repo, hours=24)" in app_source

    assert "async def mark_polled" in port_source
    assert "async def mark_polled" in task_adapter_source
    assert "async def mark_polled" in repository_source
    assert "pg_try_advisory_lock" in lock_source
    assert "pg_advisory_unlock" in lock_source


def test_dsar_api_uses_shared_error_contracts() -> None:
    """DSAR HTTP adapters use shared compatibility error codes."""
    dsar_source = Path("shared/api/dsar_router.py").read_text()

    assert "raise_dsar_approval_required" in dsar_source
    assert "from fastapi import APIRouter, Depends, HTTPException, Query" not in dsar_source
    assert "HTTPException(status_code=403" not in dsar_source


def test_outbound_admin_api_uses_shared_error_contracts() -> None:
    """Outbound admin HTTP adapters use shared compatibility error codes."""
    admin_source = Path("shared/messaging/outbound/api/admin.py").read_text()

    assert "raise_outbound_adapter_not_found" in admin_source
    assert "from fastapi import APIRouter, Depends, HTTPException" not in admin_source
    assert "HTTPException(status_code=404" not in admin_source


def test_feishu_router_uses_shared_error_contracts() -> None:
    """Feishu HTTP adapters use shared compatibility error codes."""
    feishu_source = Path("shared/integrations/feishu/router.py").read_text()

    assert "raise_feishu_signature_key_not_configured" in feishu_source
    assert "raise_feishu_invalid_signature" in feishu_source
    assert "raise_feishu_invalid_json" in feishu_source
    assert "from fastapi import APIRouter, Header, HTTPException, Request" not in feishu_source
    assert "HTTPException(status_code=401" not in feishu_source
    assert "HTTPException(status_code=400" not in feishu_source


def test_internal_auth_uses_shared_error_contracts() -> None:
    """Internal service auth uses shared compatibility error codes."""
    auth_source = Path("shared/middleware/internal_auth.py").read_text()

    assert "raise_internal_auth_not_configured" in auth_source
    assert "raise_internal_auth_unauthorized" in auth_source
    assert "from fastapi import HTTPException, Request" not in auth_source
    assert "HTTPException(" not in auth_source


def test_wecom_router_uses_shared_error_contracts() -> None:
    """WeCom HTTP adapters use shared compatibility error codes."""
    wecom_source = Path("shared/integrations/wecom/router.py").read_text()

    assert "raise_wecom_security_not_configured" in wecom_source
    assert "raise_wecom_invalid_signature" in wecom_source
    assert "raise_wecom_missing_encrypted_payload" in wecom_source
    assert "raise_wecom_invalid_xml_payload" in wecom_source
    assert "from fastapi import APIRouter, HTTPException, Query, Request" not in wecom_source
    assert "HTTPException(" not in wecom_source


def test_mcp_routes_use_shared_error_contracts() -> None:
    """MCP REST-style HTTP adapters use shared compatibility error codes."""
    mcp_source = Path("shared/protocols/mcp/server/routes.py").read_text()

    assert "raise_mcp_invalid_json" in mcp_source
    assert "raise_mcp_tool_name_required" in mcp_source
    assert "raise_mcp_tool_not_found" in mcp_source
    assert "raise_mcp_resource_not_found" in mcp_source
    assert "raise_mcp_prompt_not_found" in mcp_source
    assert "from fastapi import APIRouter, HTTPException, Request, status" not in mcp_source
    assert "HTTPException(" not in mcp_source


def test_a2a_routes_use_shared_error_contracts() -> None:
    """A2A server routes use shared compatibility error codes."""
    a2a_source = Path("shared/protocols/a2a/server/routes.py").read_text()

    assert "raise_a2a_not_enabled" in a2a_source
    assert "raise_a2a_task_not_found" in a2a_source
    assert "from fastapi import APIRouter, Depends, HTTPException, Request, status" not in (
        a2a_source
    )
    assert "HTTPException(" not in a2a_source


def test_a2a_auth_uses_shared_error_contracts() -> None:
    """A2A auth middleware uses shared compatibility error codes."""
    auth_source = Path("shared/protocols/a2a/middleware/auth.py").read_text()

    assert "raise_a2a_auth_token_expired" in auth_source
    assert "raise_a2a_auth_invalid_token" in auth_source
    assert "raise_a2a_auth_missing_or_invalid" in auth_source
    assert "raise_a2a_missing_required_scope" in auth_source
    assert "raise_a2a_rate_limit_exceeded" in auth_source
    assert "raise HTTPException(" not in auth_source
    assert "status.HTTP_" not in auth_source


def test_control_plane_api_uses_shared_error_contracts() -> None:
    """Control-plane HTTP adapters use shared compatibility error codes."""
    control_plane_source = Path("shared/control_plane/api.py").read_text()

    assert "raise_control_plane_api_error" in control_plane_source
    assert "from fastapi import APIRouter, Depends, HTTPException, Query" not in (
        control_plane_source
    )
    assert "raise HTTPException(" not in control_plane_source


def test_control_plane_approval_gate_uses_approval_store_port() -> None:
    """Approval-gate services should not directly construct repositories."""
    gate_source = Path("shared/control_plane/approval_gate.py").read_text()
    port_source = Path("shared/control_plane/approval_ports.py").read_text()
    adapter_source = Path("shared/control_plane/approval_store.py").read_text()

    assert "class ControlPlaneApprovalStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneApprovalStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "ControlPlaneRepository" not in gate_source
    assert "ControlPlaneApprovalStore" in gate_source
    assert "SqlAlchemyControlPlaneApprovalStore(session)" in gate_source


def test_control_plane_approval_api_delegates_to_use_case() -> None:
    """Control-plane approval routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    use_case_source = Path("shared/control_plane/approval_use_cases.py").read_text()

    for function_name in ("list_approvals", "approve", "reject"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n    @router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneApprovalStore(session)" in function_source
        assert "ApprovalGate(" not in function_source
        assert "append_audit_event" not in function_source
        assert "update_evolution_proposal_approval_state_by_approval" not in function_source

    assert "resolve_approval_and_sync_proposal" in api_source
    assert "ApprovalGate(" in use_case_source
    assert "update_evolution_proposal_approval_state_by_approval" in use_case_source
    assert "append_audit_event" in use_case_source


def test_control_plane_agent_registry_api_delegates_to_use_cases() -> None:
    """Control-plane agent registry routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/agent_registry_ports.py").read_text()
    adapter_source = Path("shared/control_plane/agent_registry_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/agent_registry_use_cases.py"
    ).read_text()

    assert "class ControlPlaneAgentRegistryStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneAgentRegistryStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_agent_role_with_audit" in use_case_source
    assert "update_agent_role_with_audit" in use_case_source
    assert "update_agent_status_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "DEFAULT_ADAPTER_REGISTRY" in use_case_source

    for function_name in (
        "list_agents",
        "create_agent",
        "get_agent",
        "update_agent",
        "update_agent_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneAgentRegistryStore(session)" in function_source
        assert "DEFAULT_ADAPTER_REGISTRY" not in function_source

    for function_name in ("create_agent", "update_agent", "update_agent_status"):
        function_source = _function_source(api_source, function_name)
        assert "append_audit_event" not in function_source
        assert "update_agent_role_status" not in function_source


def test_control_plane_run_api_delegates_to_query_use_cases() -> None:
    """Control-plane run read routes should not own repository queries."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/agent_run_ports.py").read_text()
    adapter_source = Path("shared/control_plane/agent_run_store.py").read_text()
    use_case_source = Path("shared/control_plane/agent_run_use_cases.py").read_text()

    assert "class ControlPlaneAgentRunStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneAgentRunStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "list_agent_runs" in use_case_source
    assert "get_agent_run" in use_case_source

    for function_name in ("list_runs", "get_run"):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneAgentRunStore(session)" in function_source


def test_control_plane_company_api_delegates_to_use_cases() -> None:
    """Control-plane company routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/company_ports.py").read_text()
    adapter_source = Path("shared/control_plane/company_store.py").read_text()
    use_case_source = Path("shared/control_plane/company_use_cases.py").read_text()

    assert "class ControlPlaneCompanyStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneCompanyStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_company_with_audit" in use_case_source
    assert "update_company_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source

    for function_name in (
        "list_companies",
        "create_company",
        "get_company",
        "update_company",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneCompanyStore(session)" in function_source

    for function_name in ("create_company", "update_company"):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source


def test_control_plane_goal_api_delegates_to_use_cases() -> None:
    """Control-plane goal routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/goal_ports.py").read_text()
    adapter_source = Path("shared/control_plane/goal_store.py").read_text()
    use_case_source = Path("shared/control_plane/goal_use_cases.py").read_text()

    assert "class ControlPlaneGoalStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneGoalStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_goal_with_audit" in use_case_source
    assert "update_goal_status_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "ParentGoalNotFoundError" in use_case_source

    for function_name in (
        "list_goals",
        "create_goal",
        "get_goal",
        "update_goal_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneGoalStore(session)" in function_source

    for function_name in ("create_goal", "update_goal_status"):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source


def test_control_plane_work_item_api_delegates_to_use_cases() -> None:
    """Control-plane work-item routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/work_item_ports.py").read_text()
    adapter_source = Path("shared/control_plane/work_item_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/work_item_use_cases.py"
    ).read_text()

    assert "class ControlPlaneWorkItemStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneWorkItemStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_work_item_with_audit" in use_case_source
    assert "update_work_item_status_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "WorkItemGoalNotFoundError" in use_case_source
    assert "WorkItemDependencyNotFoundError" in use_case_source

    for function_name in (
        "list_work_items",
        "create_work_item",
        "get_work_item",
        "update_work_item_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneWorkItemStore(session)" in function_source

    for function_name in ("create_work_item", "update_work_item_status"):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source


def test_control_plane_decision_api_delegates_to_use_cases() -> None:
    """Control-plane decision routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/decision_ports.py").read_text()
    adapter_source = Path("shared/control_plane/decision_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/decision_use_cases.py"
    ).read_text()

    assert "class ControlPlaneDecisionStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneDecisionStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_decision_with_audit" in use_case_source
    assert "update_decision_status_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "DecisionLinkMismatchError" in use_case_source

    for function_name in (
        "list_decisions",
        "create_decision",
        "get_decision",
        "update_decision_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneDecisionStore(session)" in function_source

    for function_name in ("create_decision", "update_decision_status"):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source
        assert "validate_execution_links" not in function_source


def test_control_plane_artifact_api_delegates_to_use_cases() -> None:
    """Control-plane artifact routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/artifact_ports.py").read_text()
    adapter_source = Path("shared/control_plane/artifact_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/artifact_use_cases.py"
    ).read_text()

    assert "class ControlPlaneArtifactStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneArtifactStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_artifact_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "ArtifactLinkMismatchError" in use_case_source

    for function_name in (
        "list_artifacts",
        "create_artifact",
        "get_artifact",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneArtifactStore(session)" in function_source

    function_source = _function_source(api_source, "create_artifact")
    assert "AuditEvent(" not in function_source
    assert "append_audit_event" not in function_source
    assert "validate_execution_links" not in function_source


def test_control_plane_evolution_proposal_api_delegates_to_use_cases() -> None:
    """Control-plane evolution proposal routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path(
        "shared/control_plane/evolution_proposal_ports.py"
    ).read_text()
    adapter_source = Path(
        "shared/control_plane/evolution_proposal_store.py"
    ).read_text()
    use_case_source = Path(
        "shared/control_plane/evolution_proposal_use_cases.py"
    ).read_text()

    assert "class ControlPlaneEvolutionProposalStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneEvolutionProposalStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_evolution_proposal_with_audit" in use_case_source
    assert "update_evolution_proposal_status_with_audit" in use_case_source
    assert "ApprovalGate(store)" in use_case_source
    assert "append_audit_event" in use_case_source

    for function_name in (
        "list_evolution_proposals",
        "create_evolution_proposal",
        "get_evolution_proposal",
        "update_evolution_proposal_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneEvolutionProposalStore(session)" in function_source
        assert "ApprovalGate(" not in function_source

    for function_name in (
        "create_evolution_proposal",
        "update_evolution_proposal_status",
    ):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source
        assert "_rollout_requires_approval" not in function_source


def test_control_plane_budget_api_delegates_to_use_cases() -> None:
    """Control-plane budget routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/budget_ports.py").read_text()
    adapter_source = Path("shared/control_plane/budget_store.py").read_text()
    use_case_source = Path("shared/control_plane/budget_use_cases.py").read_text()

    assert "class ControlPlaneBudgetStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneBudgetStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "create_budget_policy_with_audit" in use_case_source
    assert "update_budget_policy_with_audit" in use_case_source
    assert "append_audit_event" in use_case_source
    assert "ActiveBudgetPolicyConflictError" in use_case_source

    for function_name in (
        "list_budget_policies",
        "create_budget_policy",
        "get_budget_policy",
        "update_budget_policy",
        "list_budget_usage",
    ):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneBudgetStore(session)" in function_source

    for function_name in ("create_budget_policy", "update_budget_policy"):
        function_source = _function_source(api_source, function_name)
        assert "AuditEvent(" not in function_source
        assert "append_audit_event" not in function_source
        assert "ensure_no_active_budget_policy_conflict" not in function_source


def test_control_plane_budget_guard_uses_budget_store_port() -> None:
    """Infra budget enforcement should not construct control-plane repositories."""
    guard_source = Path("shared/control_plane/budget_guard.py").read_text()
    port_source = Path("shared/control_plane/budget_guard_ports.py").read_text()
    adapter_source = Path("shared/control_plane/budget_guard_store.py").read_text()
    llm_source = Path("shared/infra/llm_gateway.py").read_text()
    tool_source = Path("shared/infra/tool_registry.py").read_text()

    assert "class ControlPlaneBudgetGuardStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneBudgetGuardStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "ControlPlaneBudgetGuardStore" in guard_source
    assert "ControlPlaneRepository" not in guard_source

    for source in (llm_source, tool_source):
        assert "ControlPlaneRepository" not in source
        assert "SqlAlchemyControlPlaneBudgetGuardStore(session)" in source


def test_control_plane_audit_timeline_api_delegates_to_use_cases() -> None:
    """Control-plane audit and timeline routes should not own repository queries."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/audit_timeline_ports.py").read_text()
    adapter_source = Path("shared/control_plane/audit_timeline_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/audit_timeline_use_cases.py"
    ).read_text()

    assert "class ControlPlaneAuditTimelineStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneAuditTimelineStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "build_timeline" in use_case_source
    assert "TimelineScopeRequiredError" in use_case_source
    assert "_list_run_scoped_decisions" in use_case_source
    assert "_list_run_scoped_artifacts" in use_case_source
    assert "if not run_ids:" in use_case_source

    for function_name in ("list_audit_events", "get_timeline"):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneAuditTimelineStore(session)" in function_source

    function_source = _function_source(api_source, "get_timeline")
    assert "list_decisions(" not in function_source
    assert "list_artifacts(" not in function_source
    assert "_timeline_sort_key" not in function_source


def test_control_plane_agent_operations_delegate_to_use_cases_and_ports() -> None:
    """Wakeup and heartbeat routes should not construct repositories directly."""
    api_source = Path("shared/control_plane/api.py").read_text()
    port_source = Path("shared/control_plane/agent_operation_ports.py").read_text()
    adapter_source = Path("shared/control_plane/agent_operation_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/agent_operation_use_cases.py"
    ).read_text()
    runner_source = Path("shared/control_plane/agent_runner.py").read_text()
    lifecycle_source = Path("shared/control_plane/agent_run_lifecycle.py").read_text()
    scheduler_source = Path("shared/control_plane/scheduler.py").read_text()
    evidence_source = Path("shared/control_plane/run_evidence.py").read_text()

    assert "class ControlPlaneAgentOperationStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlaneAgentOperationStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "wake_agent_definition" in use_case_source
    assert "run_heartbeat_scheduler_once" in use_case_source
    assert "ControlPlaneAgentRunner(store)" in use_case_source
    assert "ControlPlaneHeartbeatScheduler(store)" in use_case_source

    for function_name in ("wake_agent", "run_heartbeat_scheduler_once"):
        function_source = _function_source(api_source, function_name)
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlaneAgentOperationStore(session)" in function_source

    for source in (runner_source, scheduler_source):
        assert "ControlPlaneAgentOperationStore" in source
        assert "ControlPlaneRepository" not in source

    assert "start_agent_wakeup_run" in runner_source
    assert "complete_agent_wakeup_run" in runner_source
    assert "fail_agent_wakeup_run" in runner_source
    assert "AgentRun(" not in runner_source
    assert "AuditEvent(" not in runner_source
    assert "create_run_evidence_artifact" not in runner_source

    assert "class AgentWakeupRunRecord" in lifecycle_source
    assert "AgentRun(" in lifecycle_source
    assert "AuditEvent(" in lifecycle_source
    assert "create_run_evidence_artifact" in lifecycle_source
    assert "ControlPlaneRepository" not in lifecycle_source

    assert "ControlPlaneRunEvidenceStore" in evidence_source
    assert "ControlPlaneRepository" not in evidence_source


def test_control_plane_repository_is_confined_to_store_adapters() -> None:
    """Concrete ControlPlaneRepository access should stay behind store adapters."""
    allowed_control_plane_files = {Path("shared/control_plane/repository.py")}
    offenders: list[str] = []

    for path in _python_files(Path("shared/control_plane")):
        if path in allowed_control_plane_files or path.name.endswith("_store.py"):
            continue
        source = path.read_text()
        if "ControlPlaneRepository" in source:
            offenders.append(str(path))

    for root in (Path("agents"), Path("services"), Path("shared/capabilities")):
        if not root.exists():
            continue
        for path in _python_files(root):
            source = path.read_text()
            if (
                "ControlPlaneRepository(" in source
                or "shared.control_plane.repository import ControlPlaneRepository"
                in source
            ):
                offenders.append(str(path))

    assert offenders == []


def test_control_plane_runtime_plugin_delegates_to_use_cases_and_ports() -> None:
    """Runtime plugin should not own repository writes or bootstrap assembly."""
    plugin_source = Path("shared/app/plugins/control_plane.py").read_text()
    port_source = Path("shared/control_plane/runtime_plugin_ports.py").read_text()
    adapter_source = Path("shared/control_plane/runtime_plugin_store.py").read_text()
    use_case_source = Path(
        "shared/control_plane/runtime_plugin_use_cases.py"
    ).read_text()
    evidence_port_source = Path("shared/control_plane/run_evidence_ports.py").read_text()

    assert "class ControlPlaneRuntimePluginStore" in port_source
    assert "ControlPlaneRunEvidenceStore" in port_source
    assert "class ControlPlaneRunEvidenceStore(Protocol)" in evidence_port_source
    assert "SqlAlchemyControlPlaneRuntimePluginStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "ensure_core_organization_role_agents" in adapter_source
    assert "ensure_core_runtime_agent_roles" in adapter_source

    assert "start_event_run" in use_case_source
    assert "complete_event_run" in use_case_source
    assert "fail_event_run" in use_case_source
    assert "bootstrap_core_agent_roles" in use_case_source
    assert "create_run_evidence_artifact" in use_case_source

    assert "ControlPlaneRepository" not in plugin_source
    assert "create_run_evidence_artifact" not in plugin_source
    assert "AgentRun(" not in plugin_source
    assert "AuditEvent(" not in plugin_source
    assert "CompanyContext(" not in plugin_source
    assert "SqlAlchemyControlPlaneRuntimePluginStore(session)" in plugin_source


def test_control_plane_role_bootstrap_uses_store_port() -> None:
    """Role bootstrap use cases should not depend on concrete repositories."""
    use_case_source = Path("shared/control_plane/bootstrap.py").read_text()
    port_source = Path("shared/control_plane/bootstrap_ports.py").read_text()
    adapter_source = Path("shared/control_plane/bootstrap_store.py").read_text()
    runtime_adapter_source = Path("shared/control_plane/runtime_plugin_store.py").read_text()

    assert "class ControlPlaneRoleBootstrapStore(Protocol)" in port_source
    assert "create_company_if_absent" in port_source
    assert "create_agent_role_if_absent" in port_source
    assert "ControlPlaneRoleBootstrapStore" in use_case_source
    assert "ControlPlaneRepository" not in use_case_source
    assert "session.begin_nested" not in use_case_source
    assert "IntegrityError" not in use_case_source
    assert "create_agent_role_if_absent" in use_case_source
    assert "create_company_if_absent" in use_case_source

    assert "SqlAlchemyControlPlaneRoleBootstrapStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "session.begin_nested" in adapter_source
    assert "IntegrityError" in adapter_source
    assert "SqlAlchemyControlPlaneRoleBootstrapStore(self._session)" in (
        runtime_adapter_source
    )


def test_control_plane_prompt_config_uses_prompt_store_port() -> None:
    """Prompt-config helpers should not directly construct repositories."""
    helper_source = Path("shared/control_plane/agent_prompt_config.py").read_text()
    port_source = Path("shared/control_plane/prompt_config_ports.py").read_text()
    adapter_source = Path("shared/control_plane/prompt_config_store.py").read_text()

    assert "class ControlPlanePromptConfigStore(Protocol)" in port_source
    assert "SqlAlchemyControlPlanePromptConfigStore" in adapter_source
    assert "ControlPlaneRepository" in adapter_source
    assert "ControlPlaneRepository" not in helper_source
    assert "ControlPlanePromptConfigStore" in helper_source
    assert "SqlAlchemyControlPlanePromptConfigStore(session)" in helper_source


def test_control_plane_prompt_config_api_delegates_to_use_case() -> None:
    """Control-plane prompt-config routes should not own repository mutations."""
    api_source = Path("shared/control_plane/api.py").read_text()

    for function_name in ("get_agent_prompt_config", "update_agent_prompt_config"):
        start = api_source.index(f"async def {function_name}")
        end = api_source.find("\n\n    @router.", start)
        if end == -1:
            end = len(api_source)
        function_source = api_source[start:end]
        assert "ControlPlaneRepository" not in function_source
        assert "SqlAlchemyControlPlanePromptConfigStore(session)" in function_source
        assert "append_audit_event" not in function_source
        assert "upsert_agent_prompt_config" not in function_source

    assert "update_prompt_config_with_audit" in api_source
    assert "get_or_default_prompt_config" in api_source


def test_backend_boundary_contract_documents_table_owners() -> None:
    """Every durable backend table family must have an explicit owner contract."""
    doc_path = Path("docs/guides/backend-boundaries.md")
    source = doc_path.read_text()

    required_sections = (
        "## 1. Boundary Rules",
        "## 2. Bounded Contexts",
        "## 3. Table Ownership",
        "## 4. API and Event Contracts",
        "## 5. Data Evolution Rules",
        "## 6. Current Known Gaps",
    )
    for section in required_sections:
        assert section in source

    required_tables = (
        "control_plane_companies",
        "control_plane_agent_roles",
        "requirements",
        "requirement_event_outbox",
        "open_questions",
        "feedback_records",
        "llm_usage",
        "pjm_agent_decomposition_records",
        "pjm_agent_event_outbox",
        "dev_agent_tasks",
        "dev_agent_event_outbox",
        "qa_acceptance_runs",
        "qa_agent_event_outbox",
        "sync_agent_mappings",
        "sync_agent_event_outbox",
        "chat_agent_conversation_histories",
        "chat_agent_event_outbox",
        "channel_gateway_event_outbox",
        "coordinator_event_outbox",
        "analysis_agent_report_logs",
        "analysis_agent_event_outbox",
        "evolution_event_outbox",
        "evolution_traces",
        "users",
    )
    for table_name in required_tables:
        assert f"`{table_name}`" in source

    index = Path("docs/INDEX.md").read_text()
    readme = Path("docs/README.md").read_text()
    assert "guides/backend-boundaries.md" in index
    assert "guides/backend-boundaries.md" in readme


def test_identity_user_table_has_migration_and_owner_contract() -> None:
    """The shared User model must have a durable migration and explicit owner."""
    migration_path = Path("migrations/versions/20260506_identity_users_table.py")
    env_source = Path("migrations/env.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    migration_source = migration_path.read_text()

    assert migration_path.exists()
    assert "shared.models.user" in env_source
    assert 'op.create_table(\n        "users"' in migration_source
    assert 'op.create_index("ix_users_email", "users", ["email"], unique=True)' in migration_source
    assert "`users` | Identity / User | Identity/user service path only" in doc_source


def test_inbound_user_service_uses_identity_store_port() -> None:
    """Inbound identity resolution should not directly construct repositories."""
    service_source = Path("shared/messaging/inbound/user_service.py").read_text()
    port_source = Path("shared/core/identity_ports.py").read_text()
    adapter_source = Path("shared/db/user_store.py").read_text()

    assert "class UserIdentityStore(Protocol)" in port_source
    assert "SqlAlchemyUserIdentityStore" in adapter_source
    assert "UserRepository" in adapter_source
    assert "shared.core.identity_ports" in adapter_source
    assert "shared.messaging.inbound" not in adapter_source
    assert "UserRepository" not in service_source
    assert "UserIdentityStore" in service_source
    assert "_new_user_store" in service_source


def test_requirement_events_have_durable_outbox_contract() -> None:
    """Requirement integration events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260507_requirement_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("agents/requirement_manager/models/requirement.py").read_text()
    repository_source = Path("agents/requirement_manager/db/repository.py").read_text()
    port_source = Path("agents/requirement_manager/core/outbox_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/outbox_store.py").read_text()
    service_source = Path("agents/requirement_manager/service/agent.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "requirement_event_outbox"' in migration_source
    assert "class RequirementEventOutbox" in model_source
    assert "class RequirementEventOutboxRepository" in repository_source
    assert "class RequirementEventOutboxStore" in port_source
    assert "SqlAlchemyRequirementEventOutboxStore" in adapter_source
    assert "await self._stage_requirement_event(session, event)" in service_source
    assert "RequirementEventOutboxRepository" not in service_source
    assert "await self._commit_requirement_mutation" in service_source
    assert "await self._publish_staged_requirement_event" in service_source
    assert "publish_pending_requirement_events" in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "`requirement_event_outbox`" in doc_source
    _assert_documented_outbox_delivery_gap(doc_source)

    app_source = Path("agents/requirement_manager/app/main.py").read_text()
    plugin_source = Path(
        "agents/requirement_manager/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "RequirementOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_requirement_events" in plugin_source


def test_pjm_decomposition_api_events_have_durable_outbox_contract() -> None:
    """PJM decomposition API events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260508_pjm_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("agents/pjm_agent/models/pm.py").read_text()
    repository_source = Path("agents/pjm_agent/db/repository.py").read_text()
    alert_port_source = Path("agents/pjm_agent/core/alert_ports.py").read_text()
    alert_store_source = Path("agents/pjm_agent/db/alert_log_store.py").read_text()
    decomposition_port_source = Path("agents/pjm_agent/core/decomposition_ports.py").read_text()
    decomposition_store_source = Path("agents/pjm_agent/db/decomposition_store.py").read_text()
    outbox_port_source = Path("agents/pjm_agent/core/outbox_ports.py").read_text()
    outbox_store_source = Path("agents/pjm_agent/db/outbox_store.py").read_text()
    orchestrator_source = Path("agents/pjm_agent/core/decomposition_orchestrator.py").read_text()
    event_use_case_source = Path("agents/pjm_agent/core/event_use_cases.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "pjm_agent_event_outbox"' in migration_source
    assert "class PJMEventOutbox" in model_source
    assert "class PJMEventOutboxRepository" in repository_source
    assert "class PJMAlertLogStore(Protocol)" in alert_port_source
    assert "class SqlAlchemyPJMAlertLogStore" in alert_store_source
    assert "class PJMDecompositionStore(Protocol)" in decomposition_port_source
    assert "class SqlAlchemyPJMDecompositionStore" in decomposition_store_source
    assert "class PJMEventOutboxStore(Protocol)" in outbox_port_source
    assert "class SqlAlchemyPJMEventOutboxStore" in outbox_store_source
    assert "from ..db." not in orchestrator_source
    assert "DecompositionRepository" not in orchestrator_source
    assert "DatabaseManager" not in orchestrator_source
    assert "PJMEventOutboxRepository" not in orchestrator_source
    assert "await self._stage_pjm_event(decomposition, completion_event)" in orchestrator_source
    assert "await self._publish_staged_pjm_event" in orchestrator_source
    assert "publish_event_via_outbox" in orchestrator_source
    assert "publish_pending_pjm_events" in orchestrator_source
    assert "shared.infra.event_bus" not in orchestrator_source
    assert "self._event_bus.publish(" not in orchestrator_source
    service_source = Path("agents/pjm_agent/service/agent.py").read_text()
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "SqlAlchemyPJMDecompositionStore(" in service_source
    assert "SqlAlchemyPJMEventOutboxStore(self._db_manager)" in service_source
    assert "SqlAlchemyPJMAlertLogStore(self._db_manager)" in service_source
    assert "DecompositionRepository" not in service_source
    assert "AlertLogRepository" not in service_source
    assert "self._decomposition_store.list_stale_pending" in service_source
    assert "self._alert_log_store.record_alerts" in event_use_case_source
    assert "await self._decomposition.publish_event_via_outbox(failure_event)" in (
        event_use_case_source
    )
    assert "await self._publish_pjm_event_via_outbox(timeout_event)" in service_source
    assert "self._event_bus.publish(" not in service_source
    assert "self._event_bus.publish(" not in event_use_case_source
    assert "`pjm_agent_event_outbox`" in doc_source
    _assert_documented_outbox_delivery_gap(doc_source)

    app_source = Path("agents/pjm_agent/app/main.py").read_text()
    plugin_source = Path("agents/pjm_agent/app/plugins/outbox_dispatcher.py").read_text()
    assert "PJMOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_pjm_events" in plugin_source


def test_coordinator_service_uses_state_store_port() -> None:
    """Coordinator orchestration should depend on a state-store port."""
    service_source = Path("services/orchestration/coordinator/service/agent.py").read_text()
    port_source = Path(
        "services/orchestration/coordinator/core/state_ports.py"
    ).read_text()

    assert "class CoordinatorStateStorePort(Protocol)" in port_source
    assert "state_store: CoordinatorStateStorePort | None = None" in service_source
    assert "self._state_store: CoordinatorStateStorePort" in service_source
    assert "CoordinatorStateStore()" in service_source


def test_coordinator_event_orchestration_delegates_to_application_use_case() -> None:
    """Coordinator service shell should not own event orchestration workflow."""
    service_source = Path("services/orchestration/coordinator/service/agent.py").read_text()
    use_case_source = Path(
        "services/orchestration/coordinator/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class CoordinatorEventUseCase" in use_case_source
    assert "class CoordinatorScratchpadPort(Protocol)" in use_case_source
    assert "CoordinatorThinker" in use_case_source
    assert "classify_event(event)" in use_case_source
    assert 'classified.kind == "progress"' in use_case_source
    assert "update_agent_state(" in use_case_source
    assert "read_incremental()" in use_case_source
    assert "get_agent_states()" in use_case_source
    assert "get_pending_decisions()" in use_case_source
    assert "decision_to_event(decision)" in use_case_source
    assert "state_store.persist(decisions)" in use_case_source
    assert "asyncio.create_task" in use_case_source

    assert "CoordinatorEventUseCase" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "classify_event(event)" not in handle_source
    assert "update_agent_state(" not in handle_source
    assert "read_incremental()" not in handle_source
    assert "decision_to_event" not in handle_source
    assert "state_store.persist" not in handle_source


def test_dev_result_collection_events_have_durable_outbox_contract() -> None:
    """Dev result-collection events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260512_dev_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("agents/dev_agent/models/dev.py").read_text()
    repository_source = Path("agents/dev_agent/db/repository.py").read_text()
    port_source = Path("agents/dev_agent/core/outbox_ports.py").read_text()
    adapter_source = Path("agents/dev_agent/db/outbox_store.py").read_text()
    workflow_log_adapter_source = Path("agents/dev_agent/db/workflow_log_store.py").read_text()
    service_source = Path("agents/dev_agent/service/agent.py").read_text()
    app_source = Path("agents/dev_agent/app/main.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "dev_agent_event_outbox"' in migration_source
    assert "class DevAgentEventOutbox" in model_source
    assert "class DevEventOutboxRepository" in repository_source
    assert "class DevEventOutboxStore" in port_source
    assert "SqlAlchemyDevEventOutboxStore" in adapter_source
    assert "SqlAlchemyDevWorkflowLogStore" in workflow_log_adapter_source
    assert "DevWorkflowLogRepository" in workflow_log_adapter_source
    assert "from ..db.repository import DevWorkflowLogRepository" not in service_source
    assert "DevWorkflowLogRepository(session)" not in service_source
    assert "self._get_log_repo(session)" in service_source
    assert "publish_pending_dev_events" in service_source
    assert "publish_staged_dev_events" in service_source
    assert "DevEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "SqlAlchemyDevEventOutboxSessionStore" in adapter_source
    assert "DevEventOutboxRepository(session)" not in app_source
    assert "SqlAlchemyDevEventOutboxSessionStore(" in app_source
    assert "await outbox.add(evt)" in app_source
    assert "await agent.publish_staged_dev_events(staged_events)" in app_source
    assert "event_bus.publish" not in app_source
    assert "`dev_agent_event_outbox`" in doc_source
    assert "`dev_agent_event_outbox`" in event_catalog_source

    plugin_source = Path("agents/dev_agent/app/plugins/outbox_dispatcher.py").read_text()
    assert "DevOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_dev_events" in plugin_source


def test_channel_gateway_events_have_durable_outbox_contract() -> None:
    """Channel gateway produced events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260513_channel_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("services/gateways/channel/models/event_outbox.py").read_text()
    repository_source = Path("services/gateways/channel/db/repository.py").read_text()
    port_source = Path("services/gateways/channel/core/outbox_ports.py").read_text()
    adapter_source = Path("services/gateways/channel/db/outbox_store.py").read_text()
    service_source = Path("services/gateways/channel/service/agent.py").read_text()
    app_source = Path("services/gateways/channel/app/main.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "channel_gateway_event_outbox"' in migration_source
    assert "class ChannelGatewayEventOutbox" in model_source
    assert "class ChannelGatewayEventOutboxRepository" in repository_source
    assert "class ChannelGatewayEventOutboxStore" in port_source
    assert "SqlAlchemyChannelGatewayEventOutboxStore" in adapter_source
    assert "publish_pending_channel_events" in service_source
    assert "publish_channel_event_via_outbox" in service_source
    assert "await self.publish_channel_event_via_outbox(e)" in service_source
    assert "ChannelGatewayEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "await self._event_bus.publish(e)" not in service_source
    assert "MessageInboundPayload" not in service_source
    assert "AdapterStatusPayload" not in service_source
    assert "`channel_gateway_event_outbox`" in doc_source
    assert "`channel_gateway_event_outbox`" in event_catalog_source

    plugin_source = Path(
        "services/gateways/channel/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "ChannelOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_channel_events" in plugin_source


def test_channel_gateway_event_orchestration_delegates_to_application_use_case() -> None:
    """Channel gateway service shell should not own outbound delivery branching."""
    service_source = Path("services/gateways/channel/service/agent.py").read_text()
    use_case_source = Path(
        "services/gateways/channel/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class ChannelAdapterPort(Protocol)" in use_case_source
    assert "class ChannelAdapterRegistryPort(Protocol)" in use_case_source
    assert "class ChannelGatewayEventUseCase" in use_case_source
    assert "MessageOutboundPayload.model_validate" in use_case_source
    assert "MessageDeliveredPayload" in use_case_source
    assert "DeliveryResult(" in use_case_source
    assert "adapter.send_message(message)" in use_case_source

    assert "service.event_handlers" not in service_source
    assert "dispatch_event" not in service_source
    assert "ChannelGatewayEventUseCase" in service_source
    assert "channel_event_use_case().handle_event(event)" in handle_source
    assert "_adapter_registry.get" not in handle_source
    assert "MessageOutboundPayload" not in service_source


def test_channel_gateway_lifecycle_delegates_to_application_use_case() -> None:
    """Channel gateway service shell should not own adapter lifecycle payloads."""
    service_source = Path("services/gateways/channel/service/agent.py").read_text()
    use_case_source = Path(
        "services/gateways/channel/core/lifecycle_use_cases.py"
    ).read_text()

    assert "class ChannelGatewayLifecycleUseCase" in use_case_source
    assert "class ChannelLifecycleAdapterPort(Protocol)" in use_case_source
    assert "class ChannelLifecycleAdapterRegistryPort(Protocol)" in use_case_source
    assert "class ChannelLifecyclePublisherPort(Protocol)" in use_case_source
    assert "MessageInboundPayload(message=message)" in use_case_source
    assert "AdapterStatusPayload(" in use_case_source
    assert "ChannelEventTypes.MESSAGE_INBOUND" in use_case_source
    assert "ChannelEventTypes.ADAPTER_STATUS" in use_case_source
    assert "publish_channel_event_via_outbox(event)" in use_case_source
    assert "adapter.connect()" in use_case_source
    assert "adapter.disconnect()" in use_case_source
    assert "adapter.listen()" in use_case_source

    assert "ChannelGatewayLifecycleUseCase" in service_source
    assert "def channel_lifecycle_use_case" in service_source
    assert (
        "await self.channel_lifecycle_use_case().connect_adapters()"
        in _function_source(service_source, "_connect_adapters")
    )
    assert "MessageInboundPayload" not in service_source
    assert "AdapterStatusPayload" not in service_source
    assert "payload.model_dump(mode=\"json\")" not in service_source


def test_analysis_events_have_durable_outbox_contract() -> None:
    """Analysis report/risk/quality events must be staged before publish."""
    migration_path = Path("migrations/versions/20260514_analysis_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("shared/capabilities/analysis/models/event_outbox.py").read_text()
    repository_source = Path("shared/capabilities/analysis/db/repository.py").read_text()
    adapter_source = Path("shared/capabilities/analysis/db/outbox_store.py").read_text()
    port_source = Path("shared/capabilities/analysis/core/outbox_ports.py").read_text()
    service_source = Path("shared/capabilities/analysis/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/analysis/core/outbox_delivery_use_cases.py"
    ).read_text()
    app_source = Path("shared/capabilities/analysis/app/main.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "analysis_agent_event_outbox"' in migration_source
    assert "class AnalysisEventOutbox" in model_source
    assert "class AnalysisEventOutboxRepository" in repository_source
    assert "class AnalysisEventOutboxStore" in port_source
    assert "SqlAlchemyAnalysisEventOutboxStore" in adapter_source
    assert "publish_pending_analysis_events" in service_source
    assert "publish_event_via_outbox" in service_source
    assert "await self._event_publisher.publish(event)" in use_case_source
    assert "publish_staged_event(event)" in service_source
    assert "AnalysisEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" not in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "`analysis_agent_event_outbox`" in doc_source
    assert "`analysis_agent_event_outbox`" in event_catalog_source

    plugin_source = Path(
        "shared/capabilities/analysis/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "AnalysisOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_analysis_events" in plugin_source


def test_coordinator_events_have_durable_outbox_contract() -> None:
    """Coordinator dispatch and handoff events must be staged before publish."""
    migration_path = Path("migrations/versions/20260515_coordinator_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path(
        "services/orchestration/coordinator/db/event_outbox.py"
    ).read_text()
    repository_source = Path(
        "services/orchestration/coordinator/db/repository.py"
    ).read_text()
    port_source = Path(
        "services/orchestration/coordinator/core/outbox_ports.py"
    ).read_text()
    adapter_source = Path(
        "services/orchestration/coordinator/db/outbox_store.py"
    ).read_text()
    service_source = Path("services/orchestration/coordinator/service/agent.py").read_text()
    app_source = Path("services/orchestration/coordinator/app/main.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "coordinator_event_outbox"' in migration_source
    assert "class CoordinatorEventOutbox" in model_source
    assert "class CoordinatorEventOutboxRepository" in repository_source
    assert "class CoordinatorEventOutboxStore" in port_source
    assert "SqlAlchemyCoordinatorEventOutboxStore" in adapter_source
    assert "publish_pending_coordinator_events" in service_source
    assert "publish_event_via_outbox" in service_source
    assert "await self._publish_staged_coordinator_event(event)" in service_source
    assert "CoordinatorEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "`coordinator_event_outbox`" in doc_source
    assert "`coordinator_event_outbox`" in event_catalog_source

    plugin_source = Path(
        "services/orchestration/coordinator/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "CoordinatorOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_coordinator_events" in plugin_source


def test_evolution_events_have_durable_outbox_contract() -> None:
    """Evolution proposal events must be staged before publish."""
    migration_path = Path("migrations/versions/20260516_evolution_event_outbox.py")
    migration_source = migration_path.read_text()
    table_source = Path("shared/evolution/db/tables.py").read_text()
    repository_source = Path("shared/evolution/db/repository.py").read_text()
    port_source = Path("shared/capabilities/evolution/core/outbox_ports.py").read_text()
    adapter_source = Path("shared/capabilities/evolution/db/outbox_store.py").read_text()
    service_source = Path("shared/capabilities/evolution/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/outbox_delivery_use_cases.py"
    ).read_text()
    app_source = Path("shared/capabilities/evolution/app/main.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "evolution_event_outbox"' in migration_source
    assert "class EvolutionEventOutbox" in table_source
    assert "class EvolutionEventOutboxRepository" in repository_source
    assert "class EvolutionEventOutboxStore" in port_source
    assert "SqlAlchemyEvolutionEventOutboxStore" in adapter_source
    assert "publish_pending_evolution_events" in service_source
    assert "publish_event_via_outbox" in service_source
    assert "publish_staged_event(event)" in service_source
    assert "EvolutionEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in use_case_source
    assert "await self._event_publisher.publish(event)" not in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "`evolution_event_outbox`" in doc_source
    assert "`evolution_event_outbox`" in event_catalog_source

    plugin_source = Path(
        "shared/capabilities/evolution/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "EvolutionOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_evolution_events" in plugin_source


def test_evolution_global_analyzer_uses_trace_analysis_store_port() -> None:
    """Global analysis should depend on a read-side port, not DB sessions."""
    analyzer_source = Path(
        "shared/capabilities/evolution/service/global_analyzer.py"
    ).read_text()
    service_source = Path("shared/capabilities/evolution/service/agent.py").read_text()
    port_source = Path(
        "shared/capabilities/evolution/core/analysis_ports.py"
    ).read_text()
    adapter_source = Path(
        "shared/capabilities/evolution/db/trace_analysis_store.py"
    ).read_text()

    assert "class EvolutionTraceAnalysisStore" in port_source
    assert "class AgentPerformanceSnapshot" in port_source
    assert "SqlAlchemyEvolutionTraceAnalysisStore" in adapter_source
    assert "EvolutionRepository" in adapter_source
    assert "EvolutionRepository" not in analyzer_source
    assert "db_manager" not in analyzer_source
    assert "EvolutionTraceAnalysisStore" in analyzer_source
    assert "trace_analysis_store" in service_source
    assert "SqlAlchemyEvolutionTraceAnalysisStore(self._db_manager)" in service_source
    assert "analyze(self._db_manager" not in service_source


def test_evolution_seed_bootstrap_uses_skill_seed_store_port() -> None:
    """Evolution startup should delegate seed persistence to a DB adapter."""
    service_source = Path("shared/capabilities/evolution/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/seed_bootstrap_use_cases.py"
    ).read_text()
    port_source = Path(
        "shared/capabilities/evolution/core/seed_ports.py"
    ).read_text()
    adapter_source = Path(
        "shared/capabilities/evolution/db/skill_seed_store.py"
    ).read_text()

    assert "class EvolutionSkillSeedStore" in port_source
    assert "SqlAlchemyEvolutionSkillSeedStore" in adapter_source
    assert "EvolutionRepository" in adapter_source
    assert "from shared.evolution.db.repository import EvolutionRepository" not in service_source
    assert "class EvolutionSeedBootstrapUseCase" in use_case_source
    assert "default_evolution_skill_seeds" in use_case_source
    assert "seed_missing_active_skills" in use_case_source
    assert "skill_seed_bootstrap_failed" in use_case_source
    assert "seed_store" in service_source
    assert "SqlAlchemyEvolutionSkillSeedStore(self._db_manager)" in service_source
    assert "def _seed_bootstrap_use_case" in service_source
    assert "return await self._seed_bootstrap_use_case().bootstrap()" in service_source
    assert "seed_missing_active_skills" not in service_source
    assert "shared.evolution.seeds" not in service_source


def test_evolution_health_check_uses_health_store_port() -> None:
    """Evolution readiness should delegate database probing to an adapter."""
    service_source = Path("shared/capabilities/evolution/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/health_use_cases.py"
    ).read_text()
    port_source = Path(
        "shared/capabilities/evolution/core/health_ports.py"
    ).read_text()
    adapter_source = Path(
        "shared/capabilities/evolution/db/health_store.py"
    ).read_text()

    assert "class EvolutionHealthStore" in port_source
    assert "SqlAlchemyEvolutionHealthStore" in adapter_source
    assert "text(\"SELECT 1\")" in adapter_source
    assert "class EvolutionHealthUseCase" in use_case_source
    assert "class EvolutionEventBusHealthPort(Protocol)" in use_case_source
    assert "await self._health_store.is_database_ready()" in use_case_source
    assert "collaboration_approval_gateway" in use_case_source
    assert "from sqlalchemy import text" not in service_source
    assert "text(\"SELECT 1\")" not in service_source
    assert "health_store" in service_source
    assert "SqlAlchemyEvolutionHealthStore(self._db_manager)" in service_source
    assert "def _health_use_case" in service_source
    assert "return await self._health_use_case().check()" in service_source
    assert "is_database_ready" not in service_source
    assert "collaboration_approval_gateway" not in service_source


def test_analysis_and_sync_health_checks_use_health_store_ports() -> None:
    """Analysis and Sync readiness should delegate database probing to adapters."""
    analysis_service = Path("shared/capabilities/analysis/service/agent.py").read_text()
    analysis_port = Path("shared/capabilities/analysis/core/health_ports.py").read_text()
    analysis_use_case = Path(
        "shared/capabilities/analysis/core/health_use_cases.py"
    ).read_text()
    analysis_adapter = Path("shared/capabilities/analysis/db/health_store.py").read_text()
    sync_service = Path("shared/capabilities/sync/service/agent.py").read_text()
    sync_port = Path("shared/capabilities/sync/core/health_ports.py").read_text()
    sync_use_case = Path(
        "shared/capabilities/sync/core/health_use_cases.py"
    ).read_text()
    sync_adapter = Path("shared/capabilities/sync/db/health_store.py").read_text()

    assert "class AnalysisHealthStore(Protocol)" in analysis_port
    assert "SqlAlchemyAnalysisHealthStore" in analysis_adapter
    assert "text(\"SELECT 1\")" in analysis_adapter
    assert "class AnalysisHealthUseCase" in analysis_use_case
    assert "await self._health_store.is_database_ready()" in analysis_use_case
    assert '"event_bus": self._event_bus is not None' in analysis_use_case
    assert "from sqlalchemy import text" not in analysis_service
    assert "text(\"SELECT 1\")" not in analysis_service
    assert "health_store" in analysis_service
    assert "SqlAlchemyAnalysisHealthStore(" in analysis_service
    assert "def _health_use_case" in analysis_service
    assert "return await self._health_use_case().check()" in analysis_service
    assert "is_database_ready" not in analysis_service

    assert "class SyncHealthStore(Protocol)" in sync_port
    assert "SqlAlchemySyncHealthStore" in sync_adapter
    assert "text(\"SELECT 1\")" in sync_adapter
    assert "class SyncHealthUseCase" in sync_use_case
    assert "await self._health_store.is_database_ready()" in sync_use_case
    assert "from sqlalchemy import text" not in sync_service
    assert "text(\"SELECT 1\")" not in sync_service
    assert "health_store" in sync_service
    assert "SqlAlchemySyncHealthStore(" in sync_service
    assert "def _health_use_case" in sync_service
    assert "return await self._health_use_case().check()" in sync_service
    assert "is_database_ready" not in sync_service


def test_qa_and_pjm_health_checks_use_health_store_ports() -> None:
    """QA and PJM readiness should delegate database probing to adapters."""
    qa_service = Path("agents/qa_agent/service/agent.py").read_text()
    qa_port = Path("agents/qa_agent/core/health_ports.py").read_text()
    qa_use_case = Path("agents/qa_agent/core/health_use_cases.py").read_text()
    qa_adapter = Path("agents/qa_agent/db/health_store.py").read_text()
    pjm_service = Path("agents/pjm_agent/service/agent.py").read_text()
    pjm_port = Path("agents/pjm_agent/core/health_ports.py").read_text()
    pjm_use_case = Path("agents/pjm_agent/core/health_use_cases.py").read_text()
    pjm_adapter = Path("agents/pjm_agent/db/health_store.py").read_text()

    assert "class QAHealthStore(Protocol)" in qa_port
    assert "SqlAlchemyQAHealthStore" in qa_adapter
    assert "text(\"SELECT 1\")" in qa_adapter
    assert "class QAHealthUseCase" in qa_use_case
    assert "await self._health_store.is_database_ready()" in qa_use_case
    assert "from sqlalchemy import text" not in qa_service
    assert "text(\"SELECT 1\")" not in qa_service
    assert "health_store" in qa_service
    assert "SqlAlchemyQAHealthStore(" in qa_service
    assert "def _health_use_case" in qa_service
    assert "return await self._health_use_case().check()" in qa_service
    assert "is_database_ready" not in qa_service

    assert "class PJMHealthStore(Protocol)" in pjm_port
    assert "SqlAlchemyPJMHealthStore" in pjm_adapter
    assert "text(\"SELECT 1\")" in pjm_adapter
    assert "class PJMHealthUseCase" in pjm_use_case
    assert "await self._health_store.is_database_ready()" in pjm_use_case
    assert "def _config_has_members" in pjm_use_case
    assert "from sqlalchemy import text" not in pjm_service
    assert "text(\"SELECT 1\")" not in pjm_service
    assert "health_store" in pjm_service
    assert "SqlAlchemyPJMHealthStore(" in pjm_service
    assert "def _health_use_case" in pjm_service
    assert "return await self._health_use_case().check()" in pjm_service
    assert "is_database_ready" not in pjm_service
    assert "len(self._config.members)" not in pjm_service


def test_requirement_and_user_interaction_health_checks_use_health_store_ports() -> None:
    """Requirement and User Interaction readiness should use health-store ports."""
    req_service = Path("agents/requirement_manager/service/agent.py").read_text()
    req_port = Path("agents/requirement_manager/core/health_ports.py").read_text()
    req_use_case = Path(
        "agents/requirement_manager/core/health_use_cases.py"
    ).read_text()
    req_adapter = Path("agents/requirement_manager/db/health_store.py").read_text()
    chat_service = Path("services/gateways/user_interaction/service/agent.py").read_text()
    chat_port = Path("services/gateways/user_interaction/core/health_ports.py").read_text()
    chat_use_case = Path(
        "services/gateways/user_interaction/core/health_use_cases.py"
    ).read_text()
    chat_adapter = Path("services/gateways/user_interaction/db/health_store.py").read_text()

    assert "class RequirementHealthStore(Protocol)" in req_port
    assert "SqlAlchemyRequirementHealthStore" in req_adapter
    assert "text(\"SELECT 1\")" in req_adapter
    assert "class RequirementHealthUseCase" in req_use_case
    assert "class RequirementEventBusHealthPort(Protocol)" in req_use_case
    assert "await self._health_store.is_database_ready()" in req_use_case
    assert '"event_bus": bool(getattr(self._event_bus, "is_connected", False))' in (
        req_use_case
    )
    assert '"messenger": self._messenger is not None' in req_use_case
    assert '"card_renderer": self._card_renderer is not None' in req_use_case
    assert "from sqlalchemy import text" not in req_service
    assert "text(\"SELECT 1\")" not in req_service
    assert "health_store" in req_service
    assert "SqlAlchemyRequirementHealthStore(" in req_service
    assert "def _health_use_case" in req_service
    assert "return await self._health_use_case().check()" in req_service
    assert "is_database_ready" not in req_service

    assert "class UserInteractionHealthStore(Protocol)" in chat_port
    assert "SqlAlchemyUserInteractionHealthStore" in chat_adapter
    assert "text(\"SELECT 1\")" in chat_adapter
    assert "class UserInteractionHealthUseCase" in chat_use_case
    assert "await self._health_store.is_database_ready()" in chat_use_case
    assert '"chat_service": self._chat_service is not None' in chat_use_case
    assert "from sqlalchemy import text" not in chat_service
    assert "text(\"SELECT 1\")" not in chat_service
    assert "health_store" in chat_service
    assert "SqlAlchemyUserInteractionHealthStore(" in chat_service
    assert "def _health_use_case" in chat_service
    assert "return await self._health_use_case().check()" in chat_service
    assert "is_database_ready" not in chat_service


def test_requirement_grpc_servicer_uses_store_ports() -> None:
    """The gRPC boundary should not construct repositories or raw DB probes."""
    servicer_source = Path("agents/requirement_manager/grpc/servicer.py").read_text()
    server_source = Path("agents/requirement_manager/grpc/server.py").read_text()
    port_source = Path("agents/requirement_manager/core/grpc_ports.py").read_text()
    adapter_source = Path("agents/requirement_manager/db/grpc_store.py").read_text()

    assert "class RequirementGrpcStore(Protocol)" in port_source
    assert "SqlAlchemyRequirementGrpcStore" in adapter_source
    assert "RequirementRepository" in adapter_source
    assert "RequirementRepository" not in servicer_source
    assert "from sqlalchemy import text" not in servicer_source
    assert "text(\"SELECT 1\")" not in servicer_source
    assert "RequirementGrpcStore" in servicer_source
    assert "RequirementHealthStore" in servicer_source
    assert "self._requirements" in servicer_source
    assert "self._health_store" in servicer_source
    assert "requirement_store" in server_source
    assert "health_store" in server_source


def test_dev_and_coordinator_health_checks_use_health_store_ports() -> None:
    """Dev and Coordinator readiness should delegate database probing to adapters."""
    dev_service = Path("agents/dev_agent/service/agent.py").read_text()
    dev_port = Path("agents/dev_agent/core/health_ports.py").read_text()
    dev_adapter = Path("agents/dev_agent/db/health_store.py").read_text()
    coordinator_service = Path(
        "services/orchestration/coordinator/service/agent.py"
    ).read_text()
    coordinator_port = Path(
        "services/orchestration/coordinator/core/health_ports.py"
    ).read_text()
    coordinator_adapter = Path(
        "services/orchestration/coordinator/db/health_store.py"
    ).read_text()

    assert "class DevHealthStore(Protocol)" in dev_port
    assert "SqlAlchemyDevHealthStore" in dev_adapter
    assert "text(\"SELECT 1\")" in dev_adapter
    assert "from sqlalchemy import text" not in dev_service
    assert "text(\"SELECT 1\")" not in dev_service
    assert "health_store" in dev_service
    assert "SqlAlchemyDevHealthStore(self._db_manager)" in dev_service
    assert "is_database_ready" in dev_service

    assert "class CoordinatorHealthStore(Protocol)" in coordinator_port
    assert "SqlAlchemyCoordinatorHealthStore" in coordinator_adapter
    assert "text(\"SELECT 1\")" in coordinator_adapter
    assert "from sqlalchemy import text" not in coordinator_service
    assert "text(\"SELECT 1\")" not in coordinator_service
    assert "health_store" in coordinator_service
    assert "SqlAlchemyCoordinatorHealthStore(self._db_manager)" in coordinator_service
    assert "is_database_ready" in coordinator_service


def test_evolution_control_plane_records_use_proposal_store_port() -> None:
    """Evolution service should not depend on the control-plane repository directly."""
    service_source = Path("shared/capabilities/evolution/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/evolution/core/proposal_approval_use_cases.py"
    ).read_text()
    port_source = Path(
        "shared/capabilities/evolution/core/control_plane_ports.py"
    ).read_text()
    adapter_source = Path(
        "shared/capabilities/evolution/db/control_plane_store.py"
    ).read_text()

    assert "class EvolutionControlPlaneProposalStore(Protocol)" in port_source
    assert "SqlAlchemyEvolutionControlPlaneProposalStore" in adapter_source
    assert "SqlAlchemyControlPlaneEvolutionProposalStore" in adapter_source
    assert "record_evolution_proposal_with_audit" in adapter_source
    assert "ensure_evolution_proposal_company" in adapter_source
    assert "ControlPlaneRepository" not in adapter_source
    assert "CompanyContext" not in adapter_source
    assert "EvolutionProposal(" not in adapter_source
    assert "AuditEvent" not in adapter_source
    assert "EventTypes" not in adapter_source
    assert "ControlPlaneRepository" not in service_source
    assert "CompanyContext" not in service_source
    assert "EvolutionProposal(" not in service_source
    assert "AuditEvent" not in service_source
    assert "EvolutionProposalApprovalUseCase" in service_source
    assert "_get_control_plane_proposal_store" in service_source
    assert "record_proposal(" not in service_source
    assert "ensure_company(" not in service_source
    assert "record_proposal(" in use_case_source
    assert "ensure_company(" in use_case_source
    assert "control_plane_db_manager" not in service_source
    assert "default_control_plane_session_provider" in adapter_source


def test_qa_acceptance_events_have_durable_outbox_contract() -> None:
    """QA acceptance events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260509_qa_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("agents/qa_agent/models/qa.py").read_text()
    repository_source = Path("agents/qa_agent/db/repository.py").read_text()
    port_source = Path("agents/qa_agent/core/outbox_ports.py").read_text()
    adapter_source = Path("agents/qa_agent/db/outbox_store.py").read_text()
    report_port_source = Path("agents/qa_agent/core/report_store.py").read_text()
    report_adapter_source = Path("agents/qa_agent/db/report_store.py").read_text()
    run_port_source = Path("agents/qa_agent/core/run_store.py").read_text()
    run_adapter_source = Path("agents/qa_agent/db/run_store.py").read_text()
    service_source = Path("agents/qa_agent/service/agent.py").read_text()
    execution_use_case_source = Path(
        "agents/qa_agent/core/acceptance_execution_use_cases.py"
    ).read_text()
    notifier_source = Path("agents/qa_agent/core/notifier.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "qa_agent_event_outbox"' in migration_source
    assert "class QAEventOutbox" in model_source
    assert "class QAEventOutboxRepository" in repository_source
    assert "class QAEventOutboxStore" in port_source
    assert "SqlAlchemyQAEventOutboxStore" in adapter_source
    assert "class QAReportStore(Protocol)" in report_port_source
    assert "AcceptanceRunRepository" not in report_port_source
    assert "AcceptanceResultRepository" not in report_port_source
    assert "SqlAlchemyQAReportStore" in report_adapter_source
    assert "from ..db.report_store import SqlAlchemyQAReportStore as QAReportStore" in service_source
    assert "class QAAcceptanceRunStore(Protocol)" in run_port_source
    assert "AcceptanceRunRepository" not in run_port_source
    assert "SqlAlchemyQAAcceptanceRunStore" in run_adapter_source
    assert "AcceptanceRunRepository" not in service_source
    assert "self._run_store.list_runs" in service_source
    assert "self._run_store.get_by_id" in service_source
    assert "self._run_store.get_by_trigger_event_id" in execution_use_case_source
    assert "await self._stage_event(session, event)" in execution_use_case_source
    assert "QAEventOutboxRepository" not in service_source
    assert "await self._publish_staged_qa_events" in service_source
    assert "publish_pending_qa_events" in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "eventbus_summary" in notifier_source
    assert "`qa_agent_event_outbox`" in doc_source
    _assert_documented_outbox_delivery_gap(doc_source)

    app_source = Path("agents/qa_agent/app/main.py").read_text()
    plugin_source = Path("agents/qa_agent/app/plugins/outbox_dispatcher.py").read_text()
    assert "QAOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_qa_events" in plugin_source


def test_sync_events_have_durable_outbox_contract() -> None:
    """Sync lifecycle and handoff events must be staged before external publish."""
    migration_path = Path("migrations/versions/20260510_sync_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path("shared/capabilities/sync/models/sync.py").read_text()
    repository_source = Path("shared/capabilities/sync/db/repository.py").read_text()
    service_source = Path("shared/capabilities/sync/service/agent.py").read_text()
    use_case_source = Path(
        "shared/capabilities/sync/core/scope_execution_use_cases.py"
    ).read_text()
    openproject_source = Path("shared/capabilities/sync/core/openproject_sync.py").read_text()
    engine_source = Path("shared/capabilities/sync/core/engine.py").read_text()
    port_source = Path("shared/capabilities/sync/core/sync_ports.py").read_text()
    adapter_source = Path("shared/capabilities/sync/db/sync_stores.py").read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "sync_agent_event_outbox"' in migration_source
    assert "class SyncEventOutbox" in model_source
    assert "class SyncEventOutboxRepository" in repository_source
    assert "class SyncEventOutboxStore" in port_source
    assert "SqlAlchemySyncEventOutboxStore" in adapter_source
    assert "await self._event_publisher.publish_sync_event_via_outbox(event)" in (
        use_case_source
    )
    assert "async def publish_sync_event_via_outbox" in service_source
    assert "publish_pending_sync_events" in service_source
    assert "SyncEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "event_publisher=self._event_publisher" in service_source
    assert "await self._event_publisher.publish(event)" in service_source
    assert "await self._event_bus.publish(event)" not in service_source
    assert "await store.stage_event(decompose_event)" in openproject_source
    assert "await self._outbox_repo.add(event)" in adapter_source
    assert "await self._publish_staged_sync_event(event)" in openproject_source
    assert "shared.infra.event_bus" not in openproject_source
    assert "shared.infra.event_bus" not in engine_source
    assert "`sync_agent_event_outbox`" in doc_source
    assert "Sync lifecycle/decomposition handoff events" in doc_source

    app_source = Path("shared/capabilities/sync/app/main.py").read_text()
    plugin_source = Path("shared/capabilities/sync/app/plugins/outbox_dispatcher.py").read_text()
    assert "SyncOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_sync_events" in plugin_source


def test_user_interaction_sync_trigger_events_have_durable_outbox_contract() -> None:
    """Gateway sync trigger commands must be staged before external publish."""
    migration_path = Path("migrations/versions/20260511_user_interaction_event_outbox.py")
    migration_source = migration_path.read_text()
    model_source = Path(
        "services/gateways/user_interaction/models/event_outbox.py"
    ).read_text()
    repository_source = Path(
        "services/gateways/user_interaction/db/repository.py"
    ).read_text()
    port_source = Path(
        "services/gateways/user_interaction/core/event_ports.py"
    ).read_text()
    adapter_source = Path(
        "services/gateways/user_interaction/db/outbox_store.py"
    ).read_text()
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    tools_source = Path(
        "services/gateways/user_interaction/core/tools.py"
    ).read_text()
    doc_source = Path("docs/guides/backend-boundaries.md").read_text()
    event_catalog_source = Path("docs/guides/event-catalog.md").read_text()

    assert migration_path.exists()
    assert 'op.create_table(\n        "chat_agent_event_outbox"' in migration_source
    assert "class UserInteractionEventOutbox" in model_source
    assert "class UserInteractionEventOutboxRepository" in repository_source
    assert "class UserInteractionEventOutboxStore" in port_source
    assert "SqlAlchemyUserInteractionEventOutboxStore" in adapter_source
    assert "event_publisher: GatewayEventPublisherPort" in tools_source
    assert "await deps.event_publisher.publish_sync_trigger" in tools_source
    assert "EventTypes.SYNC_TRIGGER" in service_source
    assert "publish_pending_user_interaction_events" in service_source
    assert "_publish_gateway_event_via_outbox" in service_source
    assert "UserInteractionEventOutboxRepository" not in service_source
    assert "EventBusEventPublisher(self._event_bus)" in service_source
    assert "self._event_bus.publish(" not in service_source
    assert "`chat_agent_event_outbox`" in doc_source
    assert "`chat_agent_event_outbox`" in event_catalog_source
    assert "event_bus.publish" not in tools_source

    app_source = Path("services/gateways/user_interaction/app/main.py").read_text()
    plugin_source = Path(
        "services/gateways/user_interaction/app/plugins/outbox_dispatcher.py"
    ).read_text()
    assert "UserInteractionOutboxDispatcherPlugin()" in app_source
    assert "publish_pending_user_interaction_events" in plugin_source


def test_feishu_card_renderers_live_in_shared_integrations() -> None:
    """Old local Feishu card modules must stay compatibility-only shims."""
    shim_paths = [
        Path("agents/requirement_manager/adapters/feishu_cards.py"),
        Path("agents/requirement_manager/integrations/feishu/cards/requirement.py"),
        Path("agents/pjm_agent/adapters/feishu_cards.py"),
        Path("agents/qa_agent/adapters/feishu_cards.py"),
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


def test_business_layers_do_not_bind_feishu_card_implementations() -> None:
    """Business layers use card-renderer ports; only composition roots bind implementations."""
    roots = [
        Path("agents/requirement_manager/app"),
        Path("agents/requirement_manager/api"),
        Path("agents/requirement_manager/core"),
        Path("agents/requirement_manager/service"),
        Path("agents/pjm_agent/app"),
        Path("agents/pjm_agent/api"),
        Path("agents/pjm_agent/core"),
        Path("agents/pjm_agent/service"),
        Path("agents/qa_agent/app"),
        Path("agents/qa_agent/api"),
        Path("agents/qa_agent/core"),
        Path("agents/qa_agent/service"),
        Path("services/gateways/user_interaction/app"),
        Path("services/gateways/user_interaction/api"),
        Path("services/gateways/user_interaction/core"),
        Path("services/gateways/user_interaction/service"),
    ]
    composition_roots = {
        Path("agents/requirement_manager/app/main.py"),
        Path("services/gateways/user_interaction/app/main.py"),
        Path("services/gateways/user_interaction/service/agent.py"),
    }
    for root in roots:
        if not root.exists():
            continue
        for path in _python_files(root):
            if path in composition_roots:
                continue
            for module in _imported_modules(path):
                assert not module.startswith("shared.integrations.feishu.cards"), (
                    f"{path} imports {module}; business layers should inject "
                    "Feishu card renderers through local card-renderer ports"
                )


def test_qa_core_uses_card_renderer_port_for_feishu_payloads() -> None:
    """QA core must not construct concrete Feishu card payloads directly."""
    path = Path("agents/qa_agent/core/notifier.py")
    text = path.read_text()

    assert '"msg_type": "interactive"' not in text
    assert "shared.integrations.feishu" not in text
    assert "shared.infra.event_bus" not in text
    assert ".card_ports" in text


def test_user_interaction_routes_do_not_build_feishu_cards_directly() -> None:
    """Gateway route/core code should use a local card-renderer port."""
    roots = [
        Path("services/gateways/user_interaction/api"),
        Path("services/gateways/user_interaction/core"),
    ]
    for root in roots:
        for path in _python_files(root):
            for module in _imported_modules(path):
                assert not module.startswith("shared.integrations.feishu.cards"), (
                    f"{path} imports {module}; route/service layers should use "
                    "services.gateways.user_interaction.core.card_ports and "
                    "inject a concrete renderer from the app/service entry point"
                )
            text = path.read_text()
            assert "CardBuilder(" not in text, (
                f"{path} constructs Feishu cards directly; use "
                "the user-interaction card-renderer port"
            )


def test_user_interaction_schema_mutations_use_control_plane_approval() -> None:
    """Bitable schema mutations must not rely on ad hoc approval flags."""
    path = Path("services/gateways/user_interaction/core/tools.py")
    text = path.read_text()

    assert "approved_sensitive_actions" not in text
    assert "ensure_approved_for_sensitive_action" in text
    assert "control_plane_approval_id" in text


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


def test_agent_core_does_not_import_agent_local_adapters_directly() -> None:
    """Agent core depends on ports and injected collaborators, not adapters."""
    for agent_root in AGENT_ROOTS:
        root = Path("agents") / agent_root / "core"
        if not root.exists():
            continue
        for path in _python_files(root):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ""
                is_relative_adapter = node.level >= 1 and module.startswith("adapters")
                is_absolute_adapter = module.startswith(f"agents.{agent_root}.adapters")
                assert not (is_relative_adapter or is_absolute_adapter), (
                    f"{path} imports agent-local adapter module {module}; "
                    "inject a port or bind adapters from the service/app layer"
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


def test_user_interaction_daily_tasks_uses_injected_llm_and_progress_ports() -> None:
    core_source = Path("services/gateways/user_interaction/core/daily_tasks.py").read_text()
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    adapter_source = Path(
        "services/gateways/user_interaction/db/daily_progress_store.py"
    ).read_text()

    assert "from shared.infra.llm_gateway import llm_gateway" not in core_source
    assert "from ..db.database import db_manager" not in core_source
    assert "from ..db.repository import DailyProgressRepository" not in core_source
    assert "class DailyDispatchLLM" in core_source
    assert "class DailyProgressStore" in core_source
    assert "dispatch_llm=llm_gateway" in service_source
    assert "daily_progress_store = SqlAlchemyDailyProgressStore" in service_source
    assert "progress_store=daily_progress_store" in service_source
    assert "DailyProgressRepository" in adapter_source


def test_user_interaction_chat_service_uses_injected_persistence_ports() -> None:
    core_source = Path("services/gateways/user_interaction/core/chat_service.py").read_text()
    port_source = Path("services/gateways/user_interaction/core/chat_ports.py").read_text()
    request_use_case_source = Path(
        "services/gateways/user_interaction/core/request_use_cases.py"
    ).read_text()
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    adapter_source = Path("services/gateways/user_interaction/db/chat_store.py").read_text()

    assert "from ..db.database import db_manager" not in core_source
    assert "from ..db.repository import ConversationRepository" not in core_source
    assert "from ..db.repository import DailyProgressRepository" not in core_source
    assert "from shared.infra.llm_gateway import llm_gateway" not in core_source
    assert "class ChatHistoryStore" in port_source
    assert "delete_inactive" in port_source
    assert "class DailyProgressContextStore" in port_source
    assert "class ChatLLM" in port_source
    assert "llm=llm_gateway" in service_source
    assert "self._history_store = history_store or SqlAlchemyChatHistoryStore" in service_source
    assert "history_store=self._history_store" in service_source
    assert "ConversationRepository" not in service_source
    assert "self._history_store.delete_inactive" not in service_source
    assert "self._history_store.delete_inactive" in request_use_case_source
    assert "daily_progress_store=daily_progress_store" in service_source
    assert "ConversationRepository" in adapter_source


def test_user_interaction_agent_request_dispatch_delegates_to_application_use_case() -> None:
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "services/gateways/user_interaction/core/request_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_request")

    assert "class UserInteractionRequestUseCase" in use_case_source
    assert "class UserInteractionChatPort(Protocol)" in use_case_source
    assert "async def handle(" in use_case_source
    assert 'action == "chat"' in use_case_source
    assert 'action == "chat_user_assistant"' in use_case_source
    assert 'action == "cleanup_conversations"' in use_case_source
    assert "unknown_action_error()" in use_case_source

    assert "UserInteractionRequestUseCase" in service_source
    assert "return await self._request_use_case().handle(request)" in handle_source
    assert 'action == "chat"' not in handle_source
    assert "chat_with_user_assistant" not in handle_source
    assert "clear_history" not in handle_source
    assert "delete_inactive" not in handle_source
    assert "dispatch_morning_tasks()" not in handle_source
    assert "collect_evening_progress()" not in handle_source


def test_user_interaction_agent_event_dispatch_delegates_to_application_use_case() -> None:
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    use_case_source = Path(
        "services/gateways/user_interaction/core/event_use_cases.py"
    ).read_text()
    handle_source = _function_source(service_source, "handle_event")

    assert "class UserInteractionEventUseCase" in use_case_source
    assert "EventTypes.CHAT_PM_RESPONSE" in use_case_source
    assert "EventTypes.COORDINATOR_RESPONSE" in use_case_source
    assert "project_management_response_received" in use_case_source
    assert "coordinator_response_received" in use_case_source
    assert "hash_identifier(user_id)" in use_case_source

    assert "UserInteractionEventUseCase" in service_source
    assert "def _event_use_case" in service_source
    assert "return await self._event_use_case().handle(event)" in handle_source
    assert "EventTypes.CHAT_PM_RESPONSE" not in handle_source
    assert "EventTypes.COORDINATOR_RESPONSE" not in handle_source
    assert "project_management_response_received" not in service_source
    assert "coordinator_response_received" not in service_source


def test_user_interaction_ops_logger_uses_injected_store_port() -> None:
    core_source = Path("services/gateways/user_interaction/core/ops_logger.py").read_text()
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()
    app_source = Path("services/gateways/user_interaction/app/main.py").read_text()
    adapter_source = Path(
        "services/gateways/user_interaction/db/operation_log_store.py"
    ).read_text()

    assert "from ..db.database import db_manager" not in core_source
    assert "from ..db.repository import CardOperationRepository" not in core_source
    assert "class CardOperationLogStore" in core_source
    assert "configure_operation_log_store" in service_source
    assert "configure_operation_log_store" in app_source
    assert "CardOperationRepository" in adapter_source


def test_user_interaction_tools_use_injected_persistence_ports() -> None:
    tools_source = Path("services/gateways/user_interaction/core/tools.py").read_text()
    service_source = Path(
        "services/gateways/user_interaction/service/agent.py"
    ).read_text()

    assert "from ..db.database import db_manager" not in tools_source
    assert "from ..db.repository import CardOperationRepository" not in tools_source
    assert "from ..db.repository import DailyProgressRepository" not in tools_source
    assert "class CardOperationQueryStore" in tools_source
    assert "class DailyProgressMutationStore" in tools_source
    assert "card_operation_store=operation_log_store" in service_source
    assert "daily_progress_store=daily_progress_store" in service_source


def test_frontend_routes_are_thin() -> None:
    route_files = [
        *Path("frontend/src/app/[locale]/(app)").rglob("page.tsx"),
        Path("frontend/src/app/[locale]/(app)/layout.tsx"),
        Path("frontend/src/app/[locale]/(app)/error.tsx"),
        Path("frontend/src/app/[locale]/(app)/not-found.tsx"),
        Path("frontend/src/app/[locale]/(auth)/login/page.tsx"),
    ]
    forbidden = [
        "useState",
        "useMemo",
        "useCallback",
        "MOCK_",
        "@/lib/hooks",
    ]
    for path in route_files:
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


def test_frontend_legacy_domain_hooks_are_compatibility_reexports() -> None:
    """Legacy hook paths must not own domain API or SWR state."""
    hooks_root = Path("frontend/src/lib/hooks")
    for path in hooks_root.glob("*.ts"):
        source = path.read_text()
        assert "@/lib/api" not in source, f"{path} imports API clients"
        assert "useSWR" not in source, f"{path} owns SWR state"
        assert "@/entities/" in source, f"{path} should re-export an entity hook"


def test_frontend_legacy_top_level_hooks_are_compatibility_reexports() -> None:
    """Canonical shared UI hooks live under frontend/src/shared."""
    hooks_root = Path("frontend/src/hooks")
    for path in hooks_root.glob("*.ts"):
        source = path.read_text()
        assert "@/shared/" in source, f"{path} should re-export shared code"
        assert "React.use" not in source, f"{path} owns hook implementation logic"

    for path in Path("frontend/src").rglob("*.ts*"):
        if path.parts[:3] == ("frontend", "src", "hooks"):
            continue
        source = path.read_text()
        assert "@/hooks/" not in source, f"{path} imports legacy top-level hooks"


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
    route_files = [
        *Path("frontend/src/app/[locale]/(app)").rglob("page.tsx"),
        Path("frontend/src/app/[locale]/(app)/layout.tsx"),
        Path("frontend/src/app/[locale]/(app)/error.tsx"),
        Path("frontend/src/app/[locale]/(app)/not-found.tsx"),
        Path("frontend/src/app/[locale]/(auth)/login/page.tsx"),
    ]
    allowed_internal_imports = ("@/widgets",)
    for path in route_files:
        source = path.read_text()
        for line in source.splitlines():
            if not line.startswith("import ") or '"@/' not in line:
                continue
            assert any(token in line for token in allowed_internal_imports), (
                f"{path} route page imports non-widget dependency: {line}"
            )


def test_frontend_locale_layout_keeps_provider_composition_in_widget() -> None:
    path = Path("frontend/src/app/[locale]/layout.tsx")
    source = path.read_text()
    forbidden_imports = (
        "@/components",
        "next/font",
        "next-intl\"",
    )

    assert "@/widgets/root-shell" in source
    for token in forbidden_imports:
        assert token not in source, (
            f"{path} owns root shell composition through {token}; "
            "compose LocaleRootShell instead"
        )


def test_frontend_root_shell_uses_shared_foundation() -> None:
    path = Path("frontend/src/widgets/root-shell/ui/locale-root-shell.tsx")
    source = path.read_text()

    assert "@/shared/providers" in source
    assert "@/shared/ui" in source
    assert "@/components" not in source


def test_frontend_ui_primitives_live_in_shared_ui() -> None:
    legacy_root = Path("frontend/src/components/ui")
    legacy_files = list(legacy_root.glob("*.tsx")) if legacy_root.exists() else []
    assert legacy_files == []

    for path in Path("frontend/src").rglob("*.ts*"):
        if "__tests__" in path.parts:
            continue
        source = path.read_text()
        assert "@/components/ui/" not in source, (
            f"{path} imports UI primitives from legacy components; "
            "use frontend/src/shared/ui"
        )


def test_frontend_generic_shared_components_live_in_shared_ui() -> None:
    generic_components = (
        "data-table",
        "empty-state",
        "page-header",
        "query-boundary",
        "stat-card",
    )
    for component in generic_components:
        assert not (
            Path("frontend/src/components/shared") / f"{component}.tsx"
        ).exists()
        assert (Path("frontend/src/shared/ui") / f"{component}.tsx").exists()

    legacy_prefix = "@/components/shared/"
    for path in Path("frontend/src").rglob("*.ts*"):
        if "__tests__" in path.parts:
            continue
        source = path.read_text()
        for component in generic_components:
            assert f"{legacy_prefix}{component}" not in source, (
                f"{path} imports generic shared UI from legacy components; "
                "use frontend/src/shared/ui"
            )


def test_frontend_app_shell_owns_event_listener() -> None:
    app_shell = Path("frontend/src/widgets/app-shell/ui/app-shell.tsx")
    source = app_shell.read_text()

    assert Path("frontend/src/widgets/app-shell/ui/event-listener.tsx").exists()
    assert not Path("frontend/src/components/shared/event-listener.tsx").exists()
    assert "@/components/shared/event-listener" not in source
    assert './event-listener' in source


def test_frontend_requirement_ui_lives_in_requirement_entity() -> None:
    for component in ("priority-badge", "status-badge"):
        assert not (
            Path("frontend/src/components/shared") / f"{component}.tsx"
        ).exists()
        assert (
            Path("frontend/src/entities/requirement/ui") / f"{component}.tsx"
        ).exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        assert "@/components/shared/priority-badge" not in source
        assert "@/components/shared/status-badge" not in source


def test_frontend_agent_display_ui_lives_in_agent_entity() -> None:
    legacy_components = (
        "agent-avatar",
        "agent-card",
        "agent-status-dot",
        "domain-badge",
    )
    for component in legacy_components:
        assert not (
            Path("frontend/src/components/shared") / f"{component}.tsx"
        ).exists()

    expected_entity_files = (
        "agent-display-avatar",
        "agent-display-card",
        "agent-display-status-dot",
        "domain-badge",
    )
    for component in expected_entity_files:
        assert (Path("frontend/src/entities/agent/ui") / f"{component}.tsx").exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        for component in legacy_components:
            assert f"@/components/shared/{component}" not in source


def test_frontend_offline_banner_lives_in_shared_ui() -> None:
    assert not Path("frontend/src/components/shared/offline-banner.tsx").exists()
    assert Path("frontend/src/shared/ui/offline-banner.tsx").exists()


def test_frontend_activity_and_approval_ui_live_in_entity_slices() -> None:
    expected = {
        "activity-item": Path("frontend/src/entities/activity/ui/activity-item.tsx"),
        "approval-card": Path("frontend/src/entities/approval/ui/approval-card.tsx"),
    }
    for component, target in expected.items():
        assert target.exists()
        assert not (Path("frontend/src/components/shared") / f"{component}.tsx").exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        assert "@/components/shared/activity-item" not in source
        assert "@/components/shared/approval-card" not in source


def test_frontend_app_shell_owns_layout_components() -> None:
    layout_components = ("app-sidebar", "top-bar", "locale-switcher")
    for component in layout_components:
        assert not (Path("frontend/src/components/layout") / f"{component}.tsx").exists()
        assert (Path("frontend/src/widgets/app-shell/ui") / f"{component}.tsx").exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        for component in layout_components:
            assert f"@/components/layout/{component}" not in source


def test_frontend_legacy_components_root_is_empty() -> None:
    legacy_files = list(Path("frontend/src/components").rglob("*.ts*"))
    assert legacy_files == []

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        assert "@/components/" not in source


def test_frontend_page_local_components_live_in_widgets() -> None:
    widget_components = {
        "activity": {
            "target": "activity",
            "files": ("activity-filters", "activity-timeline"),
        },
        "approvals": {
            "target": "approvals",
            "files": ("approval-filters", "approval-list"),
        },
        "dashboard": {
            "target": "dashboard",
            "files": (
                "fleet-summary-card",
                "llm-usage-card",
                "quick-actions",
                "stats-row",
                "status-chart",
                "trend-chart",
            ),
        },
        "home": {
            "target": "home",
            "files": (
                "fleet-grid",
                "greeting-banner",
                "pending-approvals",
                "recent-activity",
            ),
        },
        "monitor": {
            "target": "monitor",
            "files": ("circuit-breaker-card", "health-grid", "llm-stats-panel"),
        },
        "messages": {
            "target": "messages",
            "files": ("message-search", "message-table"),
        },
        "analytics": {
            "target": "cost-usage",
            "files": ("cost-chart", "token-breakdown"),
        },
    }

    for legacy_group, config in widget_components.items():
        for component in config["files"]:
            assert not (
                Path("frontend/src/components") / legacy_group / f"{component}.tsx"
            ).exists()
            assert (
                Path("frontend/src/widgets")
                / config["target"]
                / "ui"
                / f"{component}.tsx"
            ).exists()

    forbidden_prefixes = tuple(
        f"@/components/{legacy_group}/"
        for legacy_group in widget_components
    )
    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        for prefix in forbidden_prefixes:
            assert prefix not in source, (
                f"{path} imports page-local UI from {prefix}; "
                "keep page composition inside the owning widget"
            )


def test_frontend_user_action_components_live_in_features() -> None:
    feature_components = {
        "questions": {
            "target": "question-answer",
            "files": ("answer-form", "question-card"),
        },
        "ingest": {
            "target": "content-ingest",
            "files": ("ingest-result", "upload-form"),
        },
    }

    for legacy_group, config in feature_components.items():
        for component in config["files"]:
            assert not (
                Path("frontend/src/components") / legacy_group / f"{component}.tsx"
            ).exists()
            assert (
                Path("frontend/src/features")
                / config["target"]
                / "ui"
                / f"{component}.tsx"
            ).exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        assert "@/components/questions/" not in source
        assert "@/components/ingest/" not in source


def test_frontend_requirements_ui_lives_in_fsd_slices() -> None:
    entity_components = (
        "change-history",
        "context-messages",
        "requirement-header",
        "requirement-info",
        "requirements-table",
        "similar-requirements",
    )
    feature_components = ("batch-actions", "confirm-dialog", "reject-sheet")
    widget_components = ("requirements-filters",)

    for component in entity_components:
        assert not (
            Path("frontend/src/components/requirements") / f"{component}.tsx"
        ).exists()
        assert (
            Path("frontend/src/entities/requirement/ui") / f"{component}.tsx"
        ).exists()

    for component in feature_components:
        assert not (
            Path("frontend/src/components/requirements") / f"{component}.tsx"
        ).exists()
        assert (
            Path("frontend/src/features/requirement-review/ui")
            / f"{component}.tsx"
        ).exists()

    for component in widget_components:
        assert not (
            Path("frontend/src/components/requirements") / f"{component}.tsx"
        ).exists()
        assert (
            Path("frontend/src/widgets/requirements/ui") / f"{component}.tsx"
        ).exists()

    assert not Path(
        "frontend/src/components/requirements/__tests__/requirements-table.test.tsx"
    ).exists()
    assert Path(
        "frontend/src/entities/requirement/ui/requirements-table.test.tsx"
    ).exists()

    for path in Path("frontend/src").rglob("*.ts*"):
        source = path.read_text()
        assert "@/components/requirements/" not in source


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


def test_event_catalog_documents_all_runtime_event_types() -> None:
    """Every EventTypes constant is a cross-boundary contract."""
    catalog = Path("docs/guides/event-catalog.md").read_text()
    event_types = {
        value
        for name, value in vars(EventTypes).items()
        if name.isupper() and isinstance(value, str)
    }

    missing = sorted(event_type for event_type in event_types if event_type not in catalog)

    assert missing == []


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
