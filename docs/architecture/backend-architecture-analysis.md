# Backend Architecture Analysis (Phase 1, Read-Only)

Last updated: 2026-05-18

Status: Phase 1 deliverable. This document is a current-state audit of the
Wisdoverse Cell Python backend. It does not propose changes. The forward plan
lives in [`backend-evolution-plan.md`](./backend-evolution-plan.md) and will
be updated after Phase 2 (target architecture design) is agreed.

Scope: Python backend only (`agents/`, `services/`, `shared/`, `migrations/`,
backend tests). Rust gateway, frontend, and Docker/CI are out of scope. The
audit reflects code on `main` at commit `751c1e1b3 refactor(backend):
modularize service boundaries (#121)`.

Method: read-only inspection plus four parallel investigation passes
(routes/service-layer, repository/persistence, inter-module dependencies,
contracts/state/observability/tests). All findings below cite concrete files;
no code was modified.

---

## 1. Current Architecture Overview

The backend is a modular monolith on the way to becoming a set of
independently deployable agent services. The shape is:

| Layer | Code locations | Responsibility |
|-------|----------------|----------------|
| Edge plane | `rust/gateway/` (out of scope here) | TLS termination, webhook verification, gRPC fan-out |
| Operator / control plane API | `shared/control_plane/api.py` plus per-aggregate route modules under `shared/control_plane/api_routes/` | `/api/v1/control-plane/*` over the ledger |
| Business runtime agents | `agents/requirement_manager/`, `agents/pjm_agent/`, `agents/qa_agent/`, `agents/dev_agent/` | Domain workflows behind explicit service boundaries |
| Gateways | `services/gateways/user_interaction/`, `services/gateways/channel/` | Chat/webhook inbound, outbound messaging |
| Orchestration | `services/orchestration/coordinator/` | Cross-boundary dispatch decisions |
| Support capabilities | `shared/capabilities/sync/`, `shared/capabilities/analysis/`, `shared/capabilities/evolution/` | Sync, analytics, evolution; not business runtimes |
| Control plane ledger | `shared/control_plane/` | Companies, goals, work items, roles, runs, decisions, approvals, budgets, artifacts, audit, evolution proposals |
| Shared runtime + contracts | `shared/app/`, `shared/core/`, `shared/schemas/`, `shared/infra/` | `create_agent_app()`, plugin model, abstract ports, event payloads, LLM gateway, EventBus client, circuit breaker |
| Shared integrations | `shared/integrations/feishu/`, `shared/integrations/wecom/`, `shared/integrations/...` | Platform adapters and reusable presentation builders |
| Messaging | `shared/messaging/inbound/`, `shared/messaging/outbound/` | Inbound user-service path and outbound delivery |
| Retired compatibility surfaces | `shared/services/`, root `skills/`, `shared.grpc.server` | Removed; canonical imports are mandatory |

Backend Python source: ~795 non-test `.py` files under
`agents/`, `services/`, `shared/`.

Each business agent ships the same internal shape (post-PR #121):

```text
agents/<agent>/
  api/          # FastAPI routers (thin handlers)
  app/          # create_agent_app() wiring, runtime plugins (incl. outbox_dispatcher)
  core/         # *_use_cases.py, *_ports.py, *_lifecycle.py, domain helpers
  db/           # *_store.py adapters, repository.py, database.py, outbox tables
  adapters/     # Agent-local external SDK/HTTP clients
  service/      # agent shell (BaseAgent subclass)
  models/       # Pydantic DTOs and schemas
  tests/        # service-local tests
```

Communication primitives in production today:

- **HTTP REST** between agents via `shared/infra/agent_client.py`. Used
  sparingly; most cross-agent flow goes via events.
- **Redis Streams EventBus** with consumer groups and a `dlq.failed` stream
  (ADR-0001). At-least-once delivery; consumers must be idempotent.
- **Durable outbox** per runtime (10 outbox tables — see §4) drained by a
  background runtime plugin every 30 s in batches of 100.
- **Control-plane work-item execution** through the operator command surface,
  which resolves owner agents and then wakes deployed `create_agent_app()`
  services through `/agent/request`.
- **gRPC** for selected internal RPCs (e.g., requirement_manager
  `HealthCheck`).

Tech stack: FastAPI, SQLAlchemy 2.x async, pydantic v2, pydantic-settings,
structlog, OpenTelemetry (optional), LiteLLM behind `shared.infra.llm_gateway`,
Redis 8 / Redis Streams, NATS JetStream (optional), PostgreSQL 18, Milvus,
Alembic for migrations.

---

## 2. Main Business Modules

| Module | Runtime path | Business focus |
|--------|--------------|----------------|
| Requirement Manager | `agents/requirement_manager/` | Meeting ingestion, requirement lifecycle, PRD support, feedback learning, requirement search |
| Project Manager (PJM) | `agents/pjm_agent/` | Work decomposition, approval preparation, project reports, alerts |
| QA Agent | `agents/qa_agent/` | Acceptance runs, quality verdicts, idempotent triggers |
| Dev Agent | `agents/dev_agent/` | Delivery tasks, workflow execution, MR handoff, QA request |
| User Interaction Gateway | `services/gateways/user_interaction/` | Chat surface, Feishu webhook intake, card operations |
| Channel Gateway | `services/gateways/channel/` | Multi-channel outbound delivery |
| Coordinator | `services/orchestration/coordinator/` | Classification + dispatch of cross-boundary events |
| Sync Capability | `shared/capabilities/sync/` | OpenProject ↔ Feishu Bitable projection (two sub-boundaries inside one runtime) |
| Analysis Capability | `shared/capabilities/analysis/` | Risk detection, report generation |
| Evolution Capability | `shared/capabilities/evolution/` | L1/L2/L3 evolution proposals, reflections, experiments |
| Control Plane | `shared/control_plane/` | Operating ledger, runs, approvals, budgets, audit |
| Identity / User | `shared/db/user_store.py`, `shared/messaging/inbound/user_service.py` | Platform user identity (no dedicated API boundary yet) |

The control plane is the durable operating ledger; the other modules are
producers and consumers of ledger evidence.

---

## 3. Candidate Domain Boundaries

These are the bounded contexts implied by the current code, not new
proposals. Each lines up with an existing runtime owner and table-ownership
row in `docs/guides/backend-boundaries.md`.

| Context | Aggregate roots (current) | Owned tables (current) |
|---------|---------------------------|------------------------|
| Control Plane / Governance | `Company`, `Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Decision`, `ApprovalRequest`, `BudgetPolicy`, `BudgetUsage`, `Artifact`, `AuditEvent`, `EvolutionProposal`, `AgentPromptConfig` | `control_plane_*` |
| Requirement | `Meeting`, `Requirement`, `OpenQuestion`, `FeedbackRecord`, `ChatMessage`, `LlmUsage` | `meetings`, `requirements`, `open_questions`, `feedback_records`, `llm_usage`, `chat_messages`, `requirement_event_outbox` |
| Planning / PJM | `DecompositionRecord`, `AlertLog`, `ConfigCache` | `pjm_agent_*` |
| Delivery / Dev | `DevTask`, `WorkflowLog` | `dev_agent_*` |
| Quality / QA | `AcceptanceRun`, `AcceptanceResult` | `qa_acceptance_*`, `qa_agent_event_outbox` |
| Sync / Projection | `SyncMapping`, `SubtaskMapping`, `SyncLock`, `SyncLog` | `sync_agent_*` |
| Interaction / Channel | `ConversationHistory`, `CardOperation`, `DailyProgress` | `chat_agent_*`, `channel_gateway_event_outbox` |
| Coordination | `CoordinatorEventOutbox` (state captured in scratchpad + state-store ports) | `coordinator_event_outbox` |
| Analytics / Reporting | `AnalysisReportLog` | `analysis_agent_*` |
| Evolution | `EvolutionTrace`, `Reflection`, `Experiment`, `SkillConfig`, `CollaborationPattern`, `Memory` | `evolution_*` |
| Identity / User | `User` | `users` (no dedicated API boundary) |

Notes:

- Control Plane is one bounded context but holds many distinct aggregates.
  The PR #121 split into per-aggregate `*_ports.py` / `*_store.py` /
  `*_use_cases.py` is the internal seam, but the context itself does not need
  to split yet.
- Sync hosts two sub-boundaries (OpenProject side, Feishu Bitable side)
  inside one runtime.

---

## 4. Code Layering State

### 4.1 Routes / Controllers — Thin

Spot checks across `agents/*/api/`, `shared/control_plane/api.py`, and
`services/gateways/*/api/` show consistent thin handlers: Pydantic validation
→ build use-case command → invoke → map response → translate domain
exceptions to HTTP errors. Example: `agents/qa_agent/api/qa.py:44-73` is ~20
LOC and delegates to `QAApiUseCase`.

`shared/control_plane/api.py` remains large but contains only thin handlers
across many endpoints; each handler still delegates to a use-case module.

### 4.2 Agent Service Shells — Delegating

`agents/<agent>/service/agent.py` files are 277–447 LOC and act as
`BaseAgent` subclasses that route `handle_event()` and `handle_request()` to
`*_use_cases.py`. Example: `agents/qa_agent/service/agent.py:99-104`
delegates to `QAEventUseCase`. No god-service pattern detected in the
sampled agents.

### 4.3 Use Cases — Orchestration Plus Transaction Boundary

`*_use_cases.py` modules orchestrate ports and own the transaction boundary
via async session context managers. Example:
`agents/qa_agent/core/acceptance_execution_use_cases.py:242-261` opens a
session, calls repository operations, stages events, and exits the context.
No inline SQL or HTTP found in spot-checked use cases.

The coordinator follows the same pattern in
`services/orchestration/coordinator/core/event_use_cases.py:49-89`: read
state, call LLM-backed thinker, persist decisions, return events.

### 4.4 Domain — Implicit

There is no dedicated `core/domain/` directory yet. Domain rules currently
live in:

- Pydantic models in `shared/control_plane/models.py` and
  `agents/<agent>/models/` (data shape only).
- `*_lifecycle.py` modules
  (`shared/control_plane/agent_run_lifecycle.py`,
  `agents/dev_agent/core/task_lifecycle.py`,
  `agents/requirement_manager/core/requirement_lifecycle.py`) carry state
  transitions and lifecycle invariants.
- Use-case modules carry orchestration plus some domain decisions.

There is no explicit aggregate / value-object layer separate from
persistence and orchestration.

### 4.5 Infrastructure / Stores — Mostly Clean

21 `*_store.py` files act as SQLAlchemy adapters. Spot checks on
`shared/control_plane/decision_store.py` (76 LOC),
`shared/control_plane/budget_store.py` (109 LOC), and
`shared/control_plane/approval_store.py` (72 LOC) show pure persistence: no
"if status == X then update Y" business decisions inside.

Domain models (Pydantic in `shared/control_plane/models.py`) are clearly
distinct from ORM tables (`shared/control_plane/tables.py`); mapping is
explicit through `_model_values()` helpers.

### 4.6 Legacy Repository Still Active

`shared/control_plane/repository.py` is **902 LOC and is still the active
query / persistence layer**. The new `*_store.py` files delegate to it
rather than replacing it. The intended target — repository as a thin facade
over per-aggregate stores — is not yet reached.

Two other repository files exist and are smaller:
`shared/db/repository.py` (71 LOC, user reads),
`agents/qa_agent/db/repository.py` (223 LOC, acceptance + outbox).

---

## 5. Dependency Issues

### 5.1 Clean Direction (Confirmed)

- No cross-agent direct imports. `from agents.<other_agent>` does not appear
  in any `agents/<a>/` runtime code.
- `shared/capabilities/` does not import from `agents/`. Direction is
  correctly agents → capabilities.
- `shared/core/` exports only abstract ports and protocols; no concrete HTTP
  clients. The single concrete dependency is on `shared/models` for User/
  Platform DTOs, which is acceptable.
- `shared/utils/` is pure: three foundational files (`id_generator.py`,
  `logger.py`, `__init__.py`). No business logic.
- `shared/integrations/feishu/cards/` centralizes Feishu card builders;
  agent-local adapters wrap them without duplication.
- No Python imports from `frontend/`.

`tests/unit/test_architecture_boundaries.py` is 4583 LOC and encodes
roughly 10 distinct rule categories (cross-agent imports, LLM SDK isolation,
canonical-path enforcement, core/app separation, util purity, channel
abstraction, ID contract, HTTP error contract, outbox-as-publish path,
`shared/services` retirement). This is the executable form of the boundary
rules and currently passes on `main`.

### 5.2 Retired Compatibility Surfaces

- `shared/services/` has been removed. Infra, integrations, and messaging tests
  now import the canonical modules directly.
- Root `skills/` has been removed. Requirement Manager skill tests now import
  `agents.requirement_manager.skills.*` directly.

Architecture-boundary tests block both packages from being reintroduced.

### 5.3 Other Observed Issues

- **`AsyncSession` leaks into route layer.**
  `shared/control_plane/api.py:730,742,761` (and similar handlers) inject
  `AsyncSession` directly via FastAPI `Depends` and instantiate stores at
  the route level. This couples handlers to the ORM session type rather than
  to a service abstraction.
- **ORM types escape the persistence layer.**
  `shared/control_plane/approval_gate.py:15,52` imports
  `ApprovalRequestTable` and returns it from business logic.
  `shared/control_plane/repository.py:79` shows
  `create_company(...) -> CompanyContextTable`. Use cases receive ORM rows
  instead of domain models in some paths.
- **AgentClient rarely used.** Inter-agent communication is dominantly
  event-driven through outboxes. `shared/infra/agent_client.py` exposes
  `AgentClientErrorCategory` (6 categories) but only one production caller
  is wired (`agents/requirement_manager/app/plugins/feishu_gateway.py`).
  This is not a bug, but it means the documented HTTP boundary is mostly
  aspirational for cross-agent flow.
- **No structured DTO sharing between agents.** Each agent defines its own
  Pydantic schemas. Cross-boundary integration relies on event payload
  contracts in `shared/schemas/event_payloads.py` and (rarely) AgentClient.

---

## 6. High-Risk Problems

The "high-risk" label here means the problem could create real correctness,
operability, or migration risk if left in place. Each one is supported by
concrete file citations from §4 / §5.

| # | Problem | Evidence | Why high risk |
|---|---------|----------|----------------|
| H1 | Single Alembic migrations directory holds all 19 migrations for every runtime | `migrations/versions/` (19 files, all numbered chronologically across boundaries) | Blocks any agent from being split out independently. Schema drift in one boundary forces a global migration. |
| H2 | Closed: the `shared/control_plane/repository.py` compatibility facade has been retired; per-aggregate `*_store.py` adapters own SQL directly. | `shared/control_plane/*_store.py`, `tests/unit/test_architecture_boundaries.py` | Control Plane aggregate stores are now structurally split, and architecture tests block facade resurrection. |
| H3 | Partially closed: Control Plane command routes use `ControlPlaneUnitOfWork` with explicit `commit()` and rollback cleanup; many agent/capability use cases still rely on session context exit. | `shared/control_plane/unit_of_work.py`, `shared/control_plane/api.py`, `agents/*/core/*_use_cases.py` | The central governance API has a clear command transaction seam, but remaining multi-aggregate agent writes still need per-runtime adoption. |
| H4 | State transitions modeled as scattered string comparisons | `shared/capabilities/sync/core/engine.py:74-87` (`if op_status == "failed" or feishu_status == "failed"`), evolution and outbox tables with `status` string defaults | No explicit FSM. Adding states or invariants requires touching every consumer; bugs that "skip" a state are silent. |
| H5 | Closed for Control Plane: store ports and application/use-case returns expose domain records; ORM rows stay inside store adapters and private row helpers. | `shared/control_plane/domain_records.py`, `shared/control_plane/*_ports.py`, `shared/control_plane/*_store.py` | Control Plane callers no longer depend on SQLAlchemy row types. |
| H6 | No metrics layer / no Prometheus exporters / no LLM cost-and-token metrics surface | `shared/observability/` review; no exporter found; budgets exist in `shared/control_plane/budget_*` but are not emitted as metrics | At-least-once outbox delivery and LLM cost are operational evidence we cannot dashboard today. Budget enforcement happens, but operators cannot watch lag/cost trends. |
| H7 | OpenTelemetry is optional and not guaranteed deployed | `shared/observability/tracing.py:22-56`, gated on `settings.otel_endpoint` | Trace IDs are propagated through `RequestIdMiddleware`, but cross-service traces require OTEL to be on. Production may be running blind. |
| H8 | No HTTP contract tests per agent; no producer/consumer event contract tests | `tests/` layout review; only structural tests in `test_architecture_boundaries.py` | Architecture import direction is enforced, but payload compatibility is not. Adding/changing a field on an event or an HTTP response is currently caught by handwritten unit tests only. |
| H9 | `users` table has no dedicated public API boundary | `shared/db/user_store.py`, `shared/messaging/inbound/user_service.py`; identity rows are reachable through messaging-inbound paths | Identity data risks becoming shared mutable state. Documented in `backend-boundaries.md` §6. |

---

## 7. Medium- and Low-Risk Problems

| # | Problem | Severity | Evidence |
|---|---------|----------|----------|
| M1 | Partially closed: companies, goals, work items, decisions, and artifacts are split into `shared/control_plane/api_routes/`, but agent, run, approval, budget, evolution, and audit handlers still live in the main API module | Medium | `shared/control_plane/api.py`, `shared/control_plane/api_routes/*.py` |
| M2 | Domain layer is implicit; lifecycle helpers, ports, and use cases co-exist under `core/` without a separate `core/domain/` | Medium | `agents/<agent>/core/`, `shared/control_plane/agent_run_lifecycle.py` |
| M3 | Closed: compatibility surfaces `shared/services/*`, root `skills/*`, and `shared.grpc.server` have been retired | Low | `tests/unit/test_architecture_boundaries.py` |
| M4 | Sync capability hosts OpenProject and Feishu Bitable in one runtime; sub-boundaries exist only inside `core/` | Medium | `shared/capabilities/sync/core/engine.py`, `shared/capabilities/sync/core/progress.py` |
| M5 | Analysis can read source-domain tables; no explicit projection layer | Medium | `shared/capabilities/analysis/` (no projection module) |
| M6 | Closed at the runtime baseline: `create_agent_app()` responses use the structured error envelope while preserving legacy `detail`; base contract tests cover auth, HTTPException, validation, and unexpected failures | Low | `shared/api/errors.py`, `shared/middleware/error_handler.py`, `tests/integration/test_runtime_error_contract.py` |
| M7 | No per-agent OpenAPI snapshots; route inventory only documented via the `/api/v1` metadata endpoint | Low | `agents/requirement_manager/app/routes.py:9-25` |
| M8 | Closed: production settings fail closed for required secrets, internal transport protection, telemetry endpoint, control-plane approval enforcement, A2A JWT, and enabled platform callback secrets | Low | `shared/config.py`, `tests/unit/test_config_secrets.py` |
| M9 | Partially closed: Control Plane commands use `ControlPlaneUnitOfWork`; remaining agent/capability writes still need per-runtime adoption where they span multiple aggregates or outboxes | Low | §H3 above |
| M10 | Closed: the deprecated `shared/grpc/server.py` entry point has been removed; shared gRPC keeps protocol artifacts only | Low | `docs/overview/project-layout.md`, `tests/integration/test_grpc_server.py` |
| M11 | `data/` directory contains local development state under git ignore; not a code problem but a contributor surface to keep clean | Low | `.gitignore`, `docs/overview/project-layout.md` |

---

## 8. Where to Keep As-Is

Do not invest refactor effort in these surfaces yet. They are either already
right, or stable enough to leave alone while higher-priority gaps are
addressed.

1. **Agent service shells** (`agents/<a>/service/agent.py`). Delegation
   pattern is clean; not god-services.
2. **Route handlers** under `agents/*/api/` and the per-handler shape inside
   `shared/control_plane/api.py`. Each handler is thin.
3. **Use-case modules** under `agents/*/core/*_use_cases.py`. Orchestration
   and transaction boundary placement are correct.
4. **`shared/core/`**. Abstract ports only.
5. **`shared/utils/`**. Pure foundational helpers.
6. **`shared/integrations/feishu/cards/`**. Centralized, reused, no
   duplication.
7. **`shared/app/` runtime and plugin model**. `create_agent_app()` and the
   plugin system already give a clean extension seam.
8. **Outbox dispatcher runtime plugin pattern.** It is uniform across 10
   boundaries; tightening should happen at the metrics / alerting layer
   (§H6), not in the dispatcher code itself.
9. **`tests/unit/test_architecture_boundaries.py`**. 4583 LOC of executable
   boundary rules. Extend it; do not rewrite it.
10. **Public runtime identifiers** (`requirement-manager`, `pjm-agent`,
    `qa-agent`, `dev-agent`, `chat-agent`, `sync-module`, `analysis-module`,
    `evolution-module`, `cmp_wisdoverse_cell`) — frozen by
    `AGENTS.md` Part 3 rule 13.

---

## 9. Where to Change First

These are the highest-leverage changes to plan next. They follow directly
from §6 and align with the phases already drafted in
`docs/architecture/backend-evolution-plan.md` §4.

| Priority | Change | Rationale | Maps to |
|----------|--------|-----------|---------|
| P0 | Keep the retired Control Plane repository facade from returning | H2 remains closed through architecture tests | Architecture-boundary tests |
| P0 | Introduce structured error body alongside the existing `X-Error-Code` header and apply uniformly | M6 closure; needed before any public API stability promise | Backend evolution plan Phase A |
| P0 | Emit outbox-lag, DLQ-rate, and LLM cost-and-token metrics (Prometheus exporter or OpenTelemetry metrics); make tracing always-on rather than gated | H6 + H7 closure; required before any independent deployment | Backend evolution plan Phase 7 |
| P1 | Introduce an explicit domain layer per agent (`core/domain/`) that holds entities, value objects, and state-machine modeling; move `*_lifecycle.py` and string-status decisions into it | H4 + M2 closure; precondition for tighter aggregate invariants | Backend evolution plan Phase B |
| P1 | Extend explicit transaction seams from Control Plane command routes into agent/capability use cases that span more than one aggregate or outbox | H3 / M9 follow-up; supports reliable recovery and future service extraction | Backend evolution plan Phase B follow-up |
| P1 | Add HTTP contract tests per agent and provider/consumer event contract tests per event in the catalog | H8 closure; supports any contract evolution | Backend evolution plan Phase 8 |
| P2 | Define and adopt a per-runtime migration ownership story (separate Alembic directories or a per-runtime migration tool) | H1 closure; gate before any service extraction | Backend evolution plan Phase G |
| P2 | Add a `users` / identity API boundary; route all writes through it | H9 closure | Backend evolution plan Phase E |
| P2 | Add an explicit projection layer for Analysis | M5 closure | Backend evolution plan Phase C |
| P3 | Keep retired `shared/services/*`, root `skills/*`, and `shared.grpc.server` from returning | M3 / M10 remain closed | Architecture-boundary tests |
| P3 | Split Sync into two sub-capability runtimes (OpenProject and Feishu Bitable) once each side has its own outbox and repository | M4 closure | Backend evolution plan Phase D |
| P3 | Continue splitting `shared/control_plane/api.py` into per-aggregate routers | M1 closure | low-risk structure work; batch by route family |

---

## 10. Where Not to Change Yet

These items must stay stable while §9 is in flight. Touching them now would
either invalidate the executable boundary tests, break consumers, or
distract from higher-leverage work.

1. **Public HTTP routes** under `/api/v1/control-plane/*` and `/api/v1/*`.
2. **EventBus delivery model**: Redis Streams, consumer groups,
   `dlq.failed`, at-least-once semantics (ADR-0001).
3. **Per-agent PostgreSQL users and Redis DB numbers** (ADR-0002).
4. **HTTP-only inter-agent contract** (ADR-0004). No new in-process
   cross-agent imports.
5. **`shared/control_plane` aggregate set**
   (`Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Approval`, `Budget`,
   `Artifact`, `AuditEvent`, `EvolutionProposal`).
6. **Canonical runtime identifiers and agent IDs** (`AGENTS.md` Part 3 rule
   13).
7. **`tests/unit/test_architecture_boundaries.py`**. Extend, do not rewrite.
8. **Rust gateway protobuf contracts**. Anything that changes the
   `requirement.proto` boundary must coordinate with the Rust workspace.
9. **`AgentRuntime` plugin contract**. Outbox dispatchers, control-plane
   plugin, and status plugin all depend on the current shape.
10. **Default `cell` Compose topology**. Splitting agents into independent
    containers is a Phase H concern; the topology should not move ahead of
    its migration story.
11. **Frontend Feature-Sliced Design layout**. Backend changes must not push
    domain logic into frontend slices.

---

## 11. Open Questions Carried Into Phase 2

These are facts the audit could not resolve without changing scope. They
should be addressed during the Phase 2 target-architecture design.

1. **Identity ownership.** `users` is owned by shared paths today; should it
   become a dedicated runtime, or remain a shared boundary with a strict API
   facade? (Tie-in with H9 / P2.)
2. **Coordinator durability.** The coordinator has `coordinator_event_outbox`
   but its scratchpad and state-store are abstracted through ports. What is
   the durable backing today (Redis only? Postgres-backed?), and does the
   operator replay tooling exist? (Tie-in with `backend-boundaries.md` §2
   posture.)
3. **gRPC scope.** Only Requirement Manager has a live gRPC server. Is gRPC
   expected to expand to other agents, or stay scoped to gateway↔requirement
   boundaries? Phase 2 design should commit one way.
4. **Service-extraction ordering.** `backend-boundaries.md` §2 lists Dev and
   QA as strongest extraction candidates. Phase 2 should pick the first
   target and the pre-conditions explicitly (per-runtime migration story,
   read-model, replay).
5. **LLM provider strategy beyond `LLMGateway`.** All model traffic must
   route through `shared.infra.llm_gateway`, but fallback / budget / circuit
   policy is hardcoded today. Phase 2 should decide whether policy lives in
   gateway config or in the control plane.
6. **Observability stack of record.** OpenTelemetry is optional, Prometheus
   is absent. Phase 2 should commit to a specific stack and an SLI/SLO
   register.

---

## 12. Verification of This Document

This audit started as a read-only snapshot. Later backend refactor PRs keep
the status rows current when an audit item changes. Concrete verification:

- `git status` clean on `docs/backend-architecture-analysis` branch before
  this commit; only new files added under `docs/architecture/`.
- Baseline file paths existed on `main` at commit `751c1e1b3`; current
  status rows may also cite newer files added by later refactor PRs.
- Key baseline facts re-checked at write time:
  - `shared/control_plane/repository.py` = 902 LOC
  - `shared/control_plane/api.py` remains the main Control Plane router;
    company, goal, work item, decision, and artifact routes have been moved
    to `shared/control_plane/api_routes/`
  - `tests/unit/test_architecture_boundaries.py` = 4583 LOC
  - `migrations/versions/` = 19 files
  - `grep "session.begin" agents/ services/ shared/` = 0 hits
  - Backend Python source (non-test) ≈ 795 files
- No code, schema, route, event, configuration, or deployment artifact was
  modified during the original analysis phase.

---

## 13. Next Step

Phase 2 (target architecture design) is the next deliverable. The prompt
that drives Phase 2 was truncated mid-section 六 (observability). Before
producing the Phase 2 design document, the truncated sections need to be
confirmed so the design covers the user's full intent.

Open items for the Phase 2 prompt confirmation:

- §六 (observability) had only item 1 (`requestId / correlationId`) visible.
- §七 onward (likely testing strategy, evolution roadmap, rollback /
  reversibility) is absent from what was received.

This Phase 1 document is the contract Phase 2 must reconcile against.
