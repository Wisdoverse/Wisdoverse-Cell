> **META**: Supreme Law of this repo. All AI Agents must follow.

## Part 0: Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # Fill in secrets
make up-infra                                     # Start PG/Redis/NATS/Milvus
make dev                                          # Start requirement_manager
```

## Part 1: The Board of Directors

| Role | Focus | Key Question |
|------|-------|--------------|
| CPO | UX, Business Value | "Graceful fallback if LLM fails?" |
| Architect | Decoupling, Events | "Agent properly isolated?" |
| Engineer | Async, Pydantic v2 | "Blocking Event Loop?" |
| Security | PII, Injection | "Logging sensitive data?" |
| PM | Tasks, Docs | "Code matches checklist?" |

## Part 2: Mandatory Workflow

1. **Plan**: TODO checklist (Design → Logic → Events → Test → Docs)
2. **Execute**: Implement one by one, verify each step
3. **Audit** (`/audit`): Output [Analysis] [Risk:H/M/L] [Fixes]

## Part 2.1: Public-First Git Workflow

- `main` is the public-first active trunk and the default base for all new work.
- `intern-archive` is a read-only archive of the pre-public internal history.
- Never merge `intern-archive` into `main`; bring forward required changes with reviewed cherry-picks or patches only.
- Never commit directly to `main`; create a feature/fix branch before editing.

## Part 3: Architecture & Context

**Wisdoverse Cell**: AI 原生运营公司 — 用 AI Agent 替代传统组织架构，2 名人类 + 26 个 Agent 协作运营。Agent 具备三层自进化能力（L1 Skill 优化 / L2 架构优化 / L3 协作优化），模型越强，系统越强。

```
agents/
  chat_agent/                 # 用户交互网关/前台，不是 CEO
  coordinator/                # 跨 Agent 事件编排器，不是完整 CEO 角色
  pjm_agent/                   # 任务拆解/审批/预警/报表能力模块
  sync_agent/                 # OP ↔ 飞书上下文同步能力模块
  analysis_agent/             # 风险检测/数据分析能力模块
  requirement_manager/        # 需求提取/确认/PRD 生成能力模块
  evolution_agent/            # 自进化分析/建议能力模块
  qa_agent/                   # QA 验收能力模块
  dev_agent/                  # AgentForge 开发执行能力模块
  channel_gateway/            # 多渠道消息网关
gateway/                      # Go + Gin API Gateway
frontend/                     # Next.js 16 + React 19
shared/
  app/                        # AgentRuntime + create_agent_app (插件架构)
  control_plane/              # RoleAgent / capability module ledger, runs, approvals, budgets
  api/                        # Shared API routes/schemas
  core/messaging/             # Port 接口 (六边形架构)
  db/                         # Shared database layer
  grpc/                       # gRPC proto + generated code
  messaging/{inbound,outbound}/ # 消息网关
  integrations/{feishu,wecom,...}/ # 平台 Adapter
  infra/                      # CircuitBreaker, AgentClient, VectorStore, Embedder
  middleware/                  # Shared middleware
  models/                     # Shared Pydantic models
  observability/              # Logging, tracing, metrics
  protocols/                  # Protocol definitions
  schemas/                    # Event, Agent, Error
  services/                   # EventBus, LLM Gateway + 兼容层
  utils/                      # Shared utilities
  evolution/                  # 三层自进化系统 (L1/L2/L3)
    collaboration/            # L3 Agent Teams 协作优化
    db/                       # Evolution 数据库层
    seeds/                    # Agent Skill 种子数据
```

**Stack**: FastAPI | Go+Gin | Next.js 16 | PostgreSQL 18 | Redis 8 (EventBus) | NATS JetStream | Milvus | Claude API | Traefik v3

## Part 4: Coding Standards

**Events**: `Event(event_id="evt_{ulid}", event_type="{domain}.{action}", source_agent, payload, schema_version="1.0")`
- Immutable, fire-and-forget, use `trace_id`

**Imports**: Use canonical paths (`shared.integrations.feishu`, `shared.messaging.outbound`, `shared.infra.agent_client`). Never add new imports from `shared.services.*` deprecated paths.

**Agents**: Inherit `BaseAgent`, implement `handle_event()`, `startup()`, `shutdown()`. Use `create_agent_app()` for FastAPI entry (see `shared/app/`). Scheduler jobs must call `runtime.agent` not `_raw_agent`.

**Human-in-the-Loop**: Finance | Legal | Customer | Technical (must approve)

**Python**: Async I/O | `model_dump_json()` | Repository pattern | Never log secrets

## Part 5: Operational Commands

```bash
make test                                          # Python tests
make dev                                           # uvicorn --reload (requirement_manager)
make gateway-dev                                   # Go gateway dev
make frontend-dev                                  # Next.js dev
make up-dev                                        # Docker Compose 全部服务
make up-infra                                      # 仅基础设施 (PG/Redis/NATS/Milvus)
make proto                                         # Generate all protobuf code
make grpc-server                                   # Run gRPC server
make build                                         # Build Docker images
make monitoring-up                                 # Observability stack
make load-smoke                                    # k6 smoke test (10 VUs)
make clean                                         # Remove all containers + prune
ruff check agents/ shared/                         # Lint
```

## Part 6: Living Memory

### Lessons Learned

* **[2026-01 Agent ID]**: kebab-case (`requirement-manager`)
* **[2026-01 Git]**: Create feature branch BEFORE any changes; never commit directly to `main`
* **[2026-04 Public Mainline]**: `main` is the public-first trunk; `intern-archive` is read-only and must not be merged back
* **[2026-01 datetime]**: Use `datetime.now(UTC)` not deprecated `datetime.utcnow()`
* **[2026-01 Code Quality]**: Run `code-simplifier` before committing feature branches
* **[2026-03 Hexagonal Architecture]**: `shared/core/messaging/` = Port, `shared/messaging/` = orchestration, `shared/integrations/` = Adapter
* **[2026-03 Import Migration]**: Use `patch.object(module, "attr")` not `patch("string.path")` — resilient to directory moves
* **[2026-03 Compat Stubs]**: Old files → `"""Deprecated: use new.path"""\nfrom new.path import *` for zero-consumer-change migration
* **[2026-03 Feature Flags]**: `settings.use_new_delivery_service` for outbound path rollback
* **[2026-03 CI Lint]**: `scripts/lint_deprecated_imports.py` blocks new deprecated imports in MR
* **[2026-03 RuntimePlugin]**: Extend agent capabilities via plugins (`runtime.use(MyPlugin())`), not by modifying runtime
* **[2026-03 Evolution]**: `shared/evolution/` = 三层自进化 (L1 Skill/Prompt, L2 Architecture, L3 Collaboration)
* **[2026-03 Vector DB]**: Milvus (not Chroma). Use `shared/infra/milvus_store.py` + `shared/infra/embedder.py`
* **[2026-04 LLM Error Taxonomy]**: `shared/infra/llm_errors.py` — 6 error categories (rate_limit/overloaded/network/auth/content_size/other) with per-category `RetryStrategy`. Anthropic returns HTTP 400 (not 413) for prompt-too-long — detect via message pattern matching in `classify_error()`.
* **[2026-04 ContentSizeError]**: Plain `Exception` subclass, NOT `anthropic.APIStatusError` (avoids coupling to SDK constructor that requires `httpx.Response`). Chain original via `__cause__`.
* **[2026-04 Custom Retry]**: `_call_with_recovery()` in `llm_gateway.py` replaces tenacity. Enables model fallback mid-retry and ReactiveCompact on content_size. Circuit breaker records 1 failure after ALL retries+fallback exhausted.
* **[2026-04 Context Compression 3-Layer]**: MicroCompact (free, block-count tool_result clearing) → L1 trim → L2 summarize → ReactiveCompact (emergency on prompt-too-long). `micro_compact()` and `reactive_compact()` in `context_compressor.py`.
* **[2026-04 ConversationEngine]**: `shared/infra/conversation_engine.py` — shared multi-turn tool loop with AsyncGenerator events. Per-request lifetime, not singleton. Caller creates per request with `messages=loaded_history`, extracts `engine.messages` after `run()`.
* **[2026-04 Chat Agent = 前台]**: Per coordinator-agent-design.md §2, chat_agent is the receptionist (前台), NOT the CEO. Simple queries handled directly, complex cross-agent workflows escalated to Coordinator. System prompt teaches operations, not strategy.
* **[2026-05 Agent Org]**: CEO/CTO/CPO/COO 等是一等 `organization_role` AgentRole；sync/QA/requirement/dev 等现有服务是 `capability_module`，不要把功能模块伪装成组织角色。
* **[2026-04 Prompt Style]**: Follow Claude Code pattern — tool definitions via API `tools` param, prompt teaches usage STRATEGY not tool list. Sections: System → Doing Tasks → Executing Actions → Output Efficiency. Include anti-patterns ("不要...").

> *v2026.04.03-compact*
