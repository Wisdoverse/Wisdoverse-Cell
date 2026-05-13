> **META**: Supreme Law of this repo. All AI Agents must follow.

## Part 0: Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # Fill in secrets
make up-infra                                     # Start PG/Redis/NATS/Milvus
make dev                                          # Start the requirement manager agent
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
  requirement_manager/        # Real business runtime agent: requirements, PRD, local Feishu flow
  pjm_agent/                  # Real business runtime agent: task decomposition and reporting
  qa_agent/                   # Real business runtime agent: QA acceptance and quality checks
  dev_agent/                  # Real business runtime agent: AgentForge delivery execution
services/
  gateways/
    user_interaction/         # User-facing chat and Feishu webhook gateway
    channel/                  # Multi-channel messaging gateway
  orchestration/
    coordinator/              # Cross-module event orchestration worker
rust/gateway/                 # Rust + Axum API Gateway
frontend/                     # Next.js 16 + React 19
shared/
  capabilities/               # Shared support capabilities; not business agents
    sync/                     # Sync runtime; OpenProject and Feishu Bitable boundaries stay split inside core/
    analysis/                 # Risk detection and operating analytics capability
    evolution/                # Self-evolution analysis and recommendation capability
  app/                        # AgentRuntime + create_agent_app (plugin architecture)
  control_plane/              # RoleAgent / capability module ledger, runs, approvals, budgets
  api/                        # Shared API routes/schemas
  core/                       # Abstract ports/protocols; messaging ports live here
  db/                         # Shared database layer
  grpc/                       # gRPC proto + generated code
  messaging/{inbound,outbound}/ # Messaging gateway
  integrations/{feishu,wecom,...}/ # Platform adapters, including Feishu card renderers
  infra/                      # CircuitBreaker, AgentClient, EventBus, LLM Gateway, VectorStore, Embedder
  middleware/                  # Shared middleware
  models/                     # Shared Pydantic models
  observability/              # Logging, tracing, metrics
  protocols/                  # Protocol definitions
  schemas/                    # Event, Agent, Error
  services/                   # Deprecated compatibility shims only; do not add new imports here
  utils/                      # Shared utilities
  evolution/                  # Three-level self-evolution system (L1/L2/L3)
    collaboration/            # L3 Agent Teams collaboration optimization
    db/                       # Evolution database layer
    seeds/                    # Agent Skill seed data
```

**Stack**: FastAPI | Rust+Axum gateway | Next.js 16 | PostgreSQL 18 | Redis 8 (EventBus) | NATS JetStream | Milvus | LiteLLM through LLM Gateway | Traefik v3

### Architecture Boundary Rules

This section is the repository architecture constitution. `SPEC.md`,
`docs/overview/architecture.md`, and this file must stay aligned.

Wisdoverse Cell uses Control Plane Architecture at repository level.

Backend architecture:

- Agent Service Boundary for runtime isolation
- Strategic DDD for domain vocabulary and bounded contexts
- Clean Architecture inside each agent service
- Hexagonal Architecture for integrations and messaging
- Do not model the backend as a traditional DDD monolith

Frontend architecture:

- Strict Feature-Sliced Design

Agent role model:

- Organization-role agents such as CEO, CTO, CPO, and COO are durable
  `shared.control_plane.AgentRole` records and templates.
- Real business runtime agents such as `requirement-manager`, `pjm-agent`,
  `qa-agent`, and `dev-agent` live as root packages under `agents/`.
- Capability services such as sync, analysis, and evolution are independently
  deployable support modules under `shared/capabilities/`. The sync runtime
  must keep OpenProject synchronization and Feishu Bitable synchronization as
  separate bounded capabilities, even when a compatibility endpoint orchestrates
  both.
- Runtime metadata and AgentRole templates belong to
  `shared/control_plane/agent_catalog.py`.

Rules:

1. Agents must not directly import another independently deployed agent.
2. Agents communicate through HTTP clients or EventBus events.
3. External platforms must be accessed through ports and adapters.
4. `shared/control_plane` owns durable product objects: `Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Approval`, `Budget`, `Artifact`, `AuditEvent`.
5. `shared/core` owns abstract ports and protocols.
6. `shared/integrations` owns platform adapters.
7. `shared/utils` must not contain business logic.
8. Frontend route files must stay thin.
9. Frontend domain data belongs to `entities`.
10. Frontend user actions belong to `features`.
11. Frontend composed operator surfaces belong to `widgets`.
12. All cross-boundary contracts must be documented in `SPEC.md`, API docs, or the Event Catalog.
13. Canonical runtime identifiers after the 2026-05-10 brand unification: `wisdoverse-cell` (kebab — services, networks, compose project, image suffixes), `wisdoverse_cell` (snake — Python distribution, fully-qualified DB references), and `Wisdoverse Cell` (display). Existing agent IDs (`requirement-manager`, `pjm-agent`, `qa-agent`, `dev-agent`, `chat-agent`, `sync-module`, `analysis-module`, `evolution-module`) and the company ID `cmp_wisdoverse_cell` are stable from this point forward and must not be renamed.

## Part 4: Coding Standards

**Language**: English is the primary project language. Use English for
documentation, code comments, API descriptions, LLM prompts, agent seed prompts,
commit messages, PR/MR descriptions, and internal runbooks. Non-English text is
allowed only for locale files, external platform field names, quoted user/source
content, test fixtures that intentionally exercise multilingual behavior, and
user-facing product copy while an i18n path is being migrated.

**Events**: `Event(event_id="evt_{ulid}", event_type="{domain}.{action}", source_agent, payload, schema_version="1.0")`
- Immutable, fire-and-forget, use `trace_id`

**Imports**: Use canonical paths (`shared.integrations.feishu`, `shared.messaging.outbound`, `shared.infra.agent_client`). Never add new imports from `shared.services.*` deprecated paths.

**Agents**: Inherit `BaseAgent`, implement `handle_event()`, `startup()`, `shutdown()`. Use `create_agent_app()` for FastAPI entry (see `shared/app/`). Scheduler jobs must call `runtime.agent` not `_raw_agent`.

**Agent Layout**: Keep only real business runtime agents under `agents/`.
Gateway and orchestration services belong under `services/`; reusable support
capabilities belong under `shared/capabilities/`. Root-level `agents/*`
packages must be deployable agents with stable runtime identifiers, not
compatibility aliases. Within an agent package, external HTTP/SDK clients live
under `adapters/`; `core/` should depend on ports or injected collaborators.
Feishu card schema builders and reusable Feishu card renderers are shared
platform integration capabilities under `shared/integrations/feishu/cards/`;
agent and gateway code should inject them through service-local ports.

**Human-in-the-Loop**: Finance | Legal | Customer | Technical (must approve)

**Python**: Async I/O | `model_dump_json()` | Repository pattern | Never log secrets

## Part 5: Operational Commands

```bash
make test                                          # Python tests
make dev                                           # uvicorn --reload (requirement manager agent)
make rust-gateway-run                              # Rust gateway
make frontend-dev                                  # Next.js dev
make up                                            # Docker Compose Cell stack
make up-dev                                        # Alias for make up
make up-infra                                      # Infrastructure only (PG/Redis/NATS/Milvus)
make proto                                         # Generate all protobuf code
make grpc-server                                   # Run gRPC server
make build                                         # Build Docker images
make monitoring-up                                 # Observability stack
make load-smoke                                    # k6 smoke test (10 VUs)
make clean                                         # Remove all containers + prune
ruff check agents/ shared/                         # Lint
```
