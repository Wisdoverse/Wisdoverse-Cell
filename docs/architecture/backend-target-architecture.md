# Backend Target Architecture and Phased Migration Plan

Last updated: 2026-05-20

Status: Design proposal. Awaiting user confirmation before any code is
modified.

Scope: Python backend (`agents/`, `services/`, `shared/`, `migrations/`,
backend tests). Rust gateway, frontend, Docker, and CI are referenced where
they bound the design but are not redesigned here.

Inputs to this document:

- Phase 1 read-only audit:
  [`backend-architecture-analysis.md`](./backend-architecture-analysis.md).
- Existing follow-up plan:
  [`backend-evolution-plan.md`](./backend-evolution-plan.md).
- Repo architecture constitution: `AGENTS.md`, `SPEC.md`,
  `docs/overview/architecture.md`, `docs/guides/backend-boundaries.md`.

The document follows the output format requested in the senior-architect
brief. Sections 1–6 are the design. Section 7 is the explicit confirmation
gate: no code changes until the proposal in §6 is confirmed.

---

## 1. Current Architecture Understanding (当前架构理解)

### 1.1 Project Structure Overview

The backend is a modular monolith with per-runtime service shells already in
place. ~795 non-test `.py` files live under three roots:

```text
agents/                  # Real business runtime agents
  requirement_manager/   # Meetings, requirements, PRD, feedback
  pjm_agent/             # Decomposition, approval prep, reports
  qa_agent/              # Acceptance runs, quality verdicts
  dev_agent/             # Delivery tasks, workflow execution, MR handoff
services/                # Non-agent service shells
  gateways/
    user_interaction/    # Chat, Feishu webhook intake, card operations
    channel/             # Multi-channel outbound delivery
  orchestration/
    coordinator/         # Cross-boundary event dispatch
shared/                  # Reusable runtime, contracts, adapters, infra
  app/                   # create_agent_app(), AgentRuntime, plugin system
  core/                  # Abstract ports, channel/messaging contracts, ID contracts
  control_plane/         # Operating ledger: companies, goals, runs, approvals, budgets, audit
  capabilities/{sync,analysis,evolution}/   # Support capability modules
  messaging/{inbound,outbound}/             # Messaging orchestration
  integrations/{feishu,wecom,...}/          # Platform adapters + Feishu card builders
  infra/                 # AgentClient, EventBus, LLMGateway, CircuitBreaker
  schemas/               # Pydantic event payloads, agent + error schemas
  observability/         # Structured logging, tracing, privacy
  middleware/            # FastAPI middleware (request id, error handler)
  db/                    # Shared db primitives, user store
  models/                # Shared Pydantic models (User, Platform)
  services/              # Deprecated compatibility re-exports
  utils/                 # Pure helpers (3 files)
  evolution/             # Three-level self-evolution data + collaboration
migrations/              # Single Alembic directory (19 versions)
rust/gateway/            # Rust + Axum edge gateway (out of scope)
frontend/                # Next.js operator console (out of scope)
docker/, infra/, docs/, tests/, plugins/, scripts/, conftest.py, ...
```

### 1.2 Main Modules

| Module | Path | Business focus |
|--------|------|----------------|
| Requirement Manager | `agents/requirement_manager/` | Meeting ingestion, requirement lifecycle, PRD, feedback |
| PJM Agent | `agents/pjm_agent/` | Decomposition, alerts, reports, approval prep |
| QA Agent | `agents/qa_agent/` | Acceptance runs, quality results |
| Dev Agent | `agents/dev_agent/` | Delivery tasks, workflow execution, MR handoff |
| User Interaction Gateway | `services/gateways/user_interaction/` | Chat surface, Feishu webhook intake |
| Channel Gateway | `services/gateways/channel/` | Outbound multi-channel delivery |
| Coordinator | `services/orchestration/coordinator/` | Cross-boundary event classification + dispatch |
| Sync Capability | `shared/capabilities/sync/` | OpenProject ↔ Feishu Bitable projection |
| Analysis Capability | `shared/capabilities/analysis/` | Risk detection, report generation |
| Evolution Capability | `shared/capabilities/evolution/` | L1/L2/L3 evolution proposals |
| Control Plane Ledger | `shared/control_plane/` | Companies, goals, work items, runs, approvals, budgets, artifacts, audit, evolution |
| Identity / User | `shared/db/user_store.py`, `shared/messaging/inbound/user_service.py` | Platform user identity |

### 1.3 Tech Stack

- FastAPI for HTTP entry per service.
- SQLAlchemy 2.x async + PostgreSQL 18; per-runtime DB users (ADR-0002).
- pydantic v2 + pydantic-settings.
- Redis 8 + Redis Streams EventBus with consumer groups and `dlq.failed`
  (ADR-0001).
- NATS JetStream optional, exposed through the same EventBus protocol.
- Milvus for vectors.
- LiteLLM via `shared.infra.llm_gateway` (only allowed LLM boundary).
- gRPC for selected internal RPCs (`requirement_manager/grpc/`).
- structlog for structured logs; OpenTelemetry optional; no Prometheus
  exporter present today.
- Alembic for migrations (single directory, 19 versions).
- Traefik v3 for routing; Rust + Axum gateway at the edge.
- Tests: pytest, async pytest, `tests/unit/test_architecture_boundaries.py`
  (4583 LOC) enforcing ~10 boundary rule categories.

### 1.4 Current Layering

Post-PR #121, each agent ships the same internal shape:

```text
agents/<agent>/
  api/         # FastAPI routers (thin handlers)
  app/         # create_agent_app() wiring, runtime plugins (incl. outbox)
  core/        # *_use_cases.py, *_ports.py, *_lifecycle.py, helpers
  db/          # *_store.py, repository.py, database.py, outbox tables
  adapters/    # Agent-local external SDK / HTTP clients
  service/     # BaseAgent subclass (the "shell")
  models/      # Pydantic DTOs
  tests/       # service-local tests
```

Observed layer behavior (verified in the Phase 1 audit):

- Routes are thin (validate → use-case → response map).
- Service shells delegate to `*_use_cases.py`; not god-services.
- Use cases own orchestration and the transaction boundary (implicitly,
  via async session context manager).
- Stores are pure persistence; do not encode business rules.
- Domain rules are scattered between `*_lifecycle.py`, ports, and use
  cases. No explicit `core/domain/` layer yet.
- ORM tables and Pydantic domain models are separated (`tables.py` vs
  `models.py`). Control Plane store ports now return Pydantic domain records
  across the operator-facing aggregates; ORM rows stay inside SQLAlchemy
  store adapters and private row helpers.

### 1.5 Current Data Access

- One PostgreSQL database per agent runtime; same SQLAlchemy `Base` metadata
  is generated by per-agent `db/database.py` files. Isolation today is at
  URL/engine level, not schema-level.
- The retired `shared/control_plane/repository.py` facade has been deleted.
  SQL ownership lives in per-aggregate stores, including company, agent
  registry, prompt config, goal, work item, agent run, decision, artifact,
  approval, budget, audit event, evolution proposal, runtime operation, and
  timeline stores. New control-plane code must depend on store ports/factory
  adapters, not on a repository facade.
- Per-runtime outbox tables (`*_event_outbox`) for durable event publication;
  outbox drained by per-agent `OutboxDispatcherPlugin` every 30 s in batches
  of 100.
- Cross-runtime data reads / writes go through HTTP REST (`AgentClient`) or
  events. No cross-database joins. Analysis capability has direct read access
  to source tables today (medium-risk issue M5).
- All Alembic migrations are tracked in a single `migrations/versions/`
  directory (19 files), shared across all runtimes.

---

## 2. Current Problem Diagnosis (当前问题诊断)

Findings grouped by priority. Each item lists description, location, scope of
impact, risk level, and recommended handling.

### 2.1 P0 — Must Address Now

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P0-1 | The `shared/control_plane/repository.py` backward-compatible facade has been retired; per-aggregate stores own the SQL and tests use store factory / ports. | `shared/control_plane/*_store.py`, `shared/control_plane/store_factory.py` | Legacy callers can no longer bypass aggregate stores through the facade. | Low | Keep architecture tests blocking facade resurrection and route new access through ports/factory adapters. |
| P0-2 | Single Alembic directory holds 19 migrations for every runtime; per-runtime ownership impossible. | `migrations/versions/` | Blocks Phase 4 service-boundary evolution; any agent extraction requires global migration coordination. | High | Plan and adopt per-runtime migration ownership (separate Alembic dirs or a per-runtime migration tool) before service extraction starts. |
| P0-3 | Shared Prometheus metrics now live at the `shared.observability.metrics` boundary and cover LLM cost/tokens, event loop errors, loop breaker state, event queue length by stream, Redis DLQ length/rate, outbox dispatcher totals/duration/errors, and oldest pending outbox age per runtime. Alert rules now cover outbox backlog age and DLQ growth/retention. Remaining gap: dashboard panels and threshold tuning need production evidence. | `shared/observability/metrics.py`, `shared/observability/outbox.py`, `shared/infra/event_bus.py`, `docker/prometheus/rules/application.yml`, runtime outbox dispatch use cases, `shared/infra/metrics.py` compatibility shim | Operators have a canonical metrics and alerting boundary for sustained DLQ growth, stream backlog, and outbox backlog age before service extraction. | Low | Keep new metric definitions under `shared.observability.metrics`; add dashboard panels and tune thresholds from production evidence. |
| P0-4 | OpenTelemetry tracing now installs a runtime `TracerProvider` even when non-production lacks an exporter, and production settings fail closed without `OTEL_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT`. Remaining gap: sampling policy and trace dashboard evidence need production tuning. | `shared/observability/tracing.py`, `shared/config.py`, `docker/compose/docker-compose.app.yml` | Cross-runtime traces have a mandatory bootstrap contract before service extraction; non-prod keeps trace context without requiring a collector. | Low | Keep tracing initialized through `create_agent_app()`; add sampling policy and dashboard evidence during production hardening. |
| P0-5 | Runtime error responses use the shared structured envelope at the `create_agent_app()` boundary and base consumer contract tests cover auth, HTTPException, validation, and unexpected failures. Route-specific consumer coverage is still uneven. | `shared/api/errors.py`, `shared/middleware/error_handler.py`, `shared/app/factory.py`, `tests/integration/test_runtime_error_contract.py` | Operators have a consistent runtime body/header shape; remaining risk is direct-router test harness drift for specific routes. | Low | Keep the legacy `detail` field until clients have migrated and expand route-specific provider/consumer tests when routes change. |

### 2.2 P1 — High Priority

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P1-1 | No explicit domain layer per agent. Invariants and state transitions live in `*_lifecycle.py`, ports, and use cases mixed together. | `agents/*/core/`, `shared/control_plane/agent_run_lifecycle.py` | Use cases drift into domain ownership; rules duplicate; cross-aggregate invariants weak. | High | Introduce `core/domain/` per agent with entities, value objects, aggregates, and explicit state machines. |
| P1-2 | State transitions modeled as string comparisons; no explicit FSM. | `shared/capabilities/sync/core/engine.py:74-87`, sync `progress.py`, evolution tables `status` defaults | Adding states is unsafe; bugs that skip a state are silent; transitions are not auditable. | High | Adopt explicit state machines per aggregate (Python enum + transition table or a small library). Make every transition emit a domain event. |
| P1-3 | Closed for Control Plane: store ports and application/use-case returns now expose domain records across company, goal, work item, agent role, agent prompt config, agent run, approval, decision, artifact, budget, audit timeline, and evolution proposal surfaces. | `shared/control_plane/*_store.py`, `shared/control_plane/*_ports.py`, `shared/control_plane/domain_records.py` | ORM rows are infrastructure-private inside store adapters and private row helpers; callers no longer handle `metadata_json` or SQLAlchemy row types. | Low | Keep architecture tests blocking ORM table/`Any` returns in ports and domain-record conversion in use cases. |
| P1-4 | No HTTP contract tests per agent; no producer/consumer event contract tests. | `tests/` (no contract test directory found) | Payload-shape regressions are caught only by handwritten unit tests. | Medium | Add per-agent OpenAPI snapshot tests and producer/consumer event tests keyed off `docs/guides/event-catalog.md`. |
| P1-5 | `users` table has no dedicated public API boundary; identity reads/writes go through several paths. | `shared/db/user_store.py`, `shared/messaging/inbound/user_service.py` | Identity becomes shared mutable state if unrelated modules write directly. | Medium | Define an Identity / User service boundary with a single write owner; route all writes through it. |

### 2.3 P2 — Mid-Term Optimization

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P2-1 | Partially closed: core ledger route families now live under `shared/control_plane/api_routes/` for companies, goals, work items, decisions, and artifacts; remaining agent, run, approval, budget, evolution, and audit handlers still live in `shared/control_plane/api.py`. | `shared/control_plane/api.py`, `shared/control_plane/api_routes/*.py` | Cognitive load is lower for core ledger changes, but unrelated operational route diffs can still collide in the main API module. | Low | Continue the per-aggregate router split as cohesive route-family slices while keeping HTTP contracts unchanged. |
| P2-2 | Analysis capability can read source-domain tables directly. | `shared/capabilities/analysis/` (no projection module) | Reporting becomes implicit owner of other domains; refactors require analysis-side updates. | Medium | Introduce an explicit projection layer; let Analysis depend only on projection ports. |
| P2-3 | Sync capability hosts OpenProject and Feishu Bitable inside one runtime; sub-boundaries exist only in `core/`. | `shared/capabilities/sync/core/engine.py`, `progress.py` | Independent scaling / failure isolation impossible. | Medium | Split into two sub-capability runtimes, each with its own outbox and repository; keep a compatibility orchestrator endpoint. |
| P2-4 | Closed: retired `shared/services/*` and root `skills/*` compatibility surfaces have been removed. Tests and docs now use canonical paths, and architecture checks block reintroduction. | `shared/infra/tests/test_nats_event_bus.py`, `shared/db/tests/test_base_database_manager.py`, `tests/unit/test_architecture_boundaries.py` | New code has no compatibility import surface to couple to. | Low | Keep architecture tests blocking `shared/services` and root `skills` resurrection. |
| P2-5 | Closed: the deprecated `shared/grpc/server.py` runtime entry point has been removed; shared gRPC now keeps protocol artifacts only. | `shared/grpc/`, `agents/requirement_manager/grpc/`, `tests/integration/test_grpc_server.py` | New code has one requirements gRPC runtime entry point. | Low | Keep architecture and deprecated-import checks blocking `shared.grpc.server` imports. |
| P2-6 | Partially closed: Control Plane command routes use `ControlPlaneUnitOfWork` with explicit `commit()` and rollback-on-error cleanup; other runtime use cases still use implicit session context boundaries. | `shared/control_plane/unit_of_work.py`, `shared/control_plane/api.py`, `agents/*/core/*_use_cases.py` patterns | The central governance API now has an explicit command transaction seam; remaining multi-aggregate agent writes still need per-runtime adoption. | Medium | Keep command-route architecture tests in place and introduce per-runtime `UnitOfWork` ports where a use case touches more than one aggregate or outbox. |
| P2-7 | Closed: production settings fail closed when required secrets, internal transport protection, telemetry endpoint, control-plane approval enforcement, A2A JWT, and enabled platform callback secrets are missing or defaulted. | `shared/config.py`, `tests/unit/test_config_secrets.py` | Misconfigured production fails during settings validation instead of starting silently. | Low | Keep production-secret tests aligned with new required integrations and deployment markers. |
| P2-8 | AgentClient infrastructure exists but is barely used. Inter-agent comms is dominantly event-driven. | `shared/infra/agent_client.py:21-60`, single live caller in `agents/requirement_manager/app/plugins/feishu_gateway.py` | Not a bug, but the documented HTTP boundary is mostly aspirational for cross-agent flow. | Low | Either commit to event-first cross-agent communication explicitly, or strengthen HTTP usage for synchronous contracts (e.g., approvals). |

### 2.4 P3 — Can Be Deferred

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P3-1 | No auto-generated OpenAPI snapshots; route inventory only in `/api/v1` metadata endpoint. | `agents/requirement_manager/app/routes.py:9-25` | Discoverability cost; harder to compare external contract evolution. | Low | Add snapshot generation script; commit per-agent OpenAPI to `docs/`. |
| P3-2 | `data/` directory leaks local-only development state in some workflows. | `.gitignore`, `docs/overview/project-layout.md` | Contributor hygiene, not a code problem. | Low | Document better in contributor onboarding. |
| P3-3 | Mixed test placements: some service-local under `agents/*/tests/`, some cross-cutting in root `tests/`. | `tests/`, `agents/*/tests/` | Discovery cost only. | Low | Keep current rule documented in `project-layout.md`; do not relocate. |
| P3-4 | LLM provider fallback policy is hardcoded inside the gateway. | `shared/infra/llm_gateway.py` | Operator control limited; A/B model strategy requires code change. | Low | Move policy to control-plane configuration once budget evidence is fully integrated. |

---

## 3. Bounded Context Analysis (领域边界分析)

The contexts below are derived from the current code and table ownership.
Each context lists: responsibility, business objects, owned data, exposed
capabilities, external dependencies, current boundary clarity, and split
fitness. The capability/runtime mapping matches
`docs/guides/backend-boundaries.md` §2.

### 3.1 Control Plane / Governance

- **Responsibility**: durable operating ledger for the whole company.
- **Business objects**: Company, Goal, AgentRole, WorkItem, AgentRun,
  Decision, ApprovalRequest, BudgetPolicy, BudgetUsage, Artifact, AuditEvent,
  EvolutionProposal, AgentPromptConfig.
- **Owned data**: `control_plane_*` tables.
- **Capabilities exposed**: `/api/v1/control-plane/*` REST surface,
  work-item operation commands and activity feeds, `runtime.agent` wakeups,
  run evidence APIs, budget enforcement, approval gates.
- **External dependencies**: business agents emit runs / artifacts / audit
  events; LLM gateway emits budget usage; gateways consume approvals.
- **Boundary clarity**: high. Single owner. Internal SQL ownership is behind
  per-aggregate ports/stores; the retired repository facade no longer exists.
- **Split fit**: must remain central in the foreseeable future. Splitting
  the ledger fragments the operator model.

### 3.2 Requirement Management

- **Responsibility**: turn meetings and user intent into structured
  requirements, manage PRD flow, learn from feedback.
- **Business objects**: Meeting, Requirement, OpenQuestion, FeedbackRecord,
  ChatMessage, LlmUsage.
- **Owned data**: `meetings`, `requirements`, `open_questions`,
  `feedback_records`, `llm_usage`, `chat_messages`,
  `requirement_event_outbox`.
- **Capabilities exposed**: requirement REST + gRPC, requirement events
  (`requirement.*`), Feishu card flow.
- **External dependencies**: LLM gateway, Feishu integration, control plane
  (runs/audit).
- **Boundary clarity**: high. Single runtime owner.
- **Split fit**: good future service. Pre-conditions: own migrations,
  projection for analytics, contract tests, OpenAPI snapshot.

### 3.3 Planning / PJM

- **Responsibility**: decompose work, prepare approvals, surface reports and
  alerts.
- **Business objects**: DecompositionRecord, AlertLog, ConfigCache.
- **Owned data**: `pjm_agent_*` tables.
- **Capabilities exposed**: decomposition REST, PJM events, OpenProject
  handoff.
- **External dependencies**: requirement events, OpenProject (via sync),
  control plane (approvals, budgets).
- **Boundary clarity**: medium-high. Strong runtime boundary; some
  capability coupling with sync.
- **Split fit**: candidate after decomposition lifecycle is fully
  state-machine-modeled and OpenProject contracts are explicit.

### 3.4 Delivery / Dev

- **Responsibility**: run delivery tasks, execute workflows, hand off to MR
  and QA.
- **Business objects**: DevTask, WorkflowLog.
- **Owned data**: `dev_agent_*` tables.
- **Capabilities exposed**: delivery REST, dev events, MR handoff, QA
  request.
- **External dependencies**: GitLab, AgentForge, control plane, QA.
- **Boundary clarity**: high.
- **Split fit**: strong service candidate (long-running workflows want
  independent scaling). Pre-conditions: own migrations, projection for
  reporting, replay strategy.

### 3.5 Quality / QA

- **Responsibility**: run acceptance, produce quality verdicts.
- **Business objects**: AcceptanceRun, AcceptanceResult.
- **Owned data**: `qa_acceptance_*`, `qa_agent_event_outbox`.
- **Capabilities exposed**: QA REST, QA events, acceptance results.
- **External dependencies**: dev events, control plane.
- **Boundary clarity**: high. Idempotency contract already explicit.
- **Split fit**: strong service candidate once trigger contracts and
  idempotency keys are documented as public.

### 3.6 Sync / Projection

- **Responsibility**: project OpenProject ↔ Feishu Bitable, manage sync
  locks, propagate progress backflow.
- **Business objects**: SyncMapping, SubtaskMapping, SyncLock, SyncLog.
- **Owned data**: `sync_agent_*` tables.
- **Capabilities exposed**: sync trigger commands, sync status, sync events.
- **External dependencies**: OpenProject, Feishu Bitable, PJM.
- **Boundary clarity**: medium. Two sub-boundaries (OpenProject side,
  Feishu Bitable side) live in one runtime; split exists in `core/` only.
- **Split fit**: should become two sub-capability runtimes (P2-3). Keep an
  orchestrator endpoint for callers that need both.

### 3.7 Interaction / Channel Gateway

- **Responsibility**: receive inbound chat / webhook traffic and deliver
  outbound messages across channels.
- **Business objects**: ConversationHistory, CardOperation, DailyProgress.
- **Owned data**: `chat_agent_*`, `channel_gateway_event_outbox`.
- **Capabilities exposed**: chat REST/webhooks, outbound card operations,
  channel messages.
- **External dependencies**: Feishu, WeCom, business agents (downstream
  recipients of intent), control plane.
- **Boundary clarity**: medium. Two gateway services + chat-agent share
  responsibilities; gateway must not own product-domain records.
- **Split fit**: gateway boundary, not a business context. Keep as-is.

### 3.8 Coordination / Orchestration

- **Responsibility**: classify and dispatch cross-boundary events; keep
  scratchpad and short-term state for coordination decisions.
- **Business objects**: CoordinatorEventOutbox, scratchpad, agent-state
  store (port-backed).
- **Owned data**: `coordinator_event_outbox`; durable backing of scratchpad
  and state store needs to be confirmed (open question §3 in Phase 1).
- **Capabilities exposed**: cross-boundary dispatch events.
- **External dependencies**: all business agents, LLM (thinker), control
  plane.
- **Boundary clarity**: medium. Durable-state backing is implicit.
- **Split fit**: not a candidate for split until durable state and replay
  contracts are explicit.

### 3.9 Analytics / Reporting

- **Responsibility**: generate risk and operating reports from operational
  evidence.
- **Business objects**: AnalysisReportLog.
- **Owned data**: `analysis_agent_*`.
- **Capabilities exposed**: analysis REST, analysis events.
- **External dependencies**: requirement, PJM, dev, QA tables (currently
  direct read).
- **Boundary clarity**: low. Reads cross domain tables; no projection
  layer.
- **Split fit**: projection / read-model service candidate. Must stop
  direct source-table reads before any split.

### 3.10 Evolution

- **Responsibility**: produce L1 (skill), L2 (architecture), L3
  (collaboration) evolution proposals; capture traces, reflections,
  experiments.
- **Business objects**: EvolutionTrace, Reflection, Experiment,
  SkillConfig, CollaborationPattern, Memory, EvolutionProposal.
- **Owned data**: `evolution_*` tables.
- **Capabilities exposed**: evolution REST + events; proposals surface via
  control plane.
- **External dependencies**: control plane (proposals, approvals),
  business runtimes (traces).
- **Boundary clarity**: medium. Self-evolution code split between
  `shared/evolution/` and `shared/capabilities/evolution/` historically.
- **Split fit**: keep guarded; only split after approval/rollback contracts
  are hardened.

### 3.11 Identity / User

- **Responsibility**: platform user identity, lookup, and link to runtime
  context.
- **Business objects**: User, Platform.
- **Owned data**: `users` (single table; no dedicated API today).
- **Capabilities exposed**: identity lookup through messaging-inbound and
  shared user store.
- **External dependencies**: every runtime that needs user context.
- **Boundary clarity**: low. Multiple read paths; one historical write
  path; no public API.
- **Split fit**: define the public boundary first (P1-5). Splitting can wait
  until the API contract is durable.

### 3.12 Integration Plane (Feishu / WeCom / OpenProject / GitLab / AgentForge)

- **Responsibility**: external platform adapters; not a business context.
- **Owned data**: none of its own (token caches treated as infrastructure).
- **Boundary clarity**: high. Single canonical location under
  `shared/integrations/`. Feishu card builders centralized.
- **Split fit**: never a separately deployed service; treat as adapter
  library.

---

## 4. Target Architecture Proposal (目标架构建议)

### 4.1 Overall Architecture

Stay a **modular monolith** for the next 6–9 months. Improve internal seams
until they are strong enough that a single agent runtime can be lifted out
without coordinated migrations. Two services already justified for
extraction (Dev, QA) become candidates only after Stages 0–3 of the
roadmap land.

```text
┌─────────────────────────────────────────────────────────────────┐
│ Rust Edge Gateway (Axum) — TLS, webhook signature, gRPC fan-out │
└───────────────────────┬─────────────────────────────────────────┘
                        │
        ┌───────────────┴──────────────────────────┐
        │                                          │
┌───────▼────────┐                       ┌─────────▼──────────┐
│ Operator API   │                       │ Agent API surface  │
│ /api/v1/       │                       │ /agent/<id>/*      │
│ control-plane  │                       │                    │
└───────┬────────┘                       └─────────┬──────────┘
        │                                          │
        ▼                                          ▼
┌────────────────────────────────────────────────────────────┐
│ Application Layer (Python)                                  │
│   - Business runtime agents (requirement, pjm, qa, dev)     │
│   - Gateways (user_interaction, channel)                    │
│   - Orchestration (coordinator)                             │
│   - Capabilities (sync, analysis, evolution)                │
└──────────┬────────────────────┬────────────────────┬───────┘
           │                    │                    │
           ▼                    ▼                    ▼
   ┌───────────────┐   ┌────────────────┐   ┌──────────────┐
   │ Control Plane │   │ EventBus       │   │ LLM Gateway  │
   │ Ledger        │   │ (Redis Streams)│   │ (LiteLLM)    │
   └───────┬───────┘   └───────┬────────┘   └──────┬───────┘
           │                   │                   │
           ▼                   ▼                   ▼
   ┌──────────────────────────────────────────────────────┐
   │ Storage: PostgreSQL (per-runtime DBs), Redis, Milvus  │
   │ + per-runtime *_event_outbox tables                   │
   └──────────────────────────────────────────────────────┘
```

### 4.2 Module Structure (Recommended)

Each business runtime keeps the package shape established by PR #121, plus
an explicit `core/domain/` layer:

```text
agents/<agent>/
  api/                  # interfaces: FastAPI routers, request/response DTOs
  app/                  # interfaces: create_agent_app(), plugins, lifespan
  core/
    domain/             # NEW: entities, value objects, aggregates, FSMs, domain events
    use_cases/          # application: orchestration, command/query handlers
    ports/              # application: outbound port interfaces (Protocols)
    services/           # OPTIONAL: domain services that span aggregates
  db/                   # infrastructure: SQLAlchemy tables, stores, outbox
  adapters/             # infrastructure: external SDK / HTTP clients
  service/              # application/runtime: BaseAgent shell (delegates only)
  models/               # interfaces: shared Pydantic DTOs (deprecated location; migrate to api/)
  tests/                # unit + use-case tests
```

The control plane keeps its existing layout; per-aggregate stores own SQL and
return domain records from their public ports.

### 4.3 DDD Layering (Recommended Responsibilities)

| Layer | Responsibilities (must) | Forbidden |
|-------|-------------------------|-----------|
| **interfaces** (`api/`, `app/`, gRPC, MQ adapters) | HTTP / RPC / MQ entry; DTO conversion; auth/dependency wiring; error mapping; response shaping. | No business rules; no SQL; no direct ORM Session except behind a port; no transaction control. |
| **application** (`core/use_cases/`, `core/ports/`, `service/`) | Orchestrate use cases; own transaction boundary; build commands/queries; emit domain events; talk to ports. | No DB rows; no Pydantic ORM mixing; not a god service (one use-case = one purpose). |
| **domain** (`core/domain/`) | Entities, value objects, aggregates, invariants, state machines, domain events, domain services that span aggregates. | No `shared.db`, no SQLAlchemy import, no HTTP client, no LLM SDK, no config import. |
| **infrastructure** (`db/`, `adapters/`, integrations, LLM gateway, EventBus client) | Implement ports; persist rows; call external systems; cache; configure. Owns timeouts, retries, idempotency, circuit breakers. | No domain decisions; no orchestration; no business rules. |

Cross-cutting rules (binding):

1. interfaces layer must not write business rules.
2. application service must not become a god service. Split by use-case
   intent, not by entity.
3. repository interface and implementation must live on opposite sides of the
   ports/adapters seam.
4. state transitions are explicitly modeled in the domain layer; status
   strings are not allowed to drive behavior outside the FSM definition.
5. external calls (HTTP, LLM, queue, third-party SDKs) must declare
   timeout, retry policy, failure classification, and idempotency strategy.
6. domain layer must not import from infrastructure or interfaces.
7. tests at each layer use the layer below through ports; integration tests
   wire real implementations.

### 4.4 Service Boundaries (Recommended Evolution)

Today: modular monolith. Recommended next 6 months: **stay modular monolith
but harden seams**.

Decision matrix per candidate (from §3 + Phase 1 H1):

| Candidate | Clear domain boundary | Independent data ownership | Independent deploy need | Independent scale need | Failure isolation need | Different change rate | Performance bottleneck | Collaboration bottleneck | Over-split risk | Recommendation |
|-----------|-----------------------|---------------------------|------------------------|-----------------------|----------------------|----------------------|------------------------|--------------------------|-----------------|----------------|
| Dev Agent | Yes | Yes (own outbox + tables) | Soon (long workflows) | Yes (workflow burst) | Yes (workflow failures must not block QA) | Yes | Likely (workflow concurrency) | Medium | Low | Extract after Stage 3 complete |
| QA Agent | Yes | Yes | Soon (acceptance bursts) | Yes | Yes | Yes | Possible | Medium | Low | Extract after Stage 3 complete |
| Sync — OpenProject | Yes | Yes (within sync schema) | Medium | Medium | Yes (Feishu outage must not stop OpenProject) | Yes | Possible | Low | Medium | Sub-runtime split before full extraction |
| Sync — Feishu Bitable | Yes | Yes | Medium | Medium | Yes | Yes | Possible | Low | Medium | Sub-runtime split before full extraction |
| Coordinator | Medium | Partial | Low | Low | Yes (cross-boundary blast radius) | Medium | No | Medium | Medium | Keep modular; stabilize durable state first |
| Analysis | Medium | Partial (no projection today) | Low | Low | Yes | Low | No | Low | High | Keep modular; build projection first |
| Evolution | Medium | Yes (own tables) | Low | Low | Yes (proposal flow needs guardrails) | Low | No | Low | Medium | Keep modular; harden approval/rollback first |
| Requirement Manager | Yes | Yes | Medium | Medium | Yes | Yes | No | Medium | Medium | Keep modular; extract after Dev/QA pattern proves |
| PJM | Yes | Yes | Low | Low | Yes | Medium | No | Medium | Medium | Keep modular; pair with sync sub-split |
| Identity / User | No (no public API) | Partial | Low | Low | Yes | Low | No | Low | High | Define API first; do not split runtime |

Rule of thumb: extract only when **all four** of these are true: (a) outbox
+ projection + idempotency + replay are in place; (b) per-runtime
migrations land cleanly; (c) operator dashboards (metrics + tracing) cover
the boundary; (d) at least one non-production deployment proves the split
under realistic load. None of the candidates above pass all four today.

### 4.5 Data Ownership (Target)

Target ownership matches the bounded contexts in §3 and the table matrix in
`docs/guides/backend-boundaries.md` §3. Key target rules:

1. Each runtime owns its tables. Cross-runtime reads are illegal except via
   API, RPC, EventBus, or an explicit read-only projection table.
2. Outbox per runtime. Same DB today; one DB per runtime after Stage 4.
3. Analysis must consume only projections, never source tables (P2-2 target).
4. `users` becomes an Identity boundary with a single write path
   (P1-5 target).
5. Sync's OpenProject and Feishu Bitable sub-aggregates own separate
   sub-schemas; the orchestrator endpoint joins via APIs, not by reading
   each other's tables.
6. Cross-aggregate writes within a single boundary go through one use case;
   no transaction spans two runtimes.
7. No new shared ORM Entity is used as a cross-service contract. Cross-
   boundary contracts are events (preferred) or HTTP DTOs (for sync calls).
8. Migrations are owned per runtime once Stage 4 starts. Up to that point,
   a single global migration chain is the contract.
9. Distributed transactions are out of scope. Use one local transaction
   plus outbox/projection.
10. Projections are append/replace tables maintained by an event consumer
    or scheduled job; they never become a write owner.

### 4.6 API and Event Design (Recommended)

#### 4.6.1 API

- Versioning: keep `/api/v1/*` for public surfaces; introduce `/api/v2/*`
  only for breaking changes that cannot be done with additive evolution.
- DTOs: per-agent Pydantic models in `api/` (or `models/`). One DTO per
  request/response. Internal agent DTOs are not shared across runtimes.
- Error codes: extend `ApiErrorCode` enum (currently 56 codes in
  `shared/api/errors.py`) to all agents. Use namespaced codes
  (`<runtime>.<category>.<specific>`).
- Uniform response envelope: keep the existing FastAPI `detail` string for
  backward compatibility; add a structured body
  `{ "code": str, "message": str, "trace_id": str, "details": object|null }`
  in parallel; switch clients module by module. Documented in
  `docs/guides/api-reference.md`.
- Documentation: generate per-agent OpenAPI snapshots and commit them under
  `docs/` so contract changes show up in PR diffs.

#### 4.6.2 Events

- Two event categories:
  - **Domain events**: internal to one boundary. Never published to the
    EventBus. Used inside use cases to compose aggregate behavior.
  - **Integration events**: published through the EventBus; documented in
    `docs/guides/event-catalog.md`; payload model lives in
    `shared/schemas/event_payloads.py`.
- Naming: `{domain}.{action}` past-tense, already enforced.
- Schema versioning: `schema_version` is required; bump on
  backward-incompatible change; add producer/consumer contract tests.
- Idempotency: stable `event_id` (`evt_*`) **and** a domain idempotency key
  documented per event row in the catalog. Consumers must be idempotent.
- Retries: outbox handles publication retries; consumer retries follow
  the consumer-group convention; dead letters land in `dlq.failed`.
- Failure handling: handler failures must log classification + retry
  decision and increment outbox `retry_count`. The runtime plugin already
  exposes total/published/failed counts.

#### 4.6.3 Documentation Discipline

- Every new public HTTP route and every integration event must update the
  matching doc in the same PR.
- `tests/unit/test_architecture_boundaries.py` already enforces the
  outbox-as-publish path. Add a similar test that asserts every event
  listed in the catalog has a matching payload model.

### 4.7 Testing Strategy (Recommended)

Goal: every boundary has tests at the right level. Mirrors the brief's
10-item list.

| # | Test type | Purpose | Location | Recommended depth |
|---|-----------|---------|----------|-------------------|
| 1 | Domain unit tests | Verify entity invariants, value object equality, FSM transitions | `agents/<agent>/tests/unit/domain/` | One per aggregate + one per state machine |
| 2 | Use-case tests | Verify orchestration, transaction boundary, port interactions | `agents/<agent>/tests/unit/use_cases/` | One per use case; ports mocked |
| 3 | Repository / store integration tests | Verify SQL against real Postgres | `agents/<agent>/tests/integration/db/` and `tests/integration/` | Real Postgres on CI (testcontainers); avoid mocks here |
| 4 | API contract tests | Verify HTTP shape per route; OpenAPI snapshot diff | `tests/contract/http/` | One snapshot file per agent per version |
| 5 | Message consumer tests | Verify each consumer handles published payload shapes | `tests/contract/events/` | One producer + one consumer test per integration event |
| 6 | Migration tests | Verify Alembic up + down for the latest migrations | `tests/integration/migrations/` | Run on CI before each release |
| 7 | Critical flow E2E | End-to-end golden path: meeting → requirement → PRD → decomposition → delivery → QA | `tests/e2e/` | One golden-path test per quarter, plus per-runtime ready/wakeup smoke |
| 8 | Regression tests | Capture every fixed bug as an assertion to prevent recurrence | beside the related unit/use-case test | mandatory in bugfix PRs |
| 9 | Mocking strategy | Mock at the port boundary only. Never mock SQLAlchemy or HTTP libs directly inside a test; mock the port. | — | Documented in `docs/guides/agent-development.md` |
| 10 | Test data strategy | Use factory-style helpers under `tests/factories/`; never reuse production fixtures; clean per-test isolation; deterministic IDs via `shared.core.ids` | `tests/factories/`, `tests/helpers/` | Documented in same guide |

### 4.8 Observability Strategy (Recommended)

The brief's 10-item observability list maps to the following minimum bar.

| # | Requirement | Concrete target | Code path |
|---|-------------|-----------------|-----------|
| 1 | requestId / correlationId | `X-Trace-ID` from `RequestIdMiddleware`; propagated to outbound HTTP + EventBus event metadata | `shared/middleware/__init__.py` already provides; extend to outbound |
| 2 | Structured logging | structlog JSON + bound context (`trace_id`, `agent_id`, `work_item_id`, `run_id`, `approval_id`) | `shared/utils/logger.py`, `shared/observability/` |
| 3 | Key business ID logging | Every use case logs `run_id`, `work_item_id`, `goal_id`, `approval_id` on entry/exit | Add a logging helper used by all use cases |
| 4 | Error logs | Classified errors (use `ApiErrorCode`); never log raw secrets; include `trace_id` + retry decision | `shared/api/errors.py`, `shared/middleware/error_handler.py` |
| 5 | External call latency | Histogram per integration call (Feishu, OpenProject, GitLab, AgentForge, LLM) | `shared/observability/metrics.py` plus integration-specific adapters |
| 6 | DB slow query | Log queries above N ms; emit `db_query_duration_seconds` histogram | `shared/db/` SQLAlchemy event hook |
| 7 | MQ consumer state | Outbox-lag gauge, per-stream queue length, `dlq.failed` length/rate, consumer group pending count | `shared.observability.metrics` exposes event queue, DLQ, and oldest pending outbox age collectors |
| 8 | Task processing state | Per-use-case state-transition counter + duration histogram; per-agent task throughput | New metric + log convention |
| 9 | Key endpoint P95/P99 | Per-route latency histogram; SLO target documented in `docs/guides/operations.md` | FastAPI middleware metric |
| 10 | Failure rate + alerting | Outbox failure rate, DLQ rate, LLM budget breach, approval timeout — all alerted | `docker/prometheus/rules/application.yml`; tune thresholds in `docs/guides/operations.md` |

Implementation choice (recommend committing to it in Stage 0):

- **Tracing**: OpenTelemetry traces always-on with a no-export fallback in
  non-production; production settings require `OTEL_ENDPOINT` or
  `OTEL_EXPORTER_OTLP_ENDPOINT`.
- **Metrics**: Prometheus exposition via a FastAPI `/metrics` endpoint on
  every agent and gateway (gated by an internal auth key); future OTel
  metrics pipeline once Prometheus baseline is stable.
- **Logs**: structlog JSON. No new framework.

---

## 5. Phased Migration Roadmap (渐进式改造路线)

Six stages. Each stage states goal, scope, verification, risk, and done
criteria. Stages 0 and 1 are non-behavior-changing and can ship first; later
stages depend on the seams the earlier stages established.

### 5.1 Stage 0 — Architecture Docs and Standards (建立架构文档和规范)

- **Goal**: lock the contract the rest of the work runs against.
- **Scope (deliverables)**:
  1. `docs/architecture/architecture-principles.md` (the 10 binding rules
     from §4.3 + the constraints from the brief, made executable).
  2. `docs/architecture/module-boundaries.md` (consolidated view of §3, with
     responsibility / data / deps / split criteria per context).
  3. `docs/architecture/service-boundaries.md` (the matrix in §4.4).
  4. `docs/architecture/data-ownership.md` (the rules in §4.5; links to
     `docs/guides/backend-boundaries.md` §3).
  5. `docs/architecture/api-guidelines.md` (§4.6.1).
  6. `docs/architecture/event-guidelines.md` (§4.6.2).
  7. `docs/architecture/testing-strategy.md` (§4.7).
  8. `docs/architecture/observability-guidelines.md` (§4.8).
  9. `docs/architecture/architecture-review-checklist.md` (a checklist
     used in every architecture-affecting PR).
  10. `docs/architecture/migration-plan.md` (the contents of §5 as a
      standalone, linked document).
- **Will not change**: any code, schema, route, event, configuration, or
  runtime artifact.
- **Risk**: low. Documentation only.
- **Verification**: `git diff --check`; internal link resolver; reviewer
  acceptance of each doc.
- **Done criteria**: all 10 docs merged on `main`; `docs/INDEX.md` updated;
  `AGENTS.md` references them under the architecture-constitution section.

### 5.2 Stage 1 — Code Structure Cleanup (整理现有代码结构)

- **Goal**: tighten module boundaries without touching business behavior.
- **Scope**:
  1. Add an explicit `core/domain/` directory per agent (empty at first;
     no class moves yet — just the package).
  2. Move `*_lifecycle.py` files into `core/domain/lifecycle/`.
  3. Hide `AsyncSession` from route handlers in `shared/control_plane/api.py`.
     Read routes receive store factories; command routes receive
     `ControlPlaneUnitOfWork` and explicitly commit successful mutations.
  4. Continue splitting `shared/control_plane/api.py` into per-aggregate
     routers under `shared/control_plane/api_routes/` (file move; no logic
     or HTTP contract change).
  5. Add minimum tests around the use cases touched in (3) and (4).
  6. Add `trace_id`, `agent_id`, and `run_id` logging on every use case
     entry/exit (per §4.8 item 3) using a small helper.
- **Will not change**: HTTP routes, request/response shapes, event names,
  payload schemas, database schema, business behavior.
- **Risk**: medium. File moves can break test discovery and CI cache; the
  session-provider port introduces a new internal contract.
- **Verification**:
  - Full `make test` regression must match baseline (1860 passed / 15
    skipped / 183 deselected).
  - `tests/unit/test_architecture_boundaries.py` must still pass and grow
    to assert the new rules (e.g., no `AsyncSession` in route signatures).
  - Manual curl/HTTP smoke against `/api/v1/control-plane/*` to confirm
    response shapes unchanged.
- **Done criteria**: regression green; architecture-boundary tests cover
  the new rules; PR descriptions cite the rules added.

### 5.3 Stage 2 — Core Domain Modeling (明确核心领域模型)

- **Goal**: turn the implicit domain into explicit code.
- **Scope** per business runtime (one PR per aggregate to keep diffs small):
  1. Identify the aggregate root (e.g., `Requirement`, `DevTask`,
     `AcceptanceRun`, `DecompositionRecord`, `AgentRun`).
  2. Define entities, value objects, and aggregate boundaries.
  3. Define an explicit state machine (allowed transitions, illegal
     transitions raise a typed domain error).
  4. Move state-transition decisions out of use cases and stores into the
     aggregate.
  5. Introduce domain events (in-memory) and let use cases collect them
     for outbox publication.
  6. Keep public HTTP and event payloads unchanged.
- **Will not change**: APIs, event payloads, DB schema, business
  behavior.
- **Risk**: medium. Behavior must remain identical; any state-machine
  refactor risks subtle differences.
- **Verification**:
  - Domain unit tests per aggregate (§4.7 #1).
  - Use-case tests asserting the same observable outcomes as before
    (snapshot/regression tests on responses + emitted events).
  - Per-aggregate FSM coverage matrix in the PR description.
- **Done criteria**: every business runtime has a non-empty `core/domain/`
  with an aggregate, an FSM, and matching unit tests.

### 5.4 Stage 3 — Data Ownership and Boundaries (明确数据归属和边界)

- **Goal**: enforce the data-ownership rules from §4.5.
- **Scope**:
  1. Confirm one write owner per table; update
     `docs/guides/backend-boundaries.md` §3 if any row is wrong.
  2. Introduce an explicit projection table for Analysis (P2-2). One
     projection per source domain it currently reads.
  3. Introduce an Identity / User write-owner path (P1-5).
  4. Move ORM types out of business-logic returns (P1-3): Control Plane store
     ports and application use cases return domain models. ORM rows are
     infrastructure-private inside SQLAlchemy adapters and private row helpers.
  5. Add a CI rule to `tests/unit/test_architecture_boundaries.py` that
     forbids cross-runtime ORM imports in the application layer.
- **Will not change**: HTTP routes (additive only), event payloads
  (additive only), running migrations are additive (new projection tables),
  no in-place column changes.
- **Risk**: medium-high. Touches more code; projection roll-forward needs
  one operator step.
- **Verification**:
  - Migration test on the new projection tables.
  - Provider/consumer event tests for the events that drive projection
    inserts.
  - Backfill script idempotency test.
- **Done criteria**: Analysis depends only on projection ports; Identity
  has a single public API; architecture-boundary test forbids the
  remaining cross-runtime ORM access.

### 5.5 Stage 4 — Service Boundary Evolution (服务边界演进)

- **Goal**: split the first one or two runtimes once the seams are ready.
- **Scope** (per service to extract):
  1. Move that runtime to its own Alembic directory (or per-runtime
     migration tool) — closes H1 / P0-2.
  2. Switch from in-process subscribe to remote EventBus consumer group;
     verify replay + DLQ.
  3. Publish per-agent OpenAPI snapshot; lock contract.
  4. Deploy as a separate container in staging; run the canary monitor.
  5. Document rollback: revert the container to the bundled `cell`
     topology and replay events from outbox.
- **Will not change**: public HTTP routes, public event payloads, control
  plane ledger contract.
- **Risk**: high. First extraction is the riskiest. Pick Dev or QA first
  (per §4.4 matrix).
- **Verification**:
  - Stage-3 done criteria all hold.
  - Smoke tests on the new container in staging for at least two weeks
    with outbox-lag, DLQ-rate, and LLM cost dashboards green.
  - Documented rollback exercised once in staging.
- **Done criteria**: one runtime runs independently in staging with
  bounded outbox lag, no DLQ growth, observable SLIs meeting their SLOs.

### 5.6 Stage 5 — Engineering Quality (工程质量提升)

- **Goal**: lock the engineering bar so later stages do not regress.
- **Scope** (10 items from the brief):
  1. CI: keep the existing GitHub Actions pipeline; add per-runtime tests.
  2. Lint: `ruff` already in use; promote warnings to errors in two
     reviewed PRs.
  3. Type check: add `mypy` (or `pyright`) on `shared/control_plane/`,
     `shared/core/`, and one agent first; expand gradually.
  4. Test: keep `make test` as the canonical regression gate; expand
     contract + projection tests.
  5. Migration check: CI runs Alembic up + down on every PR that touches
     `migrations/`.
  6. Dependency check: Dependabot already wired (see today-2026-05-18 memory
     for chore/dependabot-config); ensure security alerts route to
     Issues.
  7. Security baseline: continue secret-detection and PII tests; add
     scheduled `cso` mode runs.
  8. Release checklist: documented in `docs/guides/operations.md`; gated
     by the architecture-review checklist from Stage 0.
  9. Rollback checklist: per-runtime; documented as part of Stage 4
     extraction.
  10. Incident runbook: extend `docs/guides/incident-response.md` to cover
      outbox lag, DLQ overflow, LLM budget breach.
- **Will not change**: any business behavior; this stage is gate
  hardening.
- **Risk**: low to medium; type-check rollout can be noisy.
- **Verification**: every gate is enforced in CI and has a documented
  override path.
- **Done criteria**: every architecture-affecting PR passes the gate set
  defined here without manual exceptions.

---

## 6. First Minimal Step Proposal (第一阶段最小改造方案)

### 6.1 Why This First

Stage 0 (architecture docs + standards) is the smallest, safest,
verifiable step that materially advances every later stage:

1. It is documentation-only. No business behavior changes.
2. It does not change any public HTTP route, event, database schema,
   configuration, or runtime artifact.
3. It introduces no new framework or dependency.
4. It has no production blast radius.
5. It is fully reviewable through `git diff --check` plus link resolution.
6. It produces the contract that every later code change must conform to.
   Without it, Stage 1 refactors risk introducing the wrong abstractions.

Alternative considered — start with code (e.g., apply P1-3 ORM-type
cleanup immediately). Rejected because it would commit code shape decisions
before the principles are documented and accepted. Likely rework cost is
higher than the cost of an extra docs PR.

### 6.2 Files to Add

The minimal first step ships **10 new files under `docs/architecture/`**,
plus updates to `docs/INDEX.md` and a one-line link from `AGENTS.md`. No
existing source code or docs are modified beyond those two references.

| File | Why |
|------|-----|
| `docs/architecture/architecture-principles.md` | Codify the 10 binding rules from §4.3 + the 20 constraints from the brief. Becomes the architecture constitution that every PR cites. |
| `docs/architecture/module-boundaries.md` | Consolidate §3 bounded context analysis into one operator-and-engineer-readable document. Links to `docs/guides/backend-boundaries.md` for table ownership. |
| `docs/architecture/service-boundaries.md` | The §4.4 matrix as a standalone doc. Used by every "should we split X?" question. |
| `docs/architecture/data-ownership.md` | §4.5 rules; cross-links to the table matrix in `backend-boundaries.md` §3. |
| `docs/architecture/api-guidelines.md` | §4.6.1; the contract every new HTTP route conforms to. |
| `docs/architecture/event-guidelines.md` | §4.6.2; the contract every new EventBus event conforms to. |
| `docs/architecture/testing-strategy.md` | §4.7 testing matrix made actionable per layer. |
| `docs/architecture/observability-guidelines.md` | §4.8 minimum observability bar. |
| `docs/architecture/architecture-review-checklist.md` | A checklist used in every architecture-affecting PR (one Markdown checklist). |
| `docs/architecture/migration-plan.md` | §5 lifted into a standalone roadmap document for reference. |

Touched (additive only):

- `docs/INDEX.md` — append "Architecture Plans" entries linking the 10
  files above (the section already exists for the two earlier docs).
- `AGENTS.md` — append one bullet under the existing architecture
  constitution section pointing at
  `docs/architecture/architecture-principles.md` and the checklist.

### 6.3 What Will Not Change

- No file under `agents/`, `services/`, `shared/`, `migrations/`,
  `rust/`, `frontend/`, `docker/`, `infra/`, `scripts/`, `tests/`, or
  `plugins/` is modified.
- No HTTP route, event, payload, database schema, environment variable,
  or configuration file is modified.
- No CI workflow is modified.
- No dependency, lock file, or Docker image is modified.
- `tests/unit/test_architecture_boundaries.py` is not modified yet (that
  belongs to Stage 1).

### 6.4 Risk

- **Inherent risk**: very low. Documentation only.
- **Process risk**: the 10 docs are substantial reading. Reviewers may
  push back on specific phrasing or completeness. The mitigation is to
  ship the docs in a single PR but accept revisions paragraph-by-paragraph
  before merge.
- **Drift risk**: if Phase 1 analysis or backend-evolution-plan content is
  later contradicted by these new docs, downstream PRs can cite the wrong
  source. The mitigation is the cross-link section §10.4 of the existing
  plan doc: every architecture-affecting PR must reconcile the four anchor
  docs in the same change.

### 6.5 Verification

- `git status` clean before commit; only the 10 new files plus the two
  additive index/AGENTS updates show up.
- `git diff --check` clean (no whitespace issues).
- Every internal link in the new docs resolves to an existing file on disk
  (script can be a single grep).
- No Python, Rust, JavaScript, SQL, YAML, Dockerfile, or shell file
  changed by the PR.
- Manual reviewer pass on each of the 10 docs against the brief's output
  format.

### 6.6 Rollback

- The PR is one atomic merge. Rollback is `git revert <merge_sha>` (or
  reverting the PR via the GitHub UI). No data, no schema, no runtime
  state is touched, so revert is instantaneous.
- If a subset of docs is rejected, drop those files from the PR before
  merge.
- If the team prefers staging the docs across multiple PRs, split by file
  groups (e.g., principles + checklist first; then API + event + obs;
  then module + service + data; then testing + migration). Order does not
  affect correctness.

---

## 7. Confirmation Gate (是否需要我确认)

Yes. Per the brief, no code is to be modified until you confirm the
proposal in §6.

This document and the Phase 1 analysis it builds on are documentation only.
Both were produced read-only; no Python, Rust, JavaScript, SQL, YAML,
Dockerfile, or shell file has been changed during Phase 2.

### 7.1 What I Will Do When You Confirm

1. Cut a new branch off `main` (after `docs/backend-architecture-analysis`
   merges) named `docs/architecture-foundation`.
2. Add the 10 documentation files listed in §6.2, plus the two additive
   updates to `docs/INDEX.md` and `AGENTS.md`.
3. Verify locally per §6.5.
4. Open a single PR titled
   `docs(architecture): add architecture foundation docs (stage 0)`.
5. Pause for review.
6. Do **not** touch any source code, schema, route, event, configuration,
   or deployment artifact.

### 7.2 What I Will Not Do Without Further Confirmation

- Any Stage 1+ code work (file moves, port introduction, FSM extraction,
  projection tables, service extraction).
- Any change to `tests/unit/test_architecture_boundaries.py`.
- Any change to existing docs except the two additive references in §6.2.
- Any change touching production configuration, secrets, environment
  variables, or auth/authz/validation.

If you would like a different first step (for example, one of the P0 code
items instead of Stage 0 docs), reply with the alternative and I will
re-scope the first step before any code is written.
