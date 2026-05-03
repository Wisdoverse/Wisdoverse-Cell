"""
Configuration - centralized settings management.

Loads settings from environment variables and the local .env file through
pydantic-settings.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global application settings.

    Priority: environment variables > .env file > defaults.
    """

    # ============ Database Configuration ============
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "projectcell"
    postgres_user: str = "cell"
    postgres_password: SecretStr = SecretStr("")

    # Connection Pool
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    db_pool_timeout: int = 30
    db_connect_timeout: int = 10
    db_command_timeout: int = 60

    @property
    def database_url(self) -> str:
        """SQLAlchemy database URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # Database Read Replica (optional — enables read/write split)
    db_read_host: Optional[str] = None
    db_read_port: Optional[int] = None

    @property
    def database_read_url(self) -> Optional[str]:
        """SQLAlchemy read replica URL (None if not configured)."""
        if not self.db_read_host:
            return None
        port = self.db_read_port or self.postgres_port
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}@{self.db_read_host}:{port}/{self.postgres_db}"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[SecretStr] = None

    @property
    def redis_url(self) -> str:
        """Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password.get_secret_value()}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def redis_event_bus_url(self) -> str:
        """EventBus always uses db 0 regardless of agent's redis_db setting."""
        base = f"redis://{self.redis_host}:{self.redis_port}"
        if self.redis_password:
            base = f"redis://:{self.redis_password.get_secret_value()}@{self.redis_host}:{self.redis_port}"
        return f"{base}/0"

    # NATS JetStream
    nats_url: str = "nats://localhost:4222"
    nats_stream_replicas: int = 1
    event_bus_backend: Literal["nats", "redis"] = "redis"

    @model_validator(mode="after")
    def _validate_nats_config(self) -> "Settings":
        if self.event_bus_backend == "nats" and not self.nats_url.strip():
            raise ValueError("nats_url must be set when event_bus_backend is 'nats'")
        if self.nats_stream_replicas < 1:
            raise ValueError("nats_stream_replicas must be >= 1")
        return self

    # Vector Database (Milvus)
    milvus_uri: str = "http://localhost:19530"
    milvus_token: SecretStr = SecretStr("")

    # Chroma (deprecated — kept for migration period, prefer milvus_*)
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # ============ LLM Configuration ============
    llm_provider: str = "litellm"  # Deprecated switch; LiteLLM is the only runtime path.
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    openrouter_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    google_api_key: SecretStr = SecretStr("")
    default_model: str = "claude-opus-4-6"
    chat_model: str = "claude-sonnet-4-20250514"  # Conversations: $3/$15 per MTok
    decompose_model: str = "claude-opus-4-20250514"  # Complex decomposition: $15/$75
    summary_model: str = "claude-haiku-4-5-20251001"  # Summaries/reports: $1/$5
    litellm_api_base: str = ""  # Optional LiteLLM/provider proxy base URL

    # Cost controls
    llm_daily_budget_usd: float = 10.0  # daily budget
    llm_monthly_budget_usd: float = 200.0  # monthly budget
    llm_per_request_cost_cap_usd: float = 2.0  # max cost per single LLM call

    # ============ Control Plane Configuration ============
    control_plane_enabled: bool = False
    control_plane_company_id: str = "cmp_projectcell"
    control_plane_approval_enforced: bool = False
    control_plane_llm_budget_enforced: bool = False
    control_plane_llm_budget_scope: Literal["company", "goal", "agent", "work_item"] = "agent"
    control_plane_llm_budget_period: Literal["daily", "monthly", "quarterly", "total"] = "daily"
    control_plane_tool_budget_enforced: bool = False
    control_plane_tool_budget_scope: Literal["company", "goal", "agent", "work_item"] = "agent"
    control_plane_tool_budget_period: Literal["daily", "monthly", "quarterly", "total"] = "daily"
    control_plane_local_adapter_enabled: bool = False
    control_plane_local_adapter_allowlist: str = ""

    @property
    def control_plane_local_adapter_allowlist_entries(self) -> set[str]:
        """Parse local adapter allowlist entries from comma-separated config."""
        return {
            item.strip()
            for item in self.control_plane_local_adapter_allowlist.split(",")
            if item.strip()
        }

    # ============ Notification Configuration ============
    feishu_webhook_url: Optional[str] = None
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[SecretStr] = None

    # ============ Feishu Deep Integration Configuration ============
    # Security configuration
    feishu_encrypt_key: SecretStr = SecretStr("")
    feishu_verification_token: SecretStr = SecretStr("")
    feishu_verify_signature: bool = True

    # Feature flags
    feishu_enabled: bool = False
    feishu_bot_enabled: bool = True
    feishu_event_enabled: bool = True
    feishu_card_enabled: bool = True

    # Notification configuration
    feishu_default_chat_id: str = ""
    feishu_default_user_id: str = ""  # prefer direct user delivery

    # Advanced configuration
    feishu_api_base_url: str = "https://open.feishu.cn/open-apis"
    feishu_token_refresh_buffer: int = 300

    # ============ Feishu Message Recording Configuration ============
    feishu_message_recording_enabled: bool = False
    feishu_monitored_chat_ids_raw: str = ""  # Comma-separated chat IDs
    feishu_session_timeout: int = 300  # seconds (5 minutes)
    feishu_min_messages_to_extract: int = 5

    @property
    def feishu_monitored_chat_ids(self) -> list[str]:
        """Parse comma-separated chat IDs from environment variable."""
        if not self.feishu_monitored_chat_ids_raw.strip():
            return []
        return [x.strip() for x in self.feishu_monitored_chat_ids_raw.split(",") if x.strip()]

    # ============ WeCom Configuration ============
    wecom_enabled: bool = False
    wecom_corp_id: str = ""
    wecom_agent_id: int = 0
    wecom_secret: SecretStr = SecretStr("")
    wecom_token: SecretStr = SecretStr("")
    wecom_encoding_aes_key: SecretStr = SecretStr("")
    wecom_api_base_url: str = "https://qyapi.weixin.qq.com/cgi-bin"
    wecom_token_refresh_buffer: int = 300
    wecom_bot_enabled: bool = True
    wecom_card_enabled: bool = True

    # ============ OpenClaw Configuration ============
    openclaw_enabled: bool = False
    openclaw_gateway_url: str = "ws://127.0.0.1:18789"
    openclaw_gateway_token: SecretStr = SecretStr("")
    openclaw_device_id: str = "projectcell"

    # ============ CORS Configuration ============
    cors_allowed_origins: str = ""
    cors_allowed_methods: str = "GET,POST,PUT,DELETE,OPTIONS"
    cors_allowed_headers: str = "Content-Type,Authorization,X-Request-ID,X-API-Key"
    cors_allow_credentials: bool = False
    cors_max_age: int = 600

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # ============ Application Configuration ============
    app_name: str = "Wisdoverse Cell"
    app_env: str = "development"  # development, staging, production
    debug: bool = False

    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ============ Rate Limiting ============
    rate_limit_requests: int = 200
    rate_limit_window_seconds: int = 60
    max_payload_size_bytes: int = 1_000_000  # 1MB default for input validation

    # ============ Security Configuration ============
    secret_key: SecretStr = SecretStr("change-me-in-production")
    pm_api_key: str = ""  # X-API-Key for non-health endpoints; empty only in dev/test
    internal_service_key: str = ""  # X-Internal-Key for inter-service calls; empty only in dev/test

    # ============ A2A Protocol Configuration ============
    a2a_enabled: bool = False
    a2a_server_port: int = 8001
    a2a_jwt_secret: SecretStr = SecretStr("change-me-in-production-a2a")
    a2a_jwt_algorithm: str = "HS256"
    a2a_jwt_expiry_minutes: int = 60
    a2a_api_key_enabled: bool = False
    a2a_api_key_header: str = "X-API-Key"
    a2a_rate_limit_requests: int = 100
    a2a_rate_limit_window_seconds: int = 60

    # ============ OpenTelemetry Configuration ============
    otel_endpoint: str = ""
    otel_service_name: str = "ai-core"

    # ============ MCP Protocol Configuration ============
    mcp_enabled: bool = False
    mcp_server_port: int = 8002

    # ============ OpenProject Configuration ============
    openproject_url: str = ""
    openproject_api_key: SecretStr = SecretStr("")

    # ============ PM System Configuration ============
    feishu_bitable_app_token: str = ""
    feishu_bitable_table_id: str = ""
    feishu_bitable_member_table_id: str = ""
    feishu_bitable_category_table_id: str = ""
    feishu_bitable_report_table_id: str = ""
    feishu_pm_app_token: str = ""
    feishu_pm_member_table_id: str = ""
    feishu_pm_project_table_id: str = ""
    feishu_pm_task_table_id: str = ""
    feishu_pm_workload_table_id: str = ""
    feishu_pm_rules_table_id: str = ""
    feishu_report_chat_id: str = ""

    # ============ Decomposition Configuration ============
    decompose_project_ids: str = ""  # Comma-separated OP project IDs, e.g. "72,84"
    decompose_notify_open_id: str = ""  # Feishu open_id for decompose approval notifications

    # ============ Channel Gateway Feature Flags ============
    use_new_delivery_service: bool = False  # gray-release outbound DeliveryService

    # ============ Event Bus Configuration ============
    event_bus_consumer_name: str = ""  # NATS durable consumer name; defaults to OTEL_SERVICE_NAME
    event_bus_queue_max_length: int = 10_000  # Max events per consumer-group queue
    event_bus_queue_ttl_seconds: int = 86_400  # Queue key expiry (24h)
    event_bus_pending_claim_idle_ms: int = 360_000  # Redis Streams pending reclaim idle time
    event_bus_pending_claim_count: int = 10  # Max pending messages to reclaim per stream poll
    event_bus_processed_event_ttl_seconds: int = 604_800  # Event replay idempotency window
    event_bus_processing_lock_ttl_seconds: int = 360  # In-flight event idempotency lock TTL
    event_loop_max_backoff_seconds: int = 60  # Max retry backoff for agent event loops
    event_handler_timeout_seconds: int = 300  # 5 min default per event handler

    # ============ GitLab Integration Configuration ============
    gitlab_api_url: str = ""  # e.g. https://gitlab.example.com/api/v4
    gitlab_project_id: str = ""
    gitlab_qa_token: SecretStr = SecretStr("")  # Bot token for MR comments
    gitlab_comment_marker: str = "<!-- qa-agent-acceptance-report -->"

    # ============ QA Agent Configuration ============
    qa_agent_url: str = "http://qa-agent:8014"
    qa_runner_timeout_seconds: int = 120
    qa_feishu_webhook_url: str = ""  # QA-specific Feishu webhook (fallback to feishu_webhook_url)
    qa_high_severity_checks: str = ""  # Comma-separated check names that trigger Feishu on L1 WARN

    @property
    def qa_high_severity_check_list(self) -> list[str]:
        if not self.qa_high_severity_checks.strip():
            return []
        return [c.strip() for c in self.qa_high_severity_checks.split(",") if c.strip()]

    # ============ Agent Service Discovery ============
    sync_agent_host: str = "sync-agent"
    sync_agent_port: int = 8010
    pjm_agent_url: str = "http://pjm-agent:8012"

    # ============ Deprecated provider-specific proxy settings ============
    # Kept only so old .env files keep loading. Use LITELLM_API_BASE instead.
    anthropic_base_url: str = ""
    require_anthropic_proxy: bool = False

    @model_validator(mode="after")
    def _fail_closed_for_production_secrets(self) -> "Settings":
        if self.app_env.lower() not in {"production", "prod"}:
            return self

        def _empty_secret(value: SecretStr | None) -> bool:
            return value is None or not value.get_secret_value().strip()

        def _selected_llm_providers() -> set[str]:
            providers: set[str] = set()
            for model in {
                self.default_model,
                self.chat_model,
                self.decompose_model,
                self.summary_model,
            }:
                normalized = model.strip().lower()
                if not normalized:
                    continue
                if normalized.startswith("openrouter/"):
                    providers.add("openrouter")
                elif normalized.startswith(("claude-", "anthropic/")):
                    providers.add("anthropic")
                elif normalized.startswith(("openai/", "azure/", "gpt-", "o1", "o3", "o4")):
                    providers.add("openai")
                elif normalized.startswith(("gemini/", "google/", "vertex_ai/")):
                    providers.add("gemini")
                else:
                    providers.add("generic")
            return providers

        def _missing_llm_access_secrets() -> list[str]:
            provider_keys = {
                "anthropic": [("ANTHROPIC_API_KEY", self.anthropic_api_key)],
                "openai": [("OPENAI_API_KEY", self.openai_api_key)],
                "openrouter": [("OPENROUTER_API_KEY", self.openrouter_api_key)],
                "gemini": [
                    ("GEMINI_API_KEY", self.gemini_api_key),
                    ("GOOGLE_API_KEY", self.google_api_key),
                ],
            }

            # LiteLLM proxy deployments commonly use OPENAI_API_KEY as the
            # proxy auth token regardless of the upstream model provider.
            if self.litellm_api_base.strip() and not _empty_secret(self.openai_api_key):
                return []

            missing: list[str] = []
            for provider in sorted(_selected_llm_providers()):
                keys = provider_keys.get(provider)
                if keys is None:
                    if all(
                        _empty_secret(secret)
                        for _, secret in [
                            ("ANTHROPIC_API_KEY", self.anthropic_api_key),
                            ("OPENAI_API_KEY", self.openai_api_key),
                            ("OPENROUTER_API_KEY", self.openrouter_api_key),
                            ("GEMINI_API_KEY", self.gemini_api_key),
                            ("GOOGLE_API_KEY", self.google_api_key),
                        ]
                    ):
                        missing.append("LLM_PROVIDER_API_KEY")
                    continue
                if all(_empty_secret(secret) for _, secret in keys):
                    missing.append(" or ".join(name for name, _ in keys))
            return missing

        missing: list[str] = []
        if _empty_secret(self.postgres_password):
            missing.append("POSTGRES_PASSWORD")
        if _empty_secret(self.redis_password):
            missing.append("REDIS_PASSWORD")
        missing.extend(_missing_llm_access_secrets())
        if self.secret_key.get_secret_value() in {
            "",
            "change-me-in-production",
            "dev-only-change-in-production",
        }:
            missing.append("SECRET_KEY")
        if not self.pm_api_key.strip():
            missing.append("PM_API_KEY")
        if not self.internal_service_key.strip():
            missing.append("INTERNAL_SERVICE_KEY")
        if not self.control_plane_enabled:
            missing.append("CONTROL_PLANE_ENABLED")
        if not self.control_plane_approval_enforced:
            missing.append("CONTROL_PLANE_APPROVAL_ENFORCED")
        if self.a2a_jwt_secret.get_secret_value() in {
            "",
            "change-me-in-production-a2a",
            "dev-only-change-in-production",
        }:
            missing.append("A2A_JWT_SECRET")
        if self.feishu_enabled:
            if not self.feishu_verify_signature:
                missing.append("FEISHU_VERIFY_SIGNATURE")
            if _empty_secret(self.feishu_encrypt_key):
                missing.append("FEISHU_ENCRYPT_KEY")
        if self.wecom_enabled:
            if _empty_secret(self.wecom_token):
                missing.append("WECOM_TOKEN")
            if _empty_secret(self.wecom_encoding_aes_key):
                missing.append("WECOM_ENCODING_AES_KEY")

        if missing:
            names = ", ".join(missing)
            raise ValueError(f"production settings require non-default secrets: {names}")
        return self

    # ============ Dev Agent Configuration ============
    # AgentForge Orchestrator
    agentforge_api_url: str = "http://localhost:4010"
    agentforge_token: SecretStr = SecretStr("")
    dev_agentforge_project_id: str = ""

    # GitLab API (MR creation only, no merge permission)
    dev_gitlab_api_url: str = ""
    dev_gitlab_token: SecretStr = SecretStr("")
    dev_gitlab_project_id: int = 0

    # Concurrency
    dev_max_concurrent_workflows: int = 5
    dev_workflow_timeout_hours: int = 6

    # LLM cost control
    dev_llm_daily_token_limit: int = 500_000
    dev_llm_per_task_token_limit: int = 20_000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Return the cached settings singleton.

    lru_cache ensures settings are loaded only once per process.
    """
    return Settings()


# Convenient module-level access
settings = get_settings()
