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

1. **Plan**: TODO checklist (Design -> Logic -> Events -> Test -> Docs)
2. **Execute**: Implement one by one, verify each step
3. **Audit** (`/audit`): Output [Analysis] [Risk:H/M/L] [Fixes]

## Part 2.1: Public-First Git Workflow

- `main` is the public-first active trunk and the default base for all new work.
- `intern-archive` is a read-only archive of the pre-public internal history.
- Never merge `intern-archive` into `main`; bring forward required changes with reviewed cherry-picks or patches only.
- Never commit directly to `main`; create a feature/fix branch before editing.

## Part 3: Architecture & Context

**Wisdoverse Cell**: AI-native operating company. It replaces traditional
organization structure with AI Agents: 2 humans + 26 agents. Agents have three
self-evolution levels: L1 skill optimization, L2 architecture optimization, and
L3 collaboration optimization. Stronger models should strengthen the system.

```
agents/
  chat_agent/                 # User interaction gateway and receptionist; not CEO
  coordinator/                # Cross-agent event orchestrator; not a full CEO role
  pjm_agent/                   # Task decomposition, approval, alert, and reporting module
  sync_agent/                 # OpenProject <-> Feishu context sync module
  analysis_agent/             # Risk detection and data analysis module
  requirement_manager/        # Requirement extraction, confirmation, and PRD module
  evolution_agent/            # Self-evolution analysis and recommendation module
  qa_agent/                   # QA acceptance module
  dev_agent/                  # AgentForge development execution module
  channel_gateway/            # Multi-channel messaging gateway
gateway/                      # Go + Gin API Gateway
frontend/                     # Next.js 16 + React 19
shared/
  app/                        # AgentRuntime + create_agent_app (plugin architecture)
  control_plane/              # RoleAgent / capability module ledger, runs, approvals, budgets
  api/                        # Shared API routes/schemas
  core/messaging/             # Port interfaces (hexagonal architecture)
  db/                         # Shared database layer
  grpc/                       # gRPC proto + generated code
  messaging/{inbound,outbound}/ # Messaging gateway
  integrations/{feishu,wecom,...}/ # Platform adapters
  infra/                      # CircuitBreaker, AgentClient, VectorStore, Embedder
  middleware/                  # Shared middleware
  models/                     # Shared Pydantic models
  observability/              # Logging, tracing, metrics
  protocols/                  # Protocol definitions
  schemas/                    # Event, Agent, Error
  services/                   # EventBus, LLM Gateway + compatibility layer
  utils/                      # Shared utilities
  evolution/                  # Three-level self-evolution system (L1/L2/L3)
    collaboration/            # L3 Agent Teams collaboration optimization
    db/                       # Evolution database layer
    seeds/                    # Agent Skill seed data
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
make up-dev                                        # Docker Compose all services
make up-infra                                      # Infrastructure only (PG/Redis/NATS/Milvus)
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
* **[2026-03 Import Migration]**: Use `patch.object(module, "attr")` not `patch("string.path")` - resilient to directory moves
* **[2026-03 Compat Stubs]**: Old files -> `"""Deprecated: use new.path"""\nfrom new.path import *` for zero-consumer-change migration
* **[2026-03 Feature Flags]**: `settings.use_new_delivery_service` for outbound path rollback
* **[2026-03 CI Lint]**: `scripts/lint_deprecated_imports.py` blocks new deprecated imports in MR
* **[2026-03 RuntimePlugin]**: Extend agent capabilities via plugins (`runtime.use(MyPlugin())`), not by modifying runtime
* **[2026-03 Evolution]**: `shared/evolution/` = three-level self-evolution (L1 Skill/Prompt, L2 Architecture, L3 Collaboration)
* **[2026-03 Vector DB]**: Milvus (not Chroma). Use `shared/infra/milvus_store.py` + `shared/infra/embedder.py`
* **[2026-04 LLM Error Taxonomy]**: `shared/infra/llm_errors.py` - 6 error categories (rate_limit/overloaded/network/auth/content_size/other) with per-category `RetryStrategy`. Anthropic returns HTTP 400 (not 413) for prompt-too-long - detect via message pattern matching in `classify_error()`.
* **[2026-04 ContentSizeError]**: Plain `Exception` subclass, NOT `anthropic.APIStatusError` (avoids coupling to SDK constructor that requires `httpx.Response`). Chain original via `__cause__`.
* **[2026-04 Custom Retry]**: `_call_with_recovery()` in `llm_gateway.py` replaces tenacity. Enables model fallback mid-retry and ReactiveCompact on content_size. Circuit breaker records 1 failure after ALL retries+fallback exhausted.
* **[2026-04 Context Compression 3-Layer]**: MicroCompact (free, block-count tool_result clearing) -> L1 trim -> L2 summarize -> ReactiveCompact (emergency on prompt-too-long). `micro_compact()` and `reactive_compact()` in `context_compressor.py`.
* **[2026-04 ConversationEngine]**: `shared/infra/conversation_engine.py` - shared multi-turn tool loop with AsyncGenerator events. Per-request lifetime, not singleton. Caller creates per request with `messages=loaded_history`, extracts `engine.messages` after `run()`.
* **[2026-04 Chat Agent = Reception]**: Per coordinator-agent-design.md section 2, chat_agent is the receptionist, NOT the CEO. Simple queries handled directly, complex cross-agent workflows escalated to Coordinator. System prompt teaches operations, not strategy.
* **[2026-05 Agent Org]**: CEO/CTO/CPO/COO are first-class `organization_role` AgentRole records. sync/QA/requirement/dev and similar existing services are `capability_module` records. Do not present capability modules as organization roles.
* **[2026-04 Prompt Style]**: Follow Claude Code pattern - tool definitions via API `tools` param, prompt teaches usage STRATEGY not tool list. Sections: System -> Doing Tasks -> Executing Actions -> Output Efficiency. Include anti-patterns ("do not...").

> *v2026.04.03-compact*
