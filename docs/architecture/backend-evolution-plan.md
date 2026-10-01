# Backend Evolution Follow-Up Plan

Last updated: 2026-10-01

Status: Historical follow-up plan with a maintained status reconciliation in
§0. Sections 1 onward preserve the earlier modularization plan and are not
the active delivery checklist.

[Backend Migration Plan](./migration-plan.md) is the canonical six-stage
roadmap. [Product Model](../overview/product-model.md) tracks operator-flow
and production-hardening milestones.

## 0. Status Update

This reconciliation uses main at commit 4fadf8b (2026-05-25), tracked code,
CI configuration and the DDD audit. It does not claim deployment acceptance
or current production SLO performance.

| Stage | Current status | Evidence and remaining work |
|-------|----------------|-----------------------------|
| 0. Architecture docs and standards | Implemented | Foundation docs, index and review checklists |
| 1. Code structure cleanup | Implemented | Per-surface routers, canonical paths, store/UoW boundaries and architecture tests |
| 2. Domain modeling | Implemented for the audited scope | [DDD audit](./ddd-compliance-audit.md#2-executive-summary) records 22/22 remediation rows closed at code-architecture level |
| 3. Data ownership and boundaries | Implemented at code level | Analysis projections, internal Identity write owner and PII-safe outbox, Chat Agent ownership and gateway HTTP boundary; public Identity API remains a future extraction prerequisite |
| 4. Service boundary evolution | Partial; acceptance pending | Physical per-runtime migration cutover, Sync deployment split, staging parity, replay and rollback evidence |
| 5. Engineering quality | Partial; continuous | Mypy and migration round-trip CI are configured; remaining work is coverage expansion, route contracts and demonstrated operating gates |

### Next Priorities

- **P0 / S4.1–S4.3**: prove per-runtime migration and independent staging
  operation, then complete the Sync split under ADR-0009. Each runtime needs
  dated observations and a rollback rehearsal.
- **P1 / S5.4**: validate the task operation flow, including approval,
  artifact inspection, retry, reassignment and duplicate-delivery behavior.
- **P2**: production scheduler ownership, enforceable permissions, SLO alerts
  and audit retention/export policy per the product milestones.

Stages 0–3 supply extraction prerequisites. Stage 5 may proceed alongside
Stage 4; required quality checks pass before a cutover is accepted. Deliver
cohesive boundary or operator-flow changes rather than mechanical moves.

### Phase 1 Gap Reconciliation

| Phase 1 gap | Current disposition |
|-------------|---------------------|
| H1 / P0-2: single Alembic directory | Cutover design exists; physical per-runtime migration adoption remains pending |
| H2 / P0-1: repository facade | Retired; per-aggregate stores own Control Plane persistence |
| H3 / P2-6: implicit transaction boundaries | Closed for the tracked code-architecture scope; UoW and transaction policies are represented in the DDD audit |
| H5 / P1-3: ORM leakage | Domain records cross store/application boundaries; ORM rows stay inside adapters |
| H6 / P0-3: missing outbox metrics | Metrics and collectors exist; staging dashboards and threshold tuning still require evidence |
| P0-4: optional tracing | Runtime provider/fail-closed production configuration implemented; verify exporter delivery on rollout |
| H8 / P1-4: contract tests | Shared envelope/event contracts exist; route-specific provider/consumer coverage remains incremental |
| H9 / P1-5: Identity boundary | Internal write owner and outbox implemented; public API remains a future extraction prerequisite |
| M1: large Control Plane API | Per-surface routers implemented; composition remains in the API module |
| M2: implicit domain layer | Tracked DDD code-level remediation closed |
| M5: Analysis source-table drift | Projection ports/tables and updater implemented; verify freshness/backfill on rollout |
| M6: error envelope | Runtime envelope and base consumer tests implemented; deepen route-level contracts |

The earlier statement that type checking and migration CI remain unimplemented
is superseded: PRs #160 and #161 configured those gates. A shared-chain round
trip does not prove per-runtime cutover readiness, and scoped Mypy does not
establish repository-wide type coverage.

### Public Evidence

Publish source/PR references, role-based responsibility and sanitized
acceptance summaries. Keep private deployment links, personal contacts,
credentials, customer data and raw production logs outside this repository.
Actual assignments and release dates are recorded when delivery work is
scheduled; this reconciliation does not invent them.

---

## 1. Current PR Scope

PR #121 captures one architecture slice. It does not finalize the backend
architecture target.

| Item | Status in PR #121 |
|------|-------------------|
| Branch | `refactor/settings-env-contract` |
| Head commit | `d3d219de refactor(backend): modularize agent service boundaries` |
| Diff size | ~539 files changed, ~41.5k insertions, ~7.8k deletions |
| Scope | Internal modularization of agent services, gateways, capabilities, and the control-plane ledger toward Clean Architecture and Hexagonal layering |
| External contracts | No new public HTTP routes; no new public event types beyond what is documented in the Event Catalog at the time of the commit |
| Public CLI / runtime IDs | Unchanged (`requirement-manager`, `pjm-agent`, `qa-agent`, `dev-agent`, `chat-agent`, `sync-module`, `analysis-module`, `evolution-module`, `cmp_wisdoverse_cell`) |
| Verification | Stable backend regression: 1860 passed / 15 skipped / 183 deselected; latest Requirement Manager stable subset: 340 passed |
| Known constraints | Full QA/PJM repository integration suites require local PostgreSQL on `127.0.0.1:5433` and are excluded from the current regression gate |

This PR intentionally does not:

- Extract any agent into its own deployment beyond the existing Compose split.
- Migrate any table owner.
- Change `/api/v1/control-plane/*` shape, the EventBus delivery model, or any
  external integration contract.
- Retire the remaining compatibility surfaces under `shared/services/` or root
  `skills/` at the time; this has since been closed by the P2-4 retirement.

---

## 2. What Has Already Been Modularized

PR #121 (and the surrounding work merged before it) has established the
following structure. Treat this section as fact, not aspiration.

### 2.1 Per-Agent Clean Architecture Layering

Every business runtime agent under `agents/` now ships the same four-layer
package shape:

| Layer | Convention | Examples |
|-------|------------|----------|
| Application use cases | `agents/<agent>/core/*_use_cases.py` | `event_use_cases.py`, `request_use_cases.py`, `api_use_cases.py`, `workflow_execution_use_cases.py`, `scheduler_use_cases.py` |
| Ports / contracts | `agents/<agent>/core/*_ports.py` | `outbox_ports.py`, `health_ports.py`, `meeting_ports.py`, `requirement_ports.py`, `chat_ports.py`, `event_ports.py` |
| Infrastructure adapters | `agents/<agent>/db/*_store.py`, `agents/<agent>/adapters/` | `task_store.py`, `workflow_log_store.py`, `health_store.py`, `outbox_store.py`, `adapters/` for external SDK clients |
| Runtime entry points | `agents/<agent>/app/`, `agents/<agent>/api/`, `agents/<agent>/service/` | `create_agent_app()` wiring, FastAPI routers, runtime plugins, agent shells |

This pattern is repeated across `requirement_manager`, `pjm_agent`, `qa_agent`,
and `dev_agent`. The count of `*_ports.py`, `*_use_cases.py`, and `*_store.py`
files added or restructured by PR #121 alone is in the low hundreds.

### 2.2 Control-Plane Ledger Decomposition

`shared/control_plane/` now has per-aggregate port, store, and use-case files
(`goal_*`, `work_item_*`, `agent_run_*`, `approval_*`, `budget_*`,
`artifact_*`, `audit_timeline_*`, `decision_*`, `evolution_proposal_*`,
`prompt_config_*`, `runtime_plugin_*`, `agent_operation_*`,
`agent_registry_*`, `company_*`, `bootstrap_*`, `budget_guard_*`,
`run_evidence_*`). The legacy `repository.py` compatibility facade has been
retired; per-aggregate stores now hold the authoritative SQL.

### 2.3 Hexagonal Boundary in Shared Code

`shared/core/` owns the abstract boundaries that platform adapters must
implement: `messaging/`, `channels/`, `ids.py`, `identity_ports.py`,
`integration_ports.py`, `event_publisher.py`, `request_result.py`.
`shared/integrations/` and `shared/messaging/{inbound,outbound}/` provide the
adapter implementations. `agents/<agent>/adapters/` keeps agent-local SDK
clients.

### 2.4 Outbox + Runtime Plugin Boundary

Each business agent now has a durable outbox table and an outbox-dispatcher
runtime plugin under `agents/<agent>/app/plugins/outbox_dispatcher.py`. The
control plane, requirement, PJM, QA, dev, sync, analysis, channel gateway,
coordinator, evolution, and chat gateway boundaries each own their own
`*_event_outbox` table, mirroring the contract documented in
`docs/guides/backend-boundaries.md` §3. The runtime plugin model in
`shared/control_plane/runtime_plugin_*.py` is the contract for opt-in plugin
registration.

### 2.5 Architecture Boundary Tests

`tests/unit/test_architecture_boundaries.py` is the executable form of the
boundary rules. At time of writing it is in the thousands of lines and enforces
import direction rules between agents, capabilities, gateways, and shared
packages. New violations should be expected to surface here, not in code
review.

### 2.6 Non-Goals That Are Now Stable

The following items already stabilized in earlier PRs and should be left
alone:

- Canonical runtime identifiers after the 2026-05-10 brand unification
  (`wisdoverse-cell`, `wisdoverse_cell`, `Wisdoverse Cell`).
- Agent IDs and `cmp_wisdoverse_cell` company ID.
- Frontend Feature-Sliced Design layout (`entities/`, `features/`, `widgets/`).
- Per-agent PostgreSQL users and Redis DB numbers (ADR-0002).
- HTTP-only inter-agent contract (ADR-0004).
- Redis Streams EventBus with consumer groups and `dlq.failed` (ADR-0001).
- `/api/v1/control-plane/*` operator and service surface.

---

## 3. Remaining Backend Architecture Gaps

These gaps are tracked centrally in
[`docs/guides/backend-boundaries.md`](../guides/backend-boundaries.md) §6 and
recapitulated here for plan continuity. Where this plan adds detail beyond
that guide, it is called out explicitly.

| Gap | Why It Matters | Authoritative Reference |
|-----|----------------|-------------------------|
| Outbox tables share one database in the modular-monolith stage | Service extraction needs deployment evidence and a read-model strategy per runtime before this is broken apart | `backend-boundaries.md` §6 |
| Retired compatibility layers under `shared/services/*`, root `skills/*`, and `shared.grpc.server` | Closed: the compatibility packages and deprecated gRPC runtime entry point have been removed; tests use canonical paths | `backend-boundaries.md` §6, `project-layout.md` §"Current Structure Assessment" |
| Analysis can drift into source-table reads | Reporting code can become an implicit write owner of other domains | `backend-boundaries.md` §6 |
| Error response contract tests are still uneven at route level | Runtime APIs expose a structured envelope and base consumer tests prove the shared failure modes, but route-specific provider/consumer tests are not yet routine | `backend-boundaries.md` §6 |
| `users` lacks a dedicated public user/profile API boundary | Identity data can become shared mutable state if unrelated modules write directly | `backend-boundaries.md` §6 |
| Agent `core/` mixes use cases with domain rules and lifecycle helpers | Closed for tracked code architecture: product-owning runtimes now have explicit domain packages or documented gateway exclusions; chat-agent owns `ConversationTranscript` for history-trimming invariants, `CardOperationLogEntry` for card-operation log invariants, and `DailyProgressEntry` for daily-progress status transitions | [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §5.1 and DDD-002 |
| User Interaction Gateway compatibility access to chat-agent internals | Closed for code architecture: gateway production code calls chat-agent only through HTTP adapters, and legacy gateway core/db/model aliases for chat-agent product state have been removed | [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §5.12 and DDD-016 |
| Chat-agent conversation-engine composition | Closed for gateway purity: `ConversationEnginePort` / `ConversationEngineFactory` live inside `agents/chat_agent/core/chat_ports.py`, and gateway production code no longer imports chat-agent internals | [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §5.13 and DDD-017 |
| Coordinator `CoordinatorStateStore` is in-memory by default | No operator replay tooling for in-flight coordination state; closes Phase 1 audit §11 open question 2 | [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §5.14 and DDD-018 |
| Aggregates are anemic (Control Plane all 13; Sync; Analysis; Identity) | Domain logic lives in lifecycle modules and use cases, not on aggregates; weak invariants | [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §5.6 and DDD-001, DDD-003, DDD-005 |
| Sync capability still hosts OpenProject and Feishu Bitable in one runtime | The sub-boundaries are split inside `core/`, but a single runtime makes targeted scaling and failure isolation impossible | `architecture.md` §3.1, `SPEC.md` §4.1.3 |
| Each agent runtime still depends on shared Alembic migrations | A per-runtime migration story is required before any independent deployment | `backend-boundaries.md` §5 |
| Cross-agent contract tests are thin | Architecture import tests are strong; provider/consumer event and HTTP contract tests are not yet routine | Section 8 below |
| Observability dashboard coverage for outbox lag and DLQ growth is still thin | Cross-cutting Prometheus metrics now have a canonical `shared.observability.metrics` boundary with event queue, Redis DLQ, and oldest pending outbox age collectors; Alertmanager rules now cover outbox backlog age and DLQ growth/retention, but dashboard coverage and production threshold tuning are still incomplete | Section 7 below |

---

## 4. Recommended Next Phases

Phases are ordered by dependency. Each phase should land in its own PR and
should be reviewable in under a week of focused work. None of the phases below
are part of PR #121.

| Phase | Goal | Exit Criteria |
|-------|------|---------------|
| Phase A — Uniform Error Contract | Extend the `X-Error-Code` header and structured error model from Requirement APIs to PJM, QA, Dev, gateways, and capability modules | Runtime envelope is implemented through `create_agent_app()`; remaining exit criteria are consumer tests that assert classification and OpenAPI/API-reference alignment |
| Phase B — Domain Layer Per Agent | Introduce an explicit `core/domain/` layer per product-owning runtime (agents, capabilities, control plane, coordinator) for invariants, value objects, aggregates, and state machines separate from `*_use_cases.py`. Per-context exit criteria are tracked in [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §6 (DDD-001 through DDD-022). | `core/` no longer mixes lifecycle math with orchestration; architecture tests block use-case modules from importing adapters; every aggregate raises in-memory domain events drained by the use case |
| Phase C — Read-Model / Projection Boundary | Add an explicit projection layer that Analysis and reporting consume, instead of source tables | Analysis module imports only projection ports; backend-boundaries gap closed |
| Phase D — Sync Sub-Capability Split | Promote OpenProject sync and Feishu Bitable sync to two distinct capability runtimes (still under `shared/capabilities/sync/` package roots, but separately deployable) | Each sub-capability has its own outbox, repository module, and runtime plugin; compatibility endpoint orchestrates both |
| Phase E — Identity / User Boundary | Define a public user/profile service boundary and route all writes through it | `users` table has a single write owner; backend-boundaries gap closed |
| Phase F — Compatibility Surface Retirement | Remove `shared/services/*` and root `skills/*` shims once consumers are migrated | Both surfaces are deleted; architecture tests assert no new imports |
| Phase G — Per-Runtime Migration Story | Split Alembic ownership per runtime, or adopt a per-runtime migration tool | Each agent runtime owns its migration directory; tests cover migrate-and-rollback for each runtime |
| Phase H — First Real Service Extraction | Use the Dev agent or QA agent as the first independently deployed runtime (per `backend-boundaries.md` §2 posture) | One agent is deployed independently in a non-production environment, with documented outbox replay, projection, and rollback plan |

Phases A through C unblock service extraction (Phase H). Phases D through G
unblock independent deployment per runtime. Do not start Phase H before A–G
are landed and stable.

---

## 5. DDD / Clean Architecture Follow-Up Tasks

Strategic DDD is declared at the boundary rule level (`AGENTS.md`,
`SPEC.md`). Tactical DDD coverage is now measured per context in
[`ddd-compliance-audit.md`](./ddd-compliance-audit.md). The audit's §6
remediation roadmap (rows DDD-001 through DDD-022) is the authoritative
follow-up list; this section keeps the same headlines in summary form to
avoid drift.

1. Keep `core/domain/` mandatory for every product-owning runtime that
   owns stateful product records; gateways remain excluded (audit §5.1,
   DDD-002).
2. Keep lifecycle modules in `core/domain/lifecycle/`; architecture tests
   block the retired top-level duplicates (audit §5.2, DDD-020).
3. Add per-context ubiquitous-language glossary under each runtime's
   `README.md` linked to [`docs/overview/glossary.md`](../overview/glossary.md)
   (audit §5.11, DDD-009).
4. Audit every new `*_use_cases.py` for hidden infrastructure imports
   (audit §5.13, DDD-017; the User Interaction violation is closed).
5. Treat `shared/control_plane/` as one bounded context with 13 aggregates;
   do not split until aggregate roots and state machines are explicit
   (audit §4.1, DDD-001).
6. Document each aggregate root and its lifecycle in
   `docs/guides/backend-boundaries.md` §3 alongside table ownership.
7. Maintain the cross-agent core import block plus the boundary tests
   listed in the audit §6 PRs (DDD-002, DDD-011, DDD-014, DDD-016).

---

## 6. API / Event / Data Contract Follow-Up Tasks

Cross-boundary contracts are still the most fragile surface. Modularization
does not finish the job here.

### 6.1 HTTP / API

1. Roll out a uniform structured error body schema; preserve the existing
   FastAPI `detail` string and `X-Error-Code` header for compatibility until
   clients migrate (`backend-boundaries.md` §4).
2. Move every agent API handler into the "thin adapter" model:
   request validation, dependency injection, DTO conversion, error mapping,
   and response shaping only.
3. Publish per-agent OpenAPI snapshots and assert against them in CI to prevent
   silent contract drift.
4. Keep the operator-facing work-item execution command documented separately
   from the internal `/agent/request` envelope. `/work-items/{work_item_id}/run`
   is the product command; `/agent/request` remains the runtime adapter
   contract that must be stable before splitting any agent runtime.

### 6.2 Events

1. Every new EventBus event must continue to ship with a payload model under
   `shared/schemas/event_payloads.py` and a row in
   [`docs/guides/event-catalog.md`](../guides/event-catalog.md). This rule is
   already in `backend-boundaries.md` §4; the follow-up is to assert it in
   tests instead of code review.
2. Add provider/consumer contract tests for every event listed in the Event
   Catalog. The current architecture-boundary test enforces structure; it does
   not yet enforce payload compatibility.
3. Document idempotency strategy per event (stable `event_id`, domain
   idempotency key, or replay-safe handler). Update the Event Catalog rows.
4. Treat domain events (internal to one boundary) as private; treat events
   that cross the EventBus as part of the public contract. Promote any
   internal event to public only via the Event Catalog update workflow.

### 6.3 Data

1. Maintain the table-ownership matrix in
   `docs/guides/backend-boundaries.md` §3 as the single source of truth. Any
   new table must update that matrix in the same change.
2. Define read-model tables before Analysis consumes them; do not let Analysis
   read source-domain tables directly.
3. Plan per-runtime migration ownership before any agent moves out of the
   shared `migrations/` directory.
4. Document the projection strategy for Sync (OpenProject side, Feishu Bitable
   side) before Phase D split.

---

## 7. Observability Follow-Up Tasks

Run evidence is already first-class via the control-plane ledger and the
`ControlPlanePlugin`. The follow-up items target outbox delivery, queue
health, and provider boundaries.

1. Dashboard outbox-lag metrics per runtime
   (`wisdoverse-cell_outbox_pending_oldest_age_seconds`,
   dispatcher cycle duration, and dispatch outcome counters).
2. Dashboard EventBus `dlq.failed` size and rate per consumer group.
3. Add structured log fields for `trace_id`, `agent_id`, `work_item_id`,
   `run_id`, and `approval_id` consistently on every cross-boundary log line.
4. Expose health and readiness signals through `create_agent_app()` for every
   business agent and capability runtime, not only those that already do.
5. Add an LLM-cost dashboard backed by `shared/control_plane/budget_*` and
   `LLMGateway` evidence. Budget enforcement already exists; the operator view
   does not.
6. Define service-level indicators per boundary (latency, success rate, cost
   per run) and document them in `docs/guides/operations.md`.

---

## 8. Testing Follow-Up Tasks

The current test surface is strong on architecture import direction; it is
thinner on contract and integration coverage.

1. Keep `tests/unit/test_architecture_boundaries.py` as the executable form of
   the boundary rules. Add new rules here in the same change that introduces a
   new boundary.
2. Add provider/consumer contract tests per event and per HTTP endpoint that
   crosses a boundary. See §6.2 item 2.
3. Bring QA and PJM repository integration suites into the regression gate by
   provisioning local PostgreSQL on `127.0.0.1:5433` in CI, or by using
   testcontainers. The PR #121 verification note documents the current gap.
4. Add a smoke test that exercises every `*_event_outbox` dispatcher cycle.
   The dispatchers are now per-agent runtime plugins; a regression here is
   silent until operators notice missing events.
5. Add a smoke test that exercises `/agent/request` against every business
   agent in the default Compose `cell` topology.
6. Maintain `make test` as the canonical Python regression command; do not let
   any new runtime escape it without an explicit exclusion documented in the
   PR description.

---

## 9. What Should Not Be Changed Yet

These items are stable and should not be touched while Phases A through G are
in flight.

1. Public HTTP routes under `/api/v1/control-plane/*` and `/api/v1/*` shapes.
2. EventBus delivery model: Redis Streams, consumer groups, `dlq.failed`,
   at-least-once semantics.
3. Canonical runtime identifiers and agent IDs after the 2026-05-10 brand
   unification (see `AGENTS.md` Part 3 rule 13).
4. The control-plane ledger schema and aggregate set
   (`Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Approval`, `Budget`,
   `Artifact`, `AuditEvent`, `EvolutionProposal`).
5. The Rust edge gateway contract: protobuf-derived clients, `/ready`, and
   webhook intake paths.
6. The frontend Feature-Sliced Design layout. Backend changes must not push
   business logic into frontend slices.
7. The deployment topology defaults: one `cell` Compose product container with
   internal agent and capability runtimes; advanced split deployments are
   reserved for explicit migration work.
8. The HTTP-only inter-agent contract: no direct Python imports across
   independently deployed agents, no shared in-process service objects across
   boundaries.

---

## 10. Risk and Rollout Strategy

The backend evolution is incremental on purpose. Each phase below uses the
same rollout pattern.

### 10.1 Per-Phase Rollout

1. Land architecture or ports change behind compatibility shims when the new
   surface is not yet stable.
2. Add or update architecture-boundary tests in the same PR.
3. Update the relevant documentation (`AGENTS.md`, `SPEC.md`,
   `architecture.md`, `backend-boundaries.md`, Event Catalog, API Reference,
   this plan) in the same PR.
4. Verify with the stable backend regression and the focused subset for the
   touched agents.
5. Watch the next two weeks of operator evidence (outbox age, DLQ rate, run
   evidence completeness) before retiring the previous surface.

### 10.2 Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Use-case refactors leak infrastructure imports back into `core/` | Medium | Use cases become hard to test in isolation, defeats the modularization | Architecture-boundary test must forbid adapter imports from `core/**` |
| Outbox lag grows silently after phase B+ refactors | Medium | At-least-once delivery degrades to "best effort" without an alert | Keep `wisdoverse-cell_outbox_pending_oldest_age_seconds` on runtime dashboards and wire Phase 7 alert rules before any cross-boundary use-case rewrite |
| Read-model projection becomes a hidden write owner | Medium | Analysis ends up co-owning source domains, repeating the gap we are closing | Phase C requires explicit projection schema review |
| Service extraction starts before outbox + projection + migration story exists | High if attempted early | Premature split creates dual-write hazards and unrecoverable replay state | Do not start Phase H before A–G are landed |
| Compatibility shim retirement breaks external consumers | Low (source-available, no SaaS) | Existing self-hosted deployments require migration runbook | Each shim retirement ships with a release note and an upgrade step in `docs/guides/operations.md` |
| Documentation drifts from code | Medium | New contributors and agents follow stale rules | Every architecture PR must update the four anchor docs in the same change |

### 10.3 Reversibility

Every phase listed in §4 is reversible at the PR boundary. If a phase shows
operational regression, revert the PR and let the previous module shape stay.
The control-plane ledger and EventBus contracts are designed to survive
boundary refactors below them.

### 10.4 Definition of Done For This Plan

This document is considered up to date when:

- The "Current PR Scope" section reflects the most recently merged backend
  modularization PR.
- The phases in §4 either reflect open work or are removed when complete.
- The gaps in §3 line up with `docs/guides/backend-boundaries.md` §6.
- The rollout strategy in §10 matches the verification commands in
  `SPEC.md` §14.

When any of those drift, the plan must be reconciled before the next backend
architecture PR lands.
