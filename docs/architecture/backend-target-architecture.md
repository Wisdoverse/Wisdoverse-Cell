# Backend Target Architecture and Phased Migration Plan

Last updated: 2026-10-01

Status: Maintained architecture reference. Delivery status and acceptance
are tracked in [Backend Migration Plan](./migration-plan.md). Project delivery
order is tracked in the [Product Roadmap](../overview/roadmap.md).

The initial analysis below predates later remediation. Current implementation
status uses main at commit c387877 (2026-10-01) and the DDD audit; it does not
establish staging or production acceptance.

For the 2026-10-01 product implementation snapshot across M0–M4 and R0, see
the [Product Roadmap snapshot](../overview/roadmap.md#engineering-delivery-snapshot-2026-10-01),
[engineering receipt](../evidence/product-roadmap-engineering-2026-10-01.md),
[product governance runbook](../runbooks/product-governance.md), and
[Control Plane metrics runbook](../runbooks/control-plane-metrics.md). Those
surfaces distinguish implemented code from open operator and deployment
acceptance.

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

Sections 1–4 describe architecture and boundary decisions. Section 5 records
current delivery status, and Section 6 links the implementation and release
review process.

---

## 1. Current Architecture Understanding

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
migrations/              # Single Alembic directory (24 versions)
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
| Chat Agent | `agents/chat_agent/` | Conversation history, card operations, daily progress, chat-triggered integration commands |
| User Interaction Gateway | `services/gateways/user_interaction/` | Chat/webhook ingress and Feishu ACL; HTTP boundary to chat-agent |
| Channel Gateway | `services/gateways/channel/` | Outbound multi-channel delivery |
| Coordinator | `services/orchestration/coordinator/` | Cross-boundary event classification + dispatch |
| Sync Capability | `shared/capabilities/sync/` | OpenProject ↔ Feishu Bitable projection |
| Analysis Capability | `shared/capabilities/analysis/` | Risk detection, report generation |
| Evolution Capability | `shared/capabilities/evolution/` | L1/L2/L3 evolution proposals |
| Control Plane Ledger | `shared/control_plane/` | Companies, goals, work items, runs, approvals, budgets, artifacts, audit, evolution |
| Identity / User | `shared/db/user_store.py`, `shared/db/identity_event_outbox_store.py`, `shared/messaging/inbound/user_service.py` | Platform user identity and identity event staging |

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
- structlog for structured logs; OpenTelemetry tracing with a no-export
  fallback outside production; Prometheus metrics exposed at the FastAPI
  boundary.
- Alembic for migrations (single directory, 24 versions).
- Traefik v3 for routing; Rust + Axum gateway at the edge.
- Tests: pytest, async pytest, `tests/unit/test_architecture_boundaries.py`
  (7240 LOC) enforcing architecture-boundary rules.

### 1.4 Current Layering

Each product-owning runtime ships the same internal shape:

```text
agents/<agent>/
  api/         # FastAPI routers (thin handlers)
  app/         # create_agent_app() wiring, runtime plugins (incl. outbox)
  core/        # *_use_cases.py, *_ports.py, domain/, helpers
  db/          # *_store.py, repository.py, database.py, outbox tables
  adapters/    # Agent-local external SDK / HTTP clients
  service/     # BaseAgent subclass (the "shell")
  models/      # Pydantic DTOs
  tests/       # service-local tests
```

Observed layer behavior:

- Routes are thin (validate → use-case → response map).
- Service shells delegate to `*_use_cases.py`; not god-services.
- Use cases own orchestration. Control Plane command routes, Requirement
  Manager core commands, Dev Agent event/request use cases plus scheduler
  maintenance paths, QA acceptance execution, and PJM decomposition
  transactions use explicit unit-of-work ports. Some adapter maintenance paths
  still rely on session context managers and are tracked under P2-6.
- Stores are pure persistence; do not encode business rules.
- Product-owning runtimes materialize explicit `core/domain/` packages for
  aggregates, value objects, lifecycle state machines, and in-memory domain
  events.
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
- Cross-runtime data reads / writes go through HTTP REST (`AgentClient`),
  events, or explicit projection ports. No cross-database joins. Analysis
  report and milestone read paths consume the Analysis-owned projection;
  source-system reads are confined to the projection updater / ACL boundary.
- All Alembic migrations are tracked in a single `migrations/versions/`
  directory (24 files), shared across all runtimes.

---

## 2. Current Problem Diagnosis

Findings grouped by priority. Each item lists description, location, scope of
impact, risk level, and recommended handling.

### 2.1 P0 — Must Address Now

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P0-1 | The `shared/control_plane/repository.py` backward-compatible facade has been retired; per-aggregate stores own the SQL and tests use store factory / ports. | `shared/control_plane/*_store.py`, `shared/control_plane/store_factory.py` | Legacy callers can no longer bypass aggregate stores through the facade. | Low | Keep architecture tests blocking facade resurrection and route new access through ports/factory adapters. |
| P0-2 | Single Alembic directory holds 24 migrations for every runtime; per-runtime ownership impossible. | `migrations/versions/` | Blocks Phase 4 service-boundary evolution; any agent extraction requires global migration coordination. | High | Plan and adopt per-runtime migration ownership (separate Alembic dirs or a per-runtime migration tool) before service extraction starts. |
| P0-3 | Shared Prometheus metrics now live at the `shared.observability.metrics` boundary and cover LLM cost/tokens, event loop errors, loop breaker state, event queue length by stream, Redis DLQ length/rate, outbox dispatcher totals/duration/errors, and oldest pending outbox age per runtime. Alert rules now cover outbox backlog age and DLQ growth/retention. Remaining gap: dashboard panels and threshold tuning need production evidence. | `shared/observability/metrics.py`, `shared/observability/outbox.py`, `shared/infra/event_bus.py`, `docker/prometheus/rules/application.yml`, runtime outbox dispatch use cases, `shared/infra/metrics.py` compatibility shim | Operators have a canonical metrics and alerting boundary for sustained DLQ growth, stream backlog, and outbox backlog age before service extraction. | Low | Keep new metric definitions under `shared.observability.metrics`; add dashboard panels and tune thresholds from production evidence. |
| P0-4 | OpenTelemetry tracing now installs a runtime `TracerProvider` even when non-production lacks an exporter, and production settings fail closed without `OTEL_ENDPOINT` or `OTEL_EXPORTER_OTLP_ENDPOINT`. Remaining gap: sampling policy and trace dashboard evidence need production tuning. | `shared/observability/tracing.py`, `shared/config.py`, `docker/compose/docker-compose.app.yml` | Cross-runtime traces have a mandatory bootstrap contract before service extraction; non-prod keeps trace context without requiring a collector. | Low | Keep tracing initialized through `create_agent_app()`; add sampling policy and dashboard evidence during production hardening. |
| P0-5 | Runtime error responses use the shared structured envelope at the `create_agent_app()` boundary and base consumer contract tests cover auth, HTTPException, validation, and unexpected failures. Route-specific consumer coverage is still uneven. | `shared/api/errors.py`, `shared/middleware/error_handler.py`, `shared/app/factory.py`, `tests/integration/test_runtime_error_contract.py` | Operators have a consistent runtime body/header shape; remaining risk is direct-router test harness drift for specific routes. | Low | Keep the legacy `detail` field until clients have migrated and expand route-specific provider/consumer tests when routes change. |

### 2.2 P1 — High Priority

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P1-1 | Closed: product-owning runtimes now materialize explicit `core/domain/` packages with aggregates, value objects, lifecycle state machines, and domain events. | `agents/*/core/domain/`, `shared/capabilities/*/core/domain/`, `services/orchestration/coordinator/core/domain/`, `shared/control_plane/domain/` | Use-case drift into domain ownership is now blocked by architecture-boundary tests and aggregate unit-test coverage. | Low | Keep new product-owning runtimes under the mandatory `core/domain/` rule. |
| P1-2 | Closed for landed aggregates: lifecycle state transitions are represented by aggregate FSMs and typed transition errors; Sync operation state is normalized through `SyncOperationStatus`. | `agents/*/core/domain/lifecycle/`, `shared/capabilities/sync/core/domain/sync_operation.py`, `shared/control_plane/domain/agent_run.py` | Existing lifecycle transitions are auditable through aggregate methods and domain events; new non-trivial records must follow the same rule. | Low | Keep FSM tests with each aggregate and block new string-only lifecycle logic. |
| P1-3 | Closed for Control Plane: store ports and application/use-case returns now expose domain records across company, goal, work item, agent role, agent prompt config, agent run, approval, decision, artifact, budget, audit timeline, and evolution proposal surfaces. | `shared/control_plane/*_store.py`, `shared/control_plane/*_ports.py`, `shared/control_plane/domain_records.py` | ORM rows are infrastructure-private inside store adapters and private row helpers; callers no longer handle `metadata_json` or SQLAlchemy row types. | Low | Keep architecture tests blocking ORM table/`Any` returns in ports and domain-record conversion in use cases. |
| P1-4 | No HTTP contract tests per agent; no producer/consumer event contract tests. | `tests/` (no contract test directory found) | Payload-shape regressions are caught only by handwritten unit tests. | Medium | Add per-agent OpenAPI snapshot tests and producer/consumer event tests keyed off `docs/guides/event-catalog.md`. |
| P1-5 | Partially closed: the Identity / User boundary now has a documented single write owner, identity domain events, and `identity_event_outbox`; the public user/profile API remains a future extraction prerequisite. | `docs/architecture/identity-boundary.md`, `shared/messaging/inbound/user_service.py`, `shared/core/identity_resolution.py`, `shared/db/user_store.py` | Internal writes are constrained, but external consumers would still couple to internal messaging paths until a public API exists. | Medium | Keep the single write-owner rule enforced; add `/api/v1/identity/users/*` before Identity runtime extraction. |

### 2.3 P2 — Mid-Term Optimization

| ID | Problem | Location | Impact | Risk | Recommended action |
|----|---------|----------|--------|------|--------------------|
| P2-1 | Closed: Control Plane HTTP handlers now live under `shared/control_plane/api_routes/`; `shared/control_plane/api.py` only owns session/UOW dependencies and router composition. | `shared/control_plane/api.py`, `shared/control_plane/api_routes/*.py` | Route ownership is explicit by ledger surface, reducing unrelated diffs in the main API entrypoint. | Low | Keep architecture tests blocking DTO and handler drift back into the composition module. |
| P2-2 | Closed for reporting paths: Analysis daily/weekly report and milestone use cases read task data through `WorkPackageProjectionPort`; source-system reads are confined to `ProjectionUpdater` as the ingestion ACL for the projection. | `shared/capabilities/analysis/core/domain/projection.py`, `shared/capabilities/analysis/core/projection_updater.py`, `shared/capabilities/analysis/db/projection_store.py` | Reporting no longer owns source-domain tables implicitly. Remaining risk is operational freshness/backfill of the projection. | Low | Keep report/milestone use cases projection-only; test projection freshness and backfill idempotency. |
| P2-3 | Sync capability hosts OpenProject and Feishu Bitable inside one runtime; sub-boundaries exist only in `core/`. | `shared/capabilities/sync/core/engine.py`, `progress.py` | Independent scaling / failure isolation impossible. | Medium | Split into two sub-capability runtimes, each with its own outbox and repository; keep a compatibility orchestrator endpoint. |
| P2-4 | Closed: retired `shared/services/*` and root `skills/*` compatibility surfaces have been removed. Tests and docs now use canonical paths, and architecture checks block reintroduction. | `shared/infra/tests/test_nats_event_bus.py`, `shared/db/tests/test_base_database_manager.py`, `tests/unit/test_architecture_boundaries.py` | New code has no compatibility import surface to couple to. | Low | Keep architecture tests blocking `shared/services` and root `skills` resurrection. |
| P2-5 | Closed: the deprecated `shared/grpc/server.py` runtime entry point has been removed; shared gRPC now keeps protocol artifacts only. | `shared/grpc/`, `agents/requirement_manager/grpc/`, `tests/integration/test_grpc_server.py` | New code has one requirements gRPC runtime entry point. | Low | Keep architecture and deprecated-import checks blocking `shared.grpc.server` imports. |
| P2-6 | Partially closed: Control Plane command routes, Requirement Manager core commands, Dev Agent event/request use cases and scheduler maintenance paths, QA acceptance execution, and PJM decomposition transactions use explicit unit-of-work ports with `commit()` and rollback cleanup; other runtime/capability use cases still use implicit session context boundaries. | `shared/control_plane/unit_of_work.py`, `shared/control_plane/api.py`, `agents/requirement_manager/db/unit_of_work.py`, `agents/dev_agent/core/unit_of_work_ports.py`, `agents/dev_agent/db/unit_of_work.py`, `agents/qa_agent/core/unit_of_work_ports.py`, `agents/pjm_agent/core/decomposition_ports.py`, `agents/*/core/*_use_cases.py` patterns | The central governance API plus Requirement, Dev, QA, and PJM decomposition runtime write boundaries have explicit transaction seams; remaining multi-aggregate agent/capability writes still need per-runtime adoption. | Medium | Keep command-route, Requirement/Dev UOW, QA UOW, and PJM transaction architecture tests in place; continue introducing per-runtime `UnitOfWork` ports where a use case touches more than one aggregate or outbox. |
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

## 3. Bounded Context Analysis

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
- **Business objects**: gateway owns none; ConversationHistory,
  CardOperation, and DailyProgress belong to `agents/chat_agent/`.
- **Owned data**: `chat_agent_*` belongs to `agents/chat_agent/`;
  `channel_gateway_event_outbox` belongs to Channel Gateway.
- **Capabilities exposed**: chat REST/webhooks, outbound card operations,
  channel messages.
- **External dependencies**: Feishu, WeCom, business agents (downstream
  recipients of intent), control plane.
- **Boundary clarity**: high. Chat-agent runtime owns product logic,
  persistence, scheduler, outbox dispatching, and internal HTTP APIs after
  ADR-0010 Steps 1-7; gateway production code calls it through HTTP adapters.
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
- **External dependencies**: Analysis-owned projection tables populated from
  OpenProject and Feishu Bitable source ports by the projection updater.
- **Boundary clarity**: medium. Report and milestone reads depend on
  `WorkPackageProjectionPort`; projection freshness/backfill remains the
  main operational seam.
- **Split fit**: projection / read-model service candidate after freshness,
  backfill, and replay evidence are production-proven.

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

- **Responsibility**: platform user identity, lookup, link to runtime
  context, and PII-safe identity event staging.
- **Business objects**: User, Platform, IdentityEventOutbox.
- **Owned data**: `users`, `identity_event_outbox` (no dedicated API today).
- **Capabilities exposed**: identity lookup through messaging-inbound and
  shared user store; `identity.*` events through the identity outbox.
- **External dependencies**: every runtime that needs user context.
- **Boundary clarity**: medium-high. Writes route through the identity
  service path and aggregate methods; identity events are staged in the
  same local transaction. No public API yet.
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

## 4. Target Architecture Proposal

### 4.1 Overall Architecture

Keep the default **modular monolith** until a selected runtime passes the
service split pre-conditions and has an observed independent deployment need.
Dev and QA remain candidates with code-level boundaries in place; migration,
staging and recovery evidence still gate extraction. The Product Roadmap can
deliver an accepted operator flow in the bundled topology while that evidence
is prepared. Calendar estimates do not substitute for acceptance.

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
| Analysis | Medium | Yes (projection + own tables) | Low | Low | Yes | Low | No | Low | Medium | Keep modular; harden projection freshness/backfill |
| Evolution | Medium | Yes (own tables) | Low | Low | Yes (proposal flow needs guardrails) | Low | No | Low | Medium | Keep modular; harden approval/rollback first |
| Requirement Manager | Yes | Yes | Medium | Medium | Yes | Yes | No | Medium | Medium | Keep modular; extract after Dev/QA pattern proves |
| PJM | Yes | Yes | Low | Low | Yes | Medium | No | Medium | Medium | Keep modular; pair with sync sub-split |
| Identity / User | Medium (internal boundary, no public API) | Yes (users + outbox) | Low | Low | Yes | Low | No | Low | High | Define API first; do not split runtime |

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
3. Analysis report and milestone read paths must consume only projections;
   only the projection updater may read source-system ports.
4. `users` and `identity_event_outbox` form the Identity boundary with a
   single write path (P1-5 target).
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

## 5. Phased Migration Roadmap

[Backend Migration Plan](./migration-plan.md) is the canonical six-stage
backend execution plan; [Product Roadmap](../overview/roadmap.md) owns the
project's outcome priorities. Their baseline, scope, dependencies and acceptance
criteria apply here; this section summarizes rather than duplicates them.

| Stage | Current status | Next action |
|-------|----------------|-------------|
| 0. Architecture docs and standards | Implemented | Maintain linked docs and evidence |
| 1. Code structure cleanup | Implemented | Preserve canonical paths, explicit UoWs and boundary tests |
| 2. Core domain modeling | Implemented for the tracked DDD scope | Audit records 22/22 code-level closures; model additional invariants when required |
| 3. Data ownership and boundaries | Implemented at code level | Verify projection freshness/backfill and rollout compatibility; public Identity API remains a future extraction prerequisite |
| 4. Service boundary evolution | Partial; acceptance pending | Per-runtime migration cutover, staging observations, replay and rollback rehearsal |
| 5. Engineering quality | Partial; continuous alongside Stage 4 | Expand route contracts and type coverage; verify operational gates on the target revision |

### 5.1 Delivered Foundation

The native executor adds a default-off, versioned HTTP receiver to the four
business runtimes. Each runtime owns its request/receipt ledger; synthetic
handler conformance and PostgreSQL replay/concurrency are verified. This is
bounded receiver engineering, not a complete Requirement-to-PJM business
handoff or live integration pilot. See the [API contract](../guides/api-reference.md#native-executor-api),
[runbook](../runbooks/native-executor.md), and [engineering evidence](../evidence/native-executor-engineering-2026-10-01.md).
Any enabled deployment must include its receipt ledger in backup and cutover
scope; Dev S4.1's earlier three-table proof does not cover this added state.

- Control Plane HTTP handlers are per-surface routers with store/UoW
  boundaries, domain lifecycle rules and architecture tests.
- Analysis report/milestone reads use projections; Identity has a single
  internal write owner and PII-safe outbox.
- Chat Agent owns its product state. Gateway production paths call Chat
  Agent through HTTP adapters; DDD-016/017 are closed at code level.
- The [DDD Compliance Audit](./ddd-compliance-audit.md#2-executive-summary)
  records all 22 remediation rows closed at code-architecture level.
- [CI](../../.github/workflows/ci.yml) configures scoped Mypy and a
  PostgreSQL migration round trip. These are implemented gates; their
  coverage and target-revision results still matter for acceptance.

Dev S4.1 synthetic engineering acceptance passed on PostgreSQL 18.6, including
schema parity, synthetic backup/loss/restore, tracking rollback/restamp,
failure and drift guards, and cleanup. The candidate remains rehearsal-only
and the legacy chain remains the active migration owner. Production-copy
validation, physical cutover preconditions, scheduling, operator backup
sign-off, staging observation and production acceptance remain pending. See
[the evidence record](./evidence/dev-migration-s41.md) and [migration plan](./migration-plan.md#s41-engineering-evidence--2026-10-01).

Subsequent synthetic acceptance adds one Requirement Manager handoff case:
confirmed requirement data maps to selected existing OpenProject IDs and
company/goal/work IDs after read-only Control Plane HTTP verification; the
mapping, receipt and pending outbox event commit atomically. It does not issue
an OpenProject write or establish PJM/Dev/QA delivery. Seven isolated
PostgreSQL cases verify the Control Plane audit/knowledge retention path: a
default-off 90-day-minimum policy, batches of at most 1,000, pending/pinned
evidence preservation and replay tombstones. The policy does not erase WAL or
backup copies; operational purge and recovery acceptance remain pending.
Native runtime receipt-ledger retention remains a separate open item.

One isolated PostgreSQL L1 evolution loop covers 50 fixed paired synthetic
cases and regression rollback without a model/provider call. One separate
real-browser case executes a synthetic restricted local-process task through
the actual operator proxy and reads back linked work, run, artifact, cost and
acceptance evidence. These checks do not establish live model quality, live
provider/platform behavior, QA-agent delivery, recurring-work pilot results,
or a production-like operator flow.

### 5.2 Remaining Delivery

1. **P0 / M0 / S5.4: first business outcome.** A synthetic real-browser case
   now verifies create, assign, real backend execution, artifact inspection,
   acceptance and close with persisted cost/audit links. Still validate the
   Requirement Manager→PJM→Dev→QA path, QA/required approval, failure recovery,
   policy denial and restart against a selected runtime.
2. **P1 / M1–M3: governed autonomy and measured improvement.** Prove atomic
   execution ownership, scheduler recovery, permissions/budget enforcement,
   executor conformance and an integrated approved evolution experiment.
   Records and component tests do not establish whole-flow acceptance.
3. **R0 / S4.1–S4.3: deployment acceptance.** Prepare per-runtime migration
   cutover, accept Dev or QA in staging when justified, and complete the Sync split per
   [ADR-0009](../adr/0009-sync-sub-runtime-split.md). Each cutover needs its
   own pre-condition evidence, at least 14 days and 1,000 matching requests in
   realistic staging within declared SLOs, and replay/rollback rehearsal.
4. **P2 / M4: company reuse.** Follow the
   [Product Roadmap](../overview/roadmap.md) for safe templates and scoped
   knowledge after stable contracts and governance.

Keep the modular deployment until each selected runtime satisfies the
[Service Boundaries](./service-boundaries.md) pre-conditions. A source-level
split does not prove independent operation, and accepting one runtime does
not accept every Stage 4 cutover.

### 5.3 Evidence and Public Documentation

Each milestone records its target revision, responsible role, dependencies,
verification date, observation interval, declared SLOs, results, rollback
outcome and remaining blockers. Public records contain sanitized summaries
and source/PR references. Personal contacts, credentials, internal deployment
links, customer data and raw production logs remain outside the repository.

Stages 0–3 supply extraction prerequisites. Stage 5 runs alongside Stage 4;
cutover-critical quality checks pass before deployment acceptance. Refer to
the migration plan for complete scope and maintenance rules.

## 6. Delivery and Review

Implementation changes follow the
[Architecture Review Checklist](./architecture-review-checklist.md).
Deployment acceptance follows the
[Release Checklist](./release-checklist.md), runtime-specific ADRs, and
[Rollback Checklist](./rollback-checklist.md). Record unresolved acceptance
separately from completed code work.

Documentation updates reconcile this section, the migration plan,
[Backend Evolution Plan](./backend-evolution-plan.md) §0, and the
[Product Model](../overview/product-model.md). The documentation index points
contributors to the maintained roadmap.
