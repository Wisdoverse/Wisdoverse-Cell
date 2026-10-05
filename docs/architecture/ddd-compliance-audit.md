# DDD Compliance Audit

Last updated: 2026-05-24

Status: Foundation document. Joins the Stage 0 architecture doc set under
`docs/architecture/`. Reconciles with
[`architecture-principles.md`](./architecture-principles.md),
[`module-boundaries.md`](./module-boundaries.md),
[`backend-evolution-plan.md`](./backend-evolution-plan.md),
[`backend-target-architecture.md`](./backend-target-architecture.md), and
[`backend-architecture-analysis.md`](./backend-architecture-analysis.md).
When this file changes, those siblings plus [AGENTS.md](../../AGENTS.md#boundaries) must be
reviewed in the same PR.

This audit grades every bounded context in the Wisdoverse Cell backend
against twelve tactical and strategic DDD dimensions. Each dimension is
scored against industry references (§3) and supported by `file:line`
evidence. The output is a remediation roadmap that slots into the existing
six-stage migration plan; no new stage is introduced.

The audit is read-only. No source code, schema, route, event, configuration,
or runtime artifact is modified in the audit-doc PR; remediation work
follows in separate PRs per
[`migration-plan.md`](./migration-plan.md) §Cross-Stage Rules.

---

## 1. Scope and Method

### 1.1 Contexts Audited

All bounded contexts catalogued in
[`module-boundaries.md`](./module-boundaries.md) §2 plus the two Sync
sub-boundaries that share a runtime:

| # | Context | Runtime owner |
|---|---------|---------------|
| 1 | Control Plane / Governance | `shared/control_plane/` |
| 2 | Requirement Management | `agents/requirement_manager/` |
| 3 | Planning / PJM | `agents/pjm_agent/` |
| 4 | Delivery / Dev | `agents/dev_agent/` |
| 5 | Quality / QA | `agents/qa_agent/` |
| 6a | Sync — OpenProject sub-boundary | `shared/capabilities/sync/` |
| 6b | Sync — Feishu Bitable sub-boundary | `shared/capabilities/sync/` |
| 7a | Interaction Gateway | `services/gateways/user_interaction/` |
| 7b | Channel Gateway | `services/gateways/channel/` |
| 8 | Coordination / Orchestration | `services/orchestration/coordinator/` |
| 9 | Analytics / Reporting | `shared/capabilities/analysis/` |
| 10 | Evolution | `shared/capabilities/evolution/`, `shared/evolution/` |
| 11 | Identity / User | `shared/messaging/inbound/user_service.py`, `shared/db/user_store.py` |
| 12 | Integration Plane | `shared/integrations/*` (adapter library, scored separately) |

Thirteen scorecards (§4.1–§4.13) grade product, gateway, and identity
contexts against the twelve dimensions in §1.2. The Integration Plane
(§4.14) is graded against a separate ACL sub-rubric because it is not a
bounded context. Remediation rows in §6 are numbered `DDD-NNN`; gap
descriptors in each scorecard cite the relevant `DDD-NNN` row.

### 1.2 Twelve DDD Dimensions

The twelve dimensions are derived from the references in §3. They are
binding for every business and capability context. Gateways (7a/7b) are
scored against a reduced set because they intentionally own no
product-domain records.

| # | Dimension | Question |
|---|-----------|----------|
| 1 | Bounded context defined | Is the ubiquitous language captured in a README or glossary near the runtime? |
| 2 | Aggregate root explicit | Is there a class (entity) that owns invariants and exposes methods that enforce them, or are invariants scattered across lifecycle modules and use cases? |
| 3 | Aggregate consistency boundary | Does a single use case write to exactly one aggregate per transaction? |
| 4 | Value objects | Are domain values modeled as immutable, equality-by-value types (frozen dataclasses or `model_config = ConfigDict(frozen=True)`)? |
| 5 | Entities (identity-based) | Are entity identities typed (NewType / value object) rather than raw `str`/`UUID`? |
| 6 | Domain services | Is cross-aggregate logic in a dedicated domain service, not stuffed into application use cases? |
| 7 | Domain events | Do aggregates raise in-memory domain events that the use case collects and forwards to the outbox? |
| 8 | State machine | Are state transitions modeled as a typed FSM (enum + transition table) with illegal-transition errors? |
| 9 | Repository pattern | Does the port live in `core/`, the adapter in `db/`, with no ORM `*Table` types escaping the store? |
| 10 | Application service purity | Are use cases free of SQL, HTTP, SDK, and config imports — depending only on ports? |
| 11 | Anti-corruption layer | Does every external integration translate the external model into a domain-friendly type at the adapter boundary? |
| 12 | Context-map relationship | Does the context document its upstream/downstream relationships (customer/supplier, conformist, ACL, partnership)? |

### 1.3 Scoring Legend

| Symbol | Meaning |
|--------|---------|
| ✓ | Fully compliant. Evidence cited. |
| ⚠ | Partial. Pattern exists in part of the context, or is implemented in a non-standard location. Gap descriptor explains. |
| ✗ | Missing. Evidence of absence cited. |
| n/a | Dimension does not apply (e.g. gateway contexts and domain services). |

Per-context summary line: `N ✓ / N ⚠ / N ✗ / N n/a (out of 12)`.

### 1.4 Method

1. Read-only evidence gathering across all thirteen scoring contexts plus
   the integration plane, collected by five parallel exploration passes.
   Evidence is `file:line`.
2. Scoring against the rubric in §1.2 and the references in §3. Each
   dimension's gap descriptor names the missing pattern, not the fix.
3. Cross-cutting patterns extracted in §5.
4. Remediation rows in §6 mapped to migration-plan stages.

This audit began as read-only evidence gathering. Later DDD remediation
PRs update the scoring history and current-state summaries in this file
as code changes land.

---

## 2. Executive Summary

The repository implements **strategic** DDD well: bounded contexts are
named, owned, and reconciled to runtime ownership in
[`module-boundaries.md`](./module-boundaries.md). Inter-context contracts
flow through HTTP, RPC, and the outbox-backed EventBus. ORM rows do not
cross boundaries. The Identity boundary has a single write owner per
[`identity-boundary.md`](./identity-boundary.md).

**Tactical** DDD has moved from uneven baseline to code-architecture
closure for the tracked remediation rows. Product-owning runtimes now
have explicit domain packages where stateful domain records exist, and
landed aggregates/value objects include Requirement, Decomposition, Task,
AcceptanceVerdict, AgentRun, EvolutionProposal, SyncOperation,
Analysis projections, and Chat Agent `ConversationTranscript`,
`CardOperationLogEntry`, and `DailyProgressEntry`. Remaining
work called out below is deployment evidence, route-level contract-test
depth, or tactical aggregate promotion when currently-simple records grow
real invariants.

The remediation sequence stayed inside the existing migration plan:
no new framework, no new stage, and no new runtime identifier.

Historical baseline aggregate compliance score across the thirteen contexts
from the original audit table (gateways score several dimensions as `n/a`
by design — see §4.9). Later rows in the scoring history below record
code-architecture closures and should not be read as a recomputed 156-cell
score unless this table is explicitly recalculated in the same PR:

| Status | Count | % of 156 cells | % excluding n/a |
|--------|-------|----------------|-----------------|
| ✓ Fully compliant | 85 | 54% | 56% |
| ⚠ Partial | 30 | 19% | 20% |
| ✗ Missing | 36 | 23% | 24% |
| n/a | 5 | 3% | — |

Scoring history (each landed `DDD-NNN` PR updates the totals here):

| PR | Net dimensional change | ✓ total |
|----|------------------------|---------|
| `4dcdd89f7` initial audit landing (#226) | baseline | 50 |
| `27a5a5d24` DDD-020 lifecycle cleanup (#226) | structural; no scorecard dimension flipped | 50 |
| #227 DDD-008 context-map relationships | dim 12 flipped from ✗/⚠ to ✓ across 12 contexts | 62 |
| #228–#247 batch (DDD-002/005/006/008/009/011/012/013/015/017/018/019/020/021/022 seeds + decisions) | dims 1 / 7 / 9 / 10 / 11 / 12 flipped across multiple contexts; aggregate seeds for Sync, Analysis, AgentRun, Evolution, UoW Coord/Evolution | 75+ |
| #248 DDD-001 first impl step (AgentRun FSM gates Control Plane wakeup transitions) | CP dims 2 + 8 flipped ⚠ → ✓ | 77 |
| #249 DDD-003 first impl step (sync engine.py uses typed FSM combiner) | both Sync sub-boundaries dim 8 flipped ✗ → ✓ (closes H4/P1-2) | 79 |
| #250 DDD-017 first impl step (chat_service uses ConversationEnginePort) | UIG dim 10 flipped ✗ → ✓ at module-level | 80 |
| #251 DDD-007 first impl step (WorkItemId NewType adoption) | CP dim 5 partial flip ⚠ → ✓ | 81 |
| #252 DDD-004 first impl step (in-memory projection adapter) | Analysis dim 9 ⚠ → ✓ (adapter ships though source-table reads remain pending) | 82 |
| #253 + #254 DDD-010 impl steps (Coord + Evolution UoW adapters) | Coord + Evolution dim 3/10 ⚠ → ✓ | 84 |
| #256 + #257 + #259 + #261 + #262 + #263 DDD-007 per-identifier adoption (Goal, AgentRun, ApprovalRequest, Decision, Artifact, BudgetPolicy) | CP dim 5 expanded coverage | 84 |
| #264 DDD-001 follow-up (runtime-plugin event runs gated by AgentRun FSM) | CP dims 2 + 8 strengthened for runtime path | 84 |
| #265 + #266 + #267 + #268 + #269 DDD-007 CompanyId adoption (17 control-plane ports) | CP dim 5 fully covered for CompanyId | 84 |
| #270 + #271 DDD-001 + audit-doc cleanup (delete `agent_run_lifecycle.py` shim + purge stale references) | CP `core/domain/` consistent with business agents | 84 |
| #273 + #274 DDD-003 follow-up (sub-engines `openproject_sync.py` + `feishu_bitable_sync.py` use SyncOperation FSM internally) | both Sync sub-boundaries strengthened — FSM-gated state across the full Sync runtime | 84 |
| #276 DDD-004 follow-up (SQLAlchemy projection adapter + Alembic migration for `analysis_work_package_projection` + `analysis_subtask_progress_projection` tables) | Analysis dim 9 strengthened — production-grade Published-Language projection persistence ships | 84 |
| #278 + #279 + #280 DDD-004 closure (ProjectionUpdater consumer + sync.completed wire + daily/weekly reports read from projection port) | Analysis dim 11 flipped ✗ → ✓ (Customer/Supplier with Sync/PJM now via Published-Language projection; §2.9 module-boundaries finding closed) | 85 |
| #282 DDD-018 replay tooling (`services/orchestration/coordinator/app/replay.py` + 6 unit tests) | Coordinator durability path strengthened — incident-response read-and-verify command lands; only the runbook bullet remains under ADR-0008 | 85 |
| #283 DDD-018 closure (replay-tool runbook lives next to coordinator/README.md) | Coordinator durability row fully closed | 85 |
| #284 DDD-006 closure for Control Plane | every product-owning runtime now raises aggregate domain events on state transitions | 86 |
| #285 DDD-013 agent-local adapter SDK-leak audit (recorded conclusion in row) | five agent-local adapters confirmed leak-free at public surface | 86 |
| #286 + #287 phantom-test promotion (DDD-015 + DDD-002 binding tests now actually exist) | aggregate→test mapping + lifecycle-canonical-path now enforced in `tests/unit/test_architecture_boundaries.py` | 86 |
| #288 DDD-002 Control Plane FSM consolidation (deleted duplicate `agent_run_lifecycle.py` aggregate; `TERMINAL_STATUSES` promoted to canonical `agent_run.py`; canonical-path test extended to Control Plane) | single source of truth for AgentRun FSM; lifecycle-canonical-path rule now enforced across business agents + Control Plane | 86 |
| #290 + #291 + #292 DDD-014 Step 1 internal split (sub-engines moved into `core/openproject/` + `core/feishu_bitable/` sub-packages; per-side outbox tables + Alembic migration shipped) | Sync sub-runtime boundary now explicit in directory layout; deployment cutover scheduled per ADR-0009 | 87 |
| #293 DDD-016 Step 1 skeleton (`agents/chat_agent/` runtime package with `ChatAgent` BaseAgent subclass + `create_agent_app` entry) | chat-agent runtime now has a landing site for the table + service moves scheduled per ADR-0010 | 87 |
| DDD-007 row closed for the current public Protocol surface | every public-signature consumer of an identifier is typed via `NewType`; remaining model-field-only identifiers are promoted when a future Protocol needs them | 88 |
| #295 DDD-005 EvolutionProposal aggregate (rollout FSM + typed `InvalidEvolutionRolloutTransitionError` + `EvolutionRolloutStatusChanged` event + 13 unit tests) | DDD-005 row closed for `EvolutionProposal`; trace/reflection/experiment aggregates promote when those records grow non-trivial state | 89 |
| #296 DDD-013 + DDD-022 closure (`OpenProjectWorkPackagePort` returns `OpenProjectWorkPackage` TypedDict at `shared/core/openproject_records.py`) | runtime shape unchanged; mypy can flag field-name typos at every `wp.get("...")` call site; both rows fully closed | 90 |
| #298 DDD-010 closure (first CoordinatorEventUseCase per-caller UoW migration; `service/agent.py` wires the factory; 2 new UoW-routed tests) | every product-owning runtime that needs a transaction boundary has UoW infra + at least one consuming use case | 91 |
| #299 DDD-016 Step 2 (chat-agent runtime owns `chat_agent_*` SQLAlchemy models + DatabaseManager) | chat-agent now owns the four chat product tables architecturally; gateway continues to dual-run during cutover per ADR-0010 | 92 |
| Current branch DDD-016 Steps 3-7 gateway boundary closure | `chat_service.py`, tool use cases, Bitable operation use cases, daily task use cases, ports, metrics, repositories, SQLAlchemy adapters, runtime service composition, scheduler, and the outbox dispatcher moved into `agents/chat_agent/`; the Control Plane catalog, frontend registry, Docker dispatcher, and cell supervisor now treat `agents.chat_agent` as the canonical `chat-agent` runtime; `/api/v1/chat-agent/conversation/{user_id}` and `/api/daily-progress` provide read endpoints, `/api/v1/chat-agent/requests` is the webhook chat request boundary, `/api/bitable/*` card-operation routes live under `agents/chat_agent/api/`, the gateway app/service/webhook path plus compatibility daily-progress/Bitable API routes call chat-agent through an HTTP client adapter, legacy gateway `core/`, `db/`, and `models/` aliases for chat-agent product state have been removed, and architecture tests forbid production gateway imports of `agents.chat_agent.*` | 100 |
| Current branch chat-agent `DailyProgressEntry` aggregate | `agents/chat_agent/core/domain/daily_progress.py` adds a typed daily-progress status FSM, `DailyProgressStatusChanged` event buffer, reported/completed status helpers, and chat-context status labels; repository batch-create/update paths now construct through the aggregate and drain status-change events for PII-safe observability, while chat service, daily reminders, and the update tool use the domain vocabulary instead of raw status string comparisons; aggregate-test coverage is bound in `test_business_aggregates_have_unit_tests` | 100 |
| Current branch chat-agent `ConversationTranscript` aggregate | `agents/chat_agent/core/domain/conversation.py` owns conversation-history message-limit trimming, serialized-size trimming, leading tool-replay safety, and `ConversationHistoryTrimmed` domain events; `ChatService` and `ConversationRepository` route history pruning through the aggregate; aggregate-test coverage is bound in `test_business_aggregates_have_unit_tests` | 100 |
| Current branch chat-agent `CardOperationLogEntry` aggregate | `agents/chat_agent/core/domain/card_operation.py` owns card-operation result normalization, failure-message validation, assignee extraction, snapshot serialization, and `CardOperationLogged` domain events; `record_op()` and `CardOperationRepository` route card-operation persistence through the aggregate; aggregate-test coverage is bound in `test_business_aggregates_have_unit_tests` | 100 |
| Current branch Control Plane `BudgetPolicy` aggregate | `shared/control_plane/domain/budget_policy.py` owns the `BudgetPolicy` aggregate, `active` / `paused` / `archived` lifecycle vocabulary, transition table, scope identity rules, limit/threshold validation, active-conflict predicate, and typed `BudgetPolicyCreated` / `BudgetPolicyUpdated` events; budget policy creation/update use cases now persist through the aggregate and drain audit summaries through the domain-event collector instead of hand-building budget audit rows | 100 |
| Current branch Control Plane `EvolutionProposal` rollout enforcement | `shared/control_plane/domain/evolution_proposal.py` owns the rollout approval policy and typed rollout-state parser; `update_evolution_proposal_status_with_audit()` now advances proposals through the aggregate FSM, so API callers must follow the domain path `proposed -> canary -> active` instead of bypassing the aggregate with direct `proposed -> active` writes | 100 |
| Current branch Control Plane `WorkItem` lifecycle aggregate | `shared/control_plane/domain/work_item.py` owns WorkItem lifecycle transitions, close-status policy, and AgentRun→WorkItem status mapping; work-item status updates now route through the aggregate, execution use cases ask the domain mapping for final state, and close commands use the domain close-status predicate; the FSM preserves operator reopen/retry behavior after `completed` while treating `cancelled` as closed | 100 |
| Current branch Control Plane `Decision` lifecycle aggregate | `shared/control_plane/domain/decision.py` owns Decision status transitions and typed `DecisionStatusChanged` events; decision status updates now route through the aggregate FSM before persistence/audit, and the API maps illegal transitions to `invalid_decision_transition` | 100 |
| Current branch Control Plane `Goal` lifecycle aggregate | `shared/control_plane/domain/goal.py` owns Goal status transitions, typed `GoalStatusChanged` events, cancelled-as-terminal policy, and the completed-progress rule; goal status updates now route through the aggregate FSM before persistence/audit, and the API maps illegal transitions to `invalid_goal_transition` | 100 |
| Current branch Control Plane `ApprovalRequest` lifecycle aggregate | `shared/control_plane/domain/approval_request.py` owns human-in-the-loop approval transitions, terminal resolved states, approved-status permission policy, and typed `ApprovalStatusChanged` events; `ApprovalGate` now routes approve/reject/ensure-approved through the aggregate before persistence, and the approval API maps illegal resolved-state rewrites to `invalid_approval_transition` | 100 |
| Current branch Control Plane budget value objects | `shared/control_plane/domain/budget_amount.py` adds immutable `BudgetAmount` and `BudgetWarningThreshold` value objects; budget policy use cases validate limit/threshold through them, and `BudgetGuard` uses `BudgetAmount` for non-negative estimates, recorded usage, addition, and limit comparison instead of ad hoc float arithmetic | 100 |
| Current branch Control Plane execution-link domain service | `shared/control_plane/domain/execution_links.py` centralizes run/work-item/goal link resolution for artifacts and decisions; artifact and decision creation still fetch records through their store ports, but mismatch detection and implied-link derivation now live in a reusable immutable domain value object instead of duplicated use-case conditionals | 100 |
| Current branch Control Plane domain-event base | `shared/control_plane/domain/events.py` adds the shared `ControlPlaneDomainEvent` base with `event_name` and `to_payload()`; AgentRun, EvolutionProposal, ApprovalRequest, Goal, WorkItem, Decision, Artifact, BudgetUsage, CompanyContext, AgentRole, and AgentPromptConfig event dataclasses now inherit it, giving aggregate-raised events a common in-memory contract before future outbox collection work | 100 |
| Current branch Control Plane domain-event audit collection | `shared/control_plane/domain_event_audit.py` adds the application-layer collector that turns aggregate-raised `ControlPlaneDomainEvent` instances into durable `AuditEvent` rows; Goal, WorkItem, Decision, EvolutionProposal, ApprovalRequest, AgentRun, Artifact, BudgetUsage, CompanyContext, AgentRole, and AgentPromptConfig status/creation/update paths now drain `pull_events()` through that boundary while preserving manual audit fallbacks for non-status changes | 100 |
| Current branch Control Plane approval-resolution domain service | `shared/control_plane/domain/approval_resolution.py` adds the explicit `ApprovalResolutionPolicy` domain service and immutable `ApprovalResolutionEffect` for the ApprovalRequest → EvolutionProposal consistency seam; the proposal-side handler resolves the effect through the domain service instead of embedding raw `ApprovalStatus.APPROVED` / `EvolutionRolloutState.REJECTED` branching in the application layer | 100 |
| Current branch Control Plane approval-resolution transaction split | `approval_use_cases.resolve_approval()` now resolves only the `ApprovalRequest` aggregate; `evolution_proposal_use_cases.apply_approval_resolution_to_linked_proposal()` and `apply_approval_resolution_event_to_linked_proposal()` apply the proposal-side effect through the EvolutionProposal store after the approval commit, while the approval route preserves immediate API compatibility through a second `ControlPlaneUnitOfWork` transaction | 100 |
| Current branch Control Plane wakeup adapter ACL | `shared/control_plane/domain/agent_wakeup_adapter.py` adds the immutable `AgentWakeupAdapterConfig` value object for persisted `AgentRole.adapter_type` / `adapter_config`; `agent_runner.py` and `scheduler.py` now interpret action, HTTP endpoint/path, command, timeout, heartbeat, and local allowlist decisions through that domain boundary instead of reading raw adapter dictionaries | 100 |
| Current branch Control Plane metadata value object | `shared/control_plane/domain/metadata.py` adds immutable `ControlPlaneMetadata` for JSON-friendly metadata/config payloads; CompanyContext, AgentPromptConfig, Artifact, AuditEvent detail, and AgentWakeupAdapterConfig now normalize keys, enum/date/sequence values, and metadata-key summaries through that value object before persistence or audit emission | 100 |
| Current branch Control Plane state-machine value object | `shared/control_plane/domain/state_machine.py` adds immutable `ControlPlaneStateMachine` for transition-table normalization, terminal-state derivation, and typed illegal-transition enforcement; AgentRole, AgentRun, ApprovalRequest, BudgetPolicy, Decision, EvolutionProposal rollout, Goal, and WorkItem lifecycle aggregates now route transition checks through that domain value object instead of ad hoc table membership checks | 100 |
| Current branch Control Plane domain-service contract | `shared/control_plane/domain/services.py` adds the shared `ControlPlaneDomainService` contract for stateless cross-aggregate policies; approval resolution, execution-link consistency, and budget active-conflict detection now implement that contract, and artifact/decision/budget use cases call the named policies instead of invoking value-object helpers or inline conflict checks directly | 100 |
| Current branch Control Plane domain-event outbox staging | `shared/control_plane/domain_event_outbox.py`, `event_outbox_store.py`, `tables.py`, and migration `20260526_control_plane_event_outbox.py` add durable `control_plane_event_outbox` staging for aggregate-raised Control Plane domain events; domain-event audit rows now derive immutable integration events in the same session before future dispatcher work | 100 |
| Current branch Control Plane `AgentRole` lifecycle aggregate | `shared/control_plane/domain/agent_role.py` adds the `AgentRole` aggregate, `AgentRoleStatus` published vocabulary, explicit runnability policy, terminal retired/terminated statuses, and typed `AgentRoleStatusChanged` events; status update use cases now transition through the aggregate and drain events into the Control Plane audit collector, while wakeup runnability checks ask the aggregate instead of duplicating stopped-status strings | 100 |
| Current branch Control Plane `AgentPromptConfig` aggregate | `shared/control_plane/domain/agent_prompt_config.py` adds the `AgentPromptConfig` aggregate, prompt length policy, actor normalization, metadata-key audit summary, and typed PII-safe `AgentPromptConfigUpdated` event; prompt-config updates now construct/update the aggregate before persistence and drain events through the Control Plane audit collector instead of hand-building audit rows in the helper | 100 |
| Current branch Control Plane `Artifact` aggregate | `shared/control_plane/domain/artifact.py` adds the `Artifact` aggregate, evidence title/URI normalization, execution-link materialization, persistence-ready type conversion, and typed PII-safe `ArtifactCreated` event; artifact creation and automatic run-evidence creation now pass through the aggregate and audit collector instead of hand-building artifact-created audit rows | 100 |
| Current branch Control Plane `CompanyContext` aggregate | `shared/control_plane/domain/company_context.py` adds the `CompanyContext` aggregate, required company-name policy, mission/metadata normalization, and typed PII-safe `CompanyContextCreated` / `CompanyContextUpdated` events; company create/update use cases now persist through the aggregate and drain audit summaries through the domain-event collector instead of hand-building company audit rows | 100 |
| Current branch Control Plane `BudgetUsage` aggregate | `shared/control_plane/domain/budget_usage.py` adds the `BudgetUsage` aggregate, non-negative cost policy, token-count normalization, required model/tool identifier, and typed `BudgetUsageRecorded` event; `BudgetGuard.record_usage()` now records through the aggregate and drains audit summaries through the domain-event collector while the existing `budget.usage-recorded` EventBus publication remains unchanged | 100 |
| Current branch Control Plane `AuditEvent` aggregate | `shared/control_plane/domain/audit_event.py` adds the append-only `AuditEvent` aggregate, required target/action identity policy, actor/idempotency normalization, and recursive JSON-friendly detail normalization; `audit_event_store.append_audit_event()` now normalizes every manual and domain-event-collected audit row through the aggregate before idempotency lookup and persistence, while `domain_event_audit.py` reuses the same detail normalizer to avoid divergent audit payload rules | 100 |
| Current branch Control Plane aggregate catalog | `shared/control_plane/domain/aggregate_catalog.py` adds `CONTROL_PLANE_AGGREGATES`, a domain-owned catalog of the 13 aggregate-root module/test pairs: `shared/control_plane/domain/company_context.py` -> `shared/control_plane/tests/test_company_context_aggregate.py`, `shared/control_plane/domain/goal.py` -> `shared/control_plane/tests/test_goal_aggregate.py`, `shared/control_plane/domain/agent_role.py` -> `shared/control_plane/tests/test_agent_role_aggregate.py`, `shared/control_plane/domain/work_item.py` -> `shared/control_plane/tests/test_work_item_aggregate.py`, `shared/control_plane/domain/agent_run.py` -> `shared/control_plane/tests/test_agent_run_aggregate.py`, `shared/control_plane/domain/decision.py` -> `shared/control_plane/tests/test_decision_aggregate.py`, `shared/control_plane/domain/approval_request.py` -> `shared/control_plane/tests/test_approval_request_aggregate.py`, `shared/control_plane/domain/budget_policy.py` -> `shared/control_plane/tests/test_budget_policy_domain.py`, `shared/control_plane/domain/budget_usage.py` -> `shared/control_plane/tests/test_budget_usage_aggregate.py`, `shared/control_plane/domain/artifact.py` -> `shared/control_plane/tests/test_artifact_aggregate.py`, `shared/control_plane/domain/audit_event.py` -> `shared/control_plane/tests/test_audit_event_aggregate.py`, `shared/control_plane/domain/evolution_proposal.py` -> `shared/control_plane/tests/test_evolution_proposal_aggregate.py`, and `shared/control_plane/domain/agent_prompt_config.py` -> `shared/control_plane/tests/test_agent_prompt_config_aggregate.py`; `shared/control_plane/tests/test_aggregate_catalog.py` verifies catalog immutability/module exports, and `tests/unit/test_architecture_boundaries.py::test_business_aggregates_have_unit_tests` now derives the Control Plane aggregate guard from this catalog instead of a duplicated literal list | 100 |
| Current branch Evolution experiment aggregate | `shared/evolution/domain/experiment.py` adds the `EvolutionExperiment` aggregate for mini-canary routing, new-experiment traffic normalization, score summaries, minimum-sample checks, optimizer promotion thresholds, and rollback decisions; `shared/evolution/canary_router.py` and `shared/evolution/skill_optimizer.py` now ask the aggregate for bucket routing and promote/rollback decisions before repository status writes; `shared/evolution/tests/test_experiment_aggregate.py` and `tests/unit/test_architecture_boundaries.py::test_evolution_proposal_value_objects_own_scope_and_context_map` guard the aggregate boundary | 100 |
| Current branch Integration Plane port-surface alignment | `shared/core/__init__.py` now exports `WecomMessengerPort` and `OpenClawIntegrationPort` beside `OpenProjectWorkPackagePort`; `tests/unit/test_integration_ports.py` and `tests/unit/test_architecture_boundaries.py::test_integration_plane_ports_are_exported_and_documented` guard the public port surface; `module-boundaries.md` and this audit now reflect the already-typed `OpenProjectWorkPackage` TypedDict return boundary plus the named WeCom/OpenClaw ports instead of the stale Integration Plane leak descriptions | 100 |
| Current branch QA `AcceptanceRun` aggregate | `agents/qa_agent/core/domain/acceptance_run.py` adds the `AcceptanceRun` aggregate root, typed `AcceptanceRunCompleted` domain event, run-completion invariants, blocking-finding selection, and `pull_events()` buffer; `build_acceptance_events()` now constructs QA integration events from the aggregate-raised completion event instead of rebuilding blocking semantics directly in the application use case | 100 |
| Current branch QA `AcceptanceRunId` identity adoption | `shared/core/identifiers.py` already exposes `AcceptanceRunId`; QA run-store ports/adapters, run query use cases, API/request ports, service facade, and outbox publishing now use that typed identity at internal boundaries while preserving the external JSON `run_id` string contract | 100 |
| Current branch Control Plane `EvolutionProposalId` identity adoption | `shared/core/identifiers.py` already exposes `EvolutionProposalId`; Control Plane evolution-proposal ports/adapters and status/get use cases now use `EvolutionProposalId`, `ApprovalRequestId`, and `CompanyId` at internal persistence boundaries while preserving external API path/body strings | 100 |
| Current branch Control Plane `AgentRoleId` identity adoption | `shared/core/identifiers.py` already exposes `AgentRoleId`; agent-registry ports/adapters/use cases plus bootstrap, agent-operation, and prompt-configuration delegated role lookups now use `AgentRoleId` at internal persistence boundaries while preserving external `agent_id` strings | 100 |
| Current branch Requirement Manager `RequirementId` identity adoption | `shared/core/identifiers.py` already exposes `RequirementId`; Requirement Manager requirement-store ports/adapters, SQL repository, mutation workflow, and command/mutation use cases now use `RequirementId` at internal persistence and lifecycle-mutation boundaries while preserving external API/agent `requirement_id` strings | 100 |
| Current branch Requirement Manager `MeetingId` identity adoption | `shared/core/identifiers.py` already exposes `MeetingId`; Requirement Manager meeting-store ports/adapters, SQL repository, read-query use cases, and ingest `mark_processed` path now use `MeetingId` at internal persistence/read boundaries while preserving external API/agent `meeting_id` strings and integration-event payloads | 100 |
| Current branch Requirement Manager `OpenQuestionId` identity adoption | `shared/core/identifiers.py` already exposes `OpenQuestionId`; Requirement Manager question-store ports/adapters, SQL repository, mutation workflow, command use case, and feedback use case now use `OpenQuestionId` at the internal answer-question boundary while preserving external API/agent `question_id` strings | 100 |
| Current branch Requirement Manager `FeedbackRecordId` identity adoption | `shared/core/identifiers.py` already exposes `FeedbackRecordId` and now generates `fb_` identifiers; Requirement Manager feedback-store ports/adapters and SQL repository use `FeedbackRecordId` for feedback lookup/mark-used boundaries and `RequirementId` for feedback-by-requirement lookup, while feedback-learning maps the typed ID back to the ORM string field at persistence | 100 |
| Current branch Requirement Manager feedback-learning domain service | `agents/requirement_manager/core/domain/feedback_learning.py` adds `RequirementFeedbackLearningPolicy`, immutable extraction snapshots, and feedback drafts for correction/rejection classification; `core/feedback_learning.py` now delegates feedback type, rejection placeholder, and changed-field decisions to the domain service before mapping to the persistence model through `RequirementFeedbackStore` | 100 |
| Current branch Requirement Manager context-map guard | `agents/requirement_manager/README.md` now serves as the runtime-local DDD context map with owned tables, ubiquitous language, upstream ACLs, downstream Customer/Supplier relationship to PJM, and Control Plane Conformist relationship; `tests/unit/test_architecture_boundaries.py::test_requirement_manager_readme_documents_ddd_context_map` locks the README against the module-boundaries catalog | 100 |
| Current branch Requirement Manager Feishu-card ACL seam | Requirement Manager composition and Feishu integration code now import card rendering through agent-local adapter/shim paths (`adapters/feishu_cards.py`, `integrations/feishu/cards/requirement.py`) while the concrete reusable renderer remains in `shared/integrations/feishu/cards/requirement.py`; `test_requirement_manager_feishu_card_acl_uses_local_adapter_path` forbids direct shared card-schema imports from the app and integration handlers | 100 |
| Current branch Requirement Manager Feishu event inbound ACL | `agents/requirement_manager/integrations/feishu/acl.py` adds immutable `FeishuMeetingEndedEvent` and `FeishuRequirementCalendarEvent` translation objects for Feishu meeting-ended and calendar payload trees; `integrations/feishu/event.py` now consumes the ACL objects for Requirement ingest fields, keyword filtering, start-time labels, attendees, and reminder-card kwargs instead of parsing nested Feishu payloads inline | 100 |
| Current branch Requirement Manager Feishu bot-message inbound ACL | `agents/requirement_manager/integrations/feishu/acl.py` adds immutable `FeishuBotMessage` and `FeishuBotCommand` translation objects for Feishu bot message payloads, JSON text extraction, command detection, and Requirement ingest kwargs; `integrations/feishu/bot.py` now consumes those local ACL objects instead of parsing Feishu message payloads or command regexes inline | 100 |
| Current branch Requirement Manager Feishu card-action inbound ACL | `agents/requirement_manager/integrations/feishu/acl.py` adds immutable `FeishuCardAction` translation for interactive-card callback payloads, operator IDs, Requirement IDs, pagination, batch IDs, rejection reasons, and PJM work-package IDs; `integrations/feishu/card.py` now consumes that local ACL object instead of reading `action.value`, `form_value`, or `operator.open_id` directly | 100 |
| Current branch Requirement Manager Feishu card-action response model | `agents/requirement_manager/integrations/feishu/acl.py` adds immutable `FeishuCardActionResponse` for callback toast/card payloads; `integrations/feishu/card.py` now returns the local response object's `to_payload()` output for success, error, info, and card-only responses instead of constructing raw Feishu callback dictionaries inline | 100 |
| Current branch Requirement Manager Feishu router adapter | `agents/requirement_manager/integrations/feishu/router.py` wraps the shared Feishu webhook router and handler registration behind `register_requirement_feishu_handlers()`; `app/main.py` now includes the Feishu webhook router through the Requirement-local integration package, and `init_feishu_gateway()` registers handlers through the local adapter instead of importing the shared router module directly | 100 |
| Current branch production lifecycle boundary closure | Requirement Manager confirmation/rejection/update, PJM decomposition status writes, and Dev task status/expiry writes now construct the owning aggregate and call the aggregate FSM before persistence; QA notification no longer has a direct EventBus publish fallback and relies on the acceptance outbox summary supplied by `QAAcceptanceExecutionUseCase`; `tests/unit/test_architecture_boundaries.py` guards aggregate use in production mutation paths, chat-agent cross-agent import coverage, QA no-direct-publish behavior, and full EventTypes-to-payload-model parity | 100 |
| Current branch Requirement Manager LLM extraction-response ACL | `agents/requirement_manager/core/llm_extraction_response.py` adds immutable `LLMExtractionResponse` / `LLMExtracted*` response models for raw LLM Gateway extraction JSON, Markdown-fence cleanup, category normalization, priority normalization, and malformed-item filtering; `core/extractor.py` now consumes that local ACL instead of parsing `json.loads()` and external labels inline | 100 |
| Current branch Requirement Manager aggregate-consistency policy | `agents/requirement_manager/core/domain/aggregate_consistency.py` adds `RequirementAggregateConsistencyPolicy`, immutable `RequirementTransactionScope`, and typed consistency errors for the allowed immediate-consistency write scopes: meeting ingest, Requirement lifecycle mutations with optional feedback evidence, question answers, outbox staging, and post-commit side effects; `meeting_ingest_workflow.py` and `requirement_mutation_workflow.py` now assert their declared aggregate write sets before UoW writes | 100 |
| Current branch Interaction Gateway webhook value object | `services/gateways/user_interaction/core/webhook_intake.py` promotes `FeishuWebhookMessage` to a frozen slotted value object with local `from_webhook_body()` translation and `text_content()` normalization; webhook intake now carries immutable primitive message fields rather than a mutable raw Feishu message dictionary | 100 |
| Current branch Requirement Manager meeting-source value object | `agents/requirement_manager/core/domain/meeting_source.py` adds immutable `MeetingSourceMetadata` for meeting source, source-system ID, title, meeting date, participants, and context; `meeting_ingest_workflow.py` now derives Meeting constructor fields and extractor arguments from that value object instead of duplicating ad hoc participant/date/source mapping | 100 |
| Current branch Requirement Manager PRD composition value objects | `agents/requirement_manager/core/domain/prd_document.py` adds immutable `PRDDocumentDraft` and `PRDRequirementSnapshot`; PRD prompt metadata, requirement payloads, and fallback ordering now derive from the domain draft instead of ad hoc generator dictionaries and sort lambdas | 100 |
| Current branch Requirement Manager extraction materialization domain service | `agents/requirement_manager/core/domain/extraction_materialization.py` adds immutable extraction requirement/question drafts and `RequirementExtractionMaterializer`; `meeting_ingest_workflow.py` now delegates extractor-result traversal, source-meeting association, and the current first-requirement open-question assignment rule to the domain plan before mapping drafts to ORM models | 100 |
| Current branch Requirement Manager extraction-publication domain service | `agents/requirement_manager/core/domain/extraction_materialization.py` adds `RequirementExtractionPublicationPolicy`, immutable persisted-requirement summaries, and `RequirementExtractionPublication`; `meeting_ingest_workflow.py` now delegates `requirement.extracted` payload shape, published requirement ID ordering, and search-index document construction to the domain publication projection before staging outbox events or invoking the vector-index port | 100 |
| Current branch PJM `WorkPackageId` workflow boundary | `shared/core/identifiers.py` exposes `WorkPackageId`; `agents/pjm_agent/core/domain/decomposition.py`, `core/decomposition_ports.py`, `db/decomposition_store.py`, `core/decomposition_request_workflow.py`, `core/decomposition_approval_workflow.py`, and `core/decomposition_recovery_workflow.py` now type the decomposition aggregate and request/approve/recover/persistence identity as `WorkPackageId`, while `DecompositionOrchestrator` converts external REST/agent/event integer IDs before workflow calls | 100 |
| Current branch PJM Feishu card ACL | `agents/pjm_agent/adapters/feishu_card_acl.py` adds immutable `FeishuDecompositionApprovalCard` and `FeishuTaskRefinementApprovalCard` translation objects plus `PJMFeishuCardACL`; `service/agent.py` now injects `PJMFeishuCardACL(FeishuPJMCardRenderer())` so PJM decomposition workflow data is converted to primitive Feishu renderer payloads at an agent-local adapter boundary while concrete card schema rendering remains in `shared/integrations/feishu/cards` | 100 |
| Current branch PJM decomposition workflow policy | `agents/pjm_agent/core/domain/decomposition_policy.py` adds `DecompositionWorkflowPolicy`, immutable intake/retry decisions, and the one-meaningful-decomposition-per-`WorkPackageId` status rules; `decomposition_request_workflow.py` and `decomposition_recovery_workflow.py` now ask the domain policy before skipping/replacing existing records or retrying failed decompositions | 100 |
| Current branch PJM value-object completion | `shared/core/identifiers.py` exposes `OpenProjectProjectId`; `core/domain/lifecycle/decomposition_lifecycle.py` defines typed `DecompositionStatus`; `core/domain/decomposition_values.py` adds immutable `DecompositionRejectionReason`; decomposition ports, request/approval/recovery workflows, the aggregate, and OP writer ports now consume typed IDs/status/reason at internal boundaries while preserving primitive API/event contracts | 100 |
| Current branch Dev value-object and policy completion | `shared/core/identifiers.py` exposes `DevTaskId` and `WorkPackageId`; `agents/dev_agent/core/domain/lifecycle/task_lifecycle.py` defines typed `TaskStatus`; `core/domain/task_values.py` owns `RiskLevel`; `core/domain/delivery_policy.py` owns automatic-delivery rejection, HITL workflow approval, capacity, and QA retry decisions; Dev core ports/use cases now consume those internal domain types while preserving primitive API/event payloads | 100 |
| Current branch Dev README and consistency boundary | `agents/dev_agent/README.md` now defines the Dev bounded context, local vocabulary, one-Task-per-`WorkPackageId` rule, WorkflowLog-as-task-history boundary, context-map relationships, and event directions; `tests/unit/test_architecture_boundaries.py::test_dev_agent_domain_owns_task_value_objects_and_policy` guards the value-object/policy boundary | 100 |
| Current branch QA inbound acceptance-request ACL | `agents/qa_agent/adapters/acceptance_request_acl.py` adds `QAAcceptanceRequestACL`, immutable `QAAcceptanceRequestEnvelope`, `GitLabMergeRequestContext`, and optional `OpenProjectWorkPackageContext` translation objects for `code.committed` / `qa.run-requested`; `core/event_use_cases.py` now depends on `QAAcceptanceRequestTranslatorPort` instead of parsing shared event payloads directly, and `service/agent.py` injects the local ACL | 100 |
| Current branch Sync value objects and typed ports | `shared/capabilities/sync/core/domain/sync_values.py` adds immutable `WorkPackageData`, `FeishuRecordData`, typed `FeishuRecordId`, `FeishuSubtaskStatus`, and completion-status helpers; `core/mapper.py` now returns those domain values, `core/progress.py` uses the status helper, and `core/sync_ports.py` replaces generic `object` return values with typed sync log / mapping records | 100 |
| Current branch Sync mapping domain records | `shared/capabilities/sync/core/domain/sync_values.py` adds `SyncMappingRecord`, `SubtaskMappingRecord`, `SyncMappingId`, and `SyncSubtaskMappingId`; mapping repositories and sync store ports now return typed domain records instead of SQLAlchemy `SyncMapping` / `SubtaskMapping` rows, preserving API read-model shape while removing ORM leakage from core mapping paths | 100 |
| Current branch Sync projection policy | `shared/capabilities/sync/core/domain/sync_values.py` adds `SyncProjectionPolicy`, `SyncMappingDecision`, `ParentSubtaskRollup`, and `FeishuSubtaskRollupItem`; OpenProject sync now asks the policy whether to create/update Feishu rows and validates OP/project mapping conflicts before persistence, while Feishu Bitable sync asks the policy to normalize parent-linked subtasks and compute parent progress rollups before updating OpenProject | 100 |
| Current branch Sync progress-update event | `EventTypes.SYNC_PROGRESS_UPDATED`, `SyncProgressUpdatedPayload`, `FeishuBitableSyncOperation.stage_event()`, and `core/feishu_bitable/engine.py` now make Feishu parent-progress writes outbox-backed integration events; the event catalog documents the compact payload and runtime retry path | 100 |
| Current branch Identity/User aggregate and value objects | `shared/core/identity_domain.py` adds immutable `PlatformUserRef`, `EmailAddress`, `PhoneNumber`, derived `IdentityState`, and in-memory `UserCreated` / `PlatformLinked` / `UserActivated` events; `shared/models/user.py` now owns `create_identity()`, `link_platform_account()`, `record_activity()`, and `pull_domain_events()`, while `UserService` constructs `PlatformUserRef` and delegates field mutation to the aggregate | 100 |
| Current branch Identity resolution core use case | `shared/core/identity_resolution.py` owns the port-driven `IdentityResolutionUseCase`, `IdentityResolutionResult`, and `IdentityPlatformDirectoryPort`; `UserService` now imports that core boundary and keeps only cache/session/serialization shell concerns, while the retired inbound-local use-case module is removed | 100 |
| Current branch Identity/User domain-event outbox staging | `shared/core/identity_event_outbox.py`, `shared/db/identity_event_outbox_store.py`, `shared/models/identity_event_outbox.py`, and migration `20260527_identity_event_outbox.py` add PII-safe `identity.*` integration-event staging for aggregate-raised identity domain events; `UserService` stages the events in the same session before committing the resolved user | 100 |
| Current branch Analysis report aggregate | `shared/capabilities/analysis/core/domain/report.py` adds `GeneratedAnalysisReport`, immutable report stats/value objects, typed report kind/status vocabulary, and `AnalysisReportGenerated` in-memory events; daily/weekly generators now build response payloads through the aggregate while preserving external JSON shape | 100 |
| Current branch Analysis report-log domain record | `shared/capabilities/analysis/core/domain/report_log.py` adds `AnalysisReportLogRecord`, typed `AnalysisReportLogId`, and generated→pushed transition validation for persisted report logs; `ReportLogRepository` now maps SQLAlchemy `ReportLog` rows into domain records and no longer returns ORM objects to callers | 100 |
| Current branch Analysis Feishu task ACL | `shared/capabilities/analysis/core/domain/feishu_task.py` adds `AnalysisFeishuTaskSnapshot`, `AnalysisFeishuTaskStatus`, and `AnalysisFeishuTaskACL`; daily/weekly report generators now translate Analysis projection rows into Feishu task snapshots before computing stats or formatting blocked/completed task details | 100 |
| Current branch Analysis assessment value objects | `shared/capabilities/analysis/core/domain/assessment.py` adds `MilestoneRiskSignal`, `AnalysisRiskSeverity`, `AnalysisRiskType`, `DeliverableQualityTask`, `QualityEvaluation`, `AnalysisQualityVerdict`, and `DeliverableQualityResult`; `MilestoneChecker` and `QualityEvaluator` now compute risk/quality through those value objects before returning legacy primitive API/event payloads | 100 |
| Current branch Analysis task-read projection closure | `SubtaskProgressProjection` now carries title, blocked reason, and feature identity in the durable Analysis projection; `DailyReportGenerator`, `WeeklyReportGenerator`, and `MilestoneChecker` read Feishu task data through `WorkPackageProjectionPort.list_subtask_progress()` instead of `BitableTablePort`, leaving Bitable reads at the projection updater/ACL boundary and closing the remaining Analysis application-service purity gap | 100 |
| Current branch Analysis report delivery command | `shared/capabilities/analysis/core/report_delivery_use_cases.py` adds `AnalysisReportDeliveryUseCase` so report generation, chat push, metrics, and report integration-event payload construction live behind one application command boundary; `event_use_cases.py` delegates daily/weekly delivery to that command instead of interleaving report delivery logic with sync-completed orchestration | 100 |
| Current branch Coordinator dispatch policy | `services/orchestration/coordinator/core/domain/dispatch.py` adds `CoordinatorDispatchPolicy`, target/relationship value objects, and primitive dispatch envelopes; `core/dispatcher.py` delegates target-specific event mapping to the domain policy instead of hardcoding target-agent strings in the adapter | 100 |
| Current branch Coordinator workflow-state aggregate | `services/orchestration/coordinator/core/domain/workflow_state.py` adds `CoordinatorWorkflowState`, typed workflow statuses, transition guards, participant uniqueness, phase updates, and `CoordinatorWorkflowStatusChanged` in-memory events; in-memory and Postgres state stores validate workflow writes through the aggregate before persistence | 100 |
| Current branch Coordinator state-record identities | `services/orchestration/coordinator/core/domain/state_records.py` adds `CoordinatorAgentStateRecord`, `CoordinatorDecisionRecord`, typed agent/decision/workflow/task identifiers, and `CoordinatorAgentStatus`; in-memory and Postgres state stores now return these domain records from agent-state and pending-decision reads while preserving replay/context `model_dump()` compatibility | 100 |
| Current branch Coordinator scratchpad consistency | `services/orchestration/coordinator/core/domain/scratchpad.py` adds `CoordinatorScratchpadProjectionPlan` and `CoordinatorScratchpadConsistencyPolicy`; `CoordinatorEventUseCase` now persists decisions through the state-store/UoW boundary before applying the scratchpad projection, and compaction is scheduled only after the projection is safe | 100 |
| Current branch Channel Gateway outbox lifecycle/context map | `services/gateways/channel/core/outbox_lifecycle.py` adds `ChannelGatewayOutboxLifecycle`, typed outbox statuses, retry/publish transition guards, and terminal published-state protection; `db/repository.py` now stages, retries, and publishes through that policy, while the runtime README and module-boundaries catalog classify the Channel Gateway Open-Host Service, Customer/Supplier, ACL, and Conformist relationships | 100 |
| Current branch Channel Gateway provider ACL | `services/gateways/channel/core/provider_acl.py` adds `ChannelProviderACL`, provider adapter/registry Protocols, and gateway-local delivery request/response values; `core/event_use_cases.py` now translates missing adapters and provider exceptions through that ACL before emitting `channel.message.delivered` | 100 |
| **All 22 audit rows now closed at code-architecture state** | the codebase DDD refactor is complete at the code boundary; remaining deployment-coordinated cutovers are operations work per the matching ADRs (especially ADR-0009) and do not require further DDD redesign | **100** |

All 22 audit rows now have at least one remediation PR. Rows fully
closed at code-architecture state: DDD-001 through DDD-022 (**22 of
22**). DDD-014 still carries an ADR-managed deployment cutover; its
code architecture is complete but the runtime split is
operator-scheduled. DDD-016/017 are closed for the User Interaction
Gateway code boundary: gateway production code no longer imports
chat-agent internals, no longer owns chat-agent product models/adapters,
and calls chat-agent through HTTP adapters.

Evolution now scores **12 ✓ / 0 ⚠ / 0 ✗**. It has an explicit
`EvolutionRolloutState` FSM, port-based stores, pure use cases, local
proposal value objects, a runtime `EvolutionExperiment` aggregate, and an
established `ApprovalGate` domain service.

All graded bounded contexts now score **12 ✓ / 0 ⚠ / 0 ✗** at the
code-architecture level. Control Plane deliberately remains the central
ledger, but the ApprovalRequest → EvolutionProposal follow-up now runs
outside the initiating approval transaction.

Highest-risk residual operations item: **Sync runtime deployment split
remains operator-scheduled**. The code architecture has separate
OpenProject and Feishu Bitable sub-boundaries, stores, and outboxes, but
ADR-0009 Step 2 still needs staged deployment evidence before the
legacy single `sync-module` runtime is retired.

Residual follow-ups outside the code-architecture closure:

- Chat-agent now has `ConversationTranscript`, `CardOperationLogEntry`,
  and `DailyProgressEntry` tactical aggregates for its three owned
  product record families.
- ADR-0009 Step 2 still needs the staged deployment cutover for the sync
  sub-runtime split.
- Route-specific HTTP provider/consumer contract coverage remains thinner
  than the architecture-boundary coverage.

---

## 3. Standards Referenced

This audit grades against the following industry references. Each
dimension in §1.2 maps to at least one of them.

| Reference | Scope | Maps to dimensions |
|-----------|-------|--------------------|
| Evans 2003 (Domain-Driven Design) | Tactical patterns: aggregate, entity, value object, repository, domain service, factory, ubiquitous language | 1, 2, 3, 4, 5, 6, 9 |
| Vernon 2013 (Implementing Domain-Driven Design) | Aggregate design rules: one aggregate per transaction, small aggregates, eventual consistency between aggregates | 2, 3, 7 |
| Cockburn 2005 (Hexagonal Architecture) | Ports and adapters; anti-corruption layer placement | 9, 10, 11 |
| Martin 2017 (Clean Architecture) | Layering: domain depends on nothing; application depends on ports | 9, 10 |
| Young 2010 (CQRS) | Read-model and command separation; used selectively for Analysis projection | 9, 10 |
| Percival & Gregory 2020 (Cosmic Python) | Python-native UoW, repository, message bus, port discipline | 6, 7, 9, 10 |
| Microsoft eShopOnContainers (2017+) | DDD reference implementation; aggregate state machines | 2, 7, 8 |
| Brandolini Context Mapping (DDD-CRC) | Upstream/downstream relationships, conformist/ACL patterns | 12 |
| Fowler 2003 (Patterns of Enterprise Application Architecture) | Repository, Unit of Work, Application Service | 6, 9, 10 |

Where this repository's stack-specific decisions differ from a reference
(for example, FastAPI dependency injection in place of constructor
injection, or async SQLAlchemy 2.x UoW in place of a session-per-request
servlet pattern), the audit grades against the spirit of the reference,
not the literal pattern.

---

## 4. Per-Context Scorecards

Each scorecard cites `file:line` evidence. Gap descriptors name the
missing pattern; remediation lives in §6.

### 4.1 Control Plane / Governance

- Runtime owner: `shared/control_plane/`
- Aggregates inventory: Company, Goal, AgentRole, WorkItem, AgentRun, Decision, ApprovalRequest, BudgetPolicy, BudgetUsage, Artifact, AuditEvent, EvolutionProposal, AgentPromptConfig; the canonical source is `CONTROL_PLANE_AGGREGATES` in `shared/control_plane/domain/aggregate_catalog.py`.
- `core/domain/` present: yes — `shared/control_plane/domain/` is the canonical home. The legacy shim at `shared/control_plane/agent_run_lifecycle.py` was deleted; all callers import from `shared/control_plane/domain/lifecycle/agent_run_lifecycle.py`. `shared/control_plane/domain/aggregate_catalog.py` owns the aggregate-root module/test inventory; `shared/control_plane/domain/events.py` owns the shared domain-event base type; `shared/control_plane/domain/services.py` owns the shared `ControlPlaneDomainService` contract; `shared/control_plane/domain_event_audit.py` owns the application-layer domain-event audit collection boundary; `shared/control_plane/domain/approval_resolution.py` owns the approval-resolution effect policy between ApprovalRequest and EvolutionProposal; `shared/control_plane/domain/artifact.py` owns artifact evidence creation policy; `shared/control_plane/domain/company_context.py` owns company-context creation/update policy and PII-safe audit summaries; `shared/control_plane/domain/agent_prompt_config.py` owns prompt-config update policy and PII-safe audit summaries; `shared/control_plane/domain/agent_role.py` owns AgentRole lifecycle and runnability policy; `shared/control_plane/domain/agent_wakeup_adapter.py` owns wakeup adapter configuration translation for runtime boundaries; `shared/control_plane/domain/metadata.py` owns JSON-friendly metadata/config value-object normalization; `shared/control_plane/domain/state_machine.py` owns shared lifecycle transition-table normalization; `shared/control_plane/domain/budget_amount.py` owns budget value objects; `shared/control_plane/domain/budget_policy.py` owns the BudgetPolicy aggregate, lifecycle, active-conflict predicate, and `BudgetPolicyConflictPolicy`; `shared/control_plane/domain/budget_usage.py` owns budget usage spend-recording policy; `shared/control_plane/domain/audit_event.py` owns append-only audit evidence validation and detail normalization; `shared/control_plane/domain/execution_links.py` owns execution-link consistency for artifact/decision evidence through `ExecutionLinkConsistencyPolicy`; `shared/control_plane/domain/evolution_proposal.py` owns EvolutionProposal rollout FSM and approval-gating policy; `shared/control_plane/domain/approval_request.py` owns ApprovalRequest lifecycle policy; `shared/control_plane/domain/goal.py` owns Goal lifecycle policy; `shared/control_plane/domain/work_item.py` owns WorkItem lifecycle policy; `shared/control_plane/domain/decision.py` owns Decision lifecycle policy.
- UoW: `ControlPlaneUnitOfWork` in `shared/control_plane/unit_of_work.py` spans one local command transaction at a time and supports explicit sequential transactions for compatibility paths that dispatch a follow-up handler after commit.
- Notable: per-aggregate `*_store.py` + `*_ports.py` + `*_use_cases.py` split landed in PR #121; legacy `repository.py` facade retired (per `backend-architecture-analysis.md` §H2 closed).

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/control_plane/README.md` defines the governance boundary, ubiquitous language, aggregate ownership, transaction rules, and context-map relationships; `module-boundaries.md` §2.1 links the local glossary | Per-context glossary now lives beside the runtime |
| 2 | Aggregate root explicit | ✓ | `shared/control_plane/domain/aggregate_catalog.py` defines `CONTROL_PLANE_AGGREGATES` as the domain-owned catalog for the 13 aggregate-root wrappers and their required unit tests; `shared/control_plane/tests/test_aggregate_catalog.py` validates the catalog's record names, module exports, immutability, and test paths; `tests/unit/test_architecture_boundaries.py::test_business_aggregates_have_unit_tests` derives the Control Plane aggregate/test guard from that catalog | Pydantic records remain the intentional transport/DB boundary shape; aggregate-root ownership is now explicit and guarded in the domain layer |
| 3 | Aggregate consistency boundary | ✓ | `approval_use_cases.resolve_approval()` mutates only `ApprovalRequest`; `ControlPlaneUnitOfWork.begin_next_transaction()` marks the compatibility route's post-commit proposal handler as a second local transaction; `evolution_proposal_use_cases.apply_approval_resolution_event_to_linked_proposal()` consumes `approval.granted` / `approval.rejected` events for eventual consistency | ApprovalRequest and EvolutionProposal no longer share one commit; immediate API behavior is preserved by invoking the proposal handler after the approval transaction commits |
| 4 | Value objects | ✓ | `domain/budget_amount.py` provides frozen `BudgetAmount` and `BudgetWarningThreshold`; budget policy use cases, `BudgetGuard`, and `BudgetUsage` validate/add/compare budget amounts through those value objects. `domain/metadata.py` provides immutable `ControlPlaneMetadata` for JSON-friendly metadata/config normalization and deterministic key summaries across CompanyContext, AgentPromptConfig, Artifact, AuditEvent detail, and AgentWakeupAdapterConfig. `domain/budget_usage.py` centralizes token-count and model/tool-id normalization. `domain/audit_event.py` centralizes audit actor/idempotency/detail normalization. `domain/agent_wakeup_adapter.py` provides frozen `AgentWakeupAdapterConfig` for adapter config, command, timeout, heartbeat, and allowlist interpretation | Value objects now cover money, metadata/config, audit identity, budget usage model/tool identifiers, and runtime adapter interpretation before persistence/use-case decisions |
| 5 | Entities (identity-based) | ✓ | `shared/core/identifiers.py` defines typed `NewType` identities; Control Plane ports/stores use `CompanyId`, `WorkItemId`, `GoalId`, `AgentRunId`, `DecisionId`, `ApprovalRequestId`, `ArtifactId`, `BudgetPolicyId`, `EvolutionProposalId`, and `AgentRoleId` on public persistence boundaries | External API payloads and Pydantic records still expose strings at the transport/DB boundary |
| 6 | Domain services | ✓ | `domain/services.py` defines `ControlPlaneDomainService`; `domain/approval_resolution.py` implements `ApprovalResolutionPolicy`; `domain/execution_links.py` implements `ExecutionLinkConsistencyPolicy`; `domain/budget_policy.py` implements `BudgetPolicyConflictPolicy`; approval, artifact, decision, and budget use cases call these named policies before persistence | Cross-aggregate Control Plane rules now have explicit domain-service homes and a shared contract |
| 7 | Domain events | ✓ | `domain/events.py` provides shared `ControlPlaneDomainEvent`; `domain_event_audit.py` collects aggregate-raised events into durable audit rows; `domain_event_outbox.py` maps domain-event audit rows into immutable integration events; `event_outbox_store.py`, `tables.py`, and migration `20260526_control_plane_event_outbox.py` stage those events in `control_plane_event_outbox`; Artifact, BudgetPolicy, BudgetUsage, CompanyContext, AgentPromptConfig, AgentRole, AgentRun, EvolutionProposal, ApprovalRequest, Goal, WorkItem, and Decision event dataclasses inherit it and expose `pull_events()` from aggregates | Aggregate-raised Control Plane events now have a durable outbox staging path; external dispatcher wiring remains a runtime delivery concern |
| 8 | State machine | ✓ | `domain/state_machine.py` provides immutable `ControlPlaneStateMachine`; `models.py:20-90` defines `GoalStatus`, `AgentRunStatus`, `WorkItemStatus`, `ApprovalStatus`, `DecisionStatus`, `EvolutionRolloutState` as StrEnum; `domain/agent_role.py`, `domain/agent_run.py`, `domain/approval_request.py`, `domain/budget_policy.py`, `domain/decision.py`, `domain/evolution_proposal.py`, `domain/goal.py`, and `domain/work_item.py` define transition tables, terminal states, and typed illegal-transition errors through that shared state-machine value object | Lifecycle status families now share one domain-owned transition contract |
| 9 | Repository pattern | ✓ | `shared/control_plane/*_store.py` return domain records via `shared/control_plane/domain_records.py` mappers (e.g. `approval_store.py:9,33`); private `_*_row()` helpers stay internal | Ports return domain models; ORM `*Table` types do not escape |
| 10 | Application service purity | ✓ | `*_use_cases.py` import only models, ports, `shared.schemas.event`; `budget_use_cases.py:61-99` delegates to store ports; no SQLAlchemy or SDK imports | Use cases are pure |
| 11 | ACL for external systems | ✓ | `shared/control_plane/README.md` documents the Control Plane relationships to runtime agents, LLM gateway/providers, and EventBus. `domain/agent_wakeup_adapter.py` translates persisted adapter fields before HTTP/local-process execution; `BudgetGuard` and `BudgetAmount` translate LLM budget usage into Control Plane budget vocabulary before usage evidence is persisted; EventBus-facing integrations publish Control Plane vocabulary rather than transport envelopes | Keep future external integrations behind named Control Plane value objects or ports before they reach use cases |
| 12 | Context-map relationship | ✓ | `module-boundaries.md` §2.1 classifies Control Plane as an Open-Host Service with Published Language records and root-authority ownership | Keep new outbound integrations reflected in the context-map row |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗ (out of 12). Control Plane now keeps the central ledger while preserving aggregate consistency: ApprovalRequest resolution commits first, and linked EvolutionProposal synchronization runs through a named proposal-side handler in a follow-up transaction/event path.

### 4.2 Requirement Management

- Runtime owner: `agents/requirement_manager/`
- Aggregate landed: `Requirement` (Stage 2 PR #139).
- `core/domain/` contents: `requirement.py`, `aggregate_consistency.py`, `meeting_source.py`, `prd_document.py`, `extraction_materialization.py`, `feedback_learning.py`, `lifecycle/` subdir.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `module-boundaries.md` §2.2 names the context; `agents/requirement_manager/README.md` documents owned tables, aggregate root, UoW, and ubiquitous language for `Meeting`, `Requirement`, `OpenQuestion`, `FeedbackRecord`, and `PRD` | Runtime-local context description and glossary are explicit |
| 2 | Aggregate root explicit | ✓ | `agents/requirement_manager/core/domain/requirement.py:52-101` `Requirement` aggregate with `transition_to()`, `pull_events()`, `InvalidRequirementTransitionError` | Clear aggregate; raises typed transition error |
| 3 | Aggregate consistency boundary | ✓ | `core/domain/aggregate_consistency.py` defines `RequirementAggregateConsistencyPolicy` and `RequirementTransactionScope` for the allowed immediate-consistency write scopes; `meeting_ingest_workflow.py` asserts the meeting-ingest write set (`Meeting`, derived `Requirement`/`OpenQuestion`, outbox) before UoW writes; `requirement_mutation_workflow.py` asserts lifecycle/question scopes including optional `FeedbackRecord` evidence and outbox staging | Cross-aggregate writes are explicit named exceptions; vector indexing and notifications remain post-commit side effects |
| 4 | Value objects | ✓ | `RequirementStatusChanged` is frozen dataclass; `shared/core/identifiers.py` defines `RequirementId`, `MeetingId`, `OpenQuestionId`, and `FeedbackRecordId`; command/mutation/read/use-case/store boundaries convert external strings before entering internal workflows and stores; `MeetingSourceMetadata` owns immutable meeting source metadata; `PRDDocumentDraft` and `PRDRequirementSnapshot` own PRD composition metadata and fallback ordering; `ExtractedRequirementDraft`, `ExtractedOpenQuestionDraft`, and `RequirementExtractionPlan` own extraction materialization data; `RequirementExtractionSnapshot` and `RequirementFeedbackDraft` are immutable feedback-learning value objects | Core identity, meeting-source, PRD-composition, extraction-materialization, and feedback-learning value objects are explicit |
| 5 | Entities (identity-based) | ✓ | `requirement_ports.py` and `db/requirement_store.py` use `RequirementId` on get/update/confirm/reject/delete boundaries; `meeting_ports.py` and `db/meeting_store.py` use `MeetingId` on get/mark-processed boundaries; `question_ports.py` and `db/question_store.py` use `OpenQuestionId` on answer boundaries; `feedback_ports.py`, `db/feedback_store.py`, and `db/repository.py` use `FeedbackRecordId` for feedback lookup/mark-used boundaries and `RequirementId` for feedback-by-requirement lookup; `requirement_mutation_workflow.py` accepts typed identities for lifecycle/question mutations | External API payloads and ORM/Pydantic rows intentionally expose strings at the transport/database boundary |
| 6 | Domain services | ✓ | `core/domain/feedback_learning.py` owns correction/rejection classification, immutable extraction snapshots, feedback drafts, rejection placeholder, and changed-field calculation; `core/domain/extraction_materialization.py` owns extractor-result traversal, requirement draft creation, source-meeting association, first-requirement open-question assignment, persisted extraction publication, `requirement.extracted` payload shape, and search-index document construction; `agents/requirement_manager/README.md` carries the per-context domain-service catalogue | Application services now map domain drafts/projections to stores, outbox, and vector-index ports without owning those publication rules |
| 7 | Domain events | ✓ | `requirement.py:41-48` `RequirementStatusChanged` frozen domain event; `pull_events()` drained by use case for outbox | Events raised by aggregate, collected by UoW, staged in outbox |
| 8 | State machine | ✓ | `core/domain/lifecycle/requirement_states.py:31-36` `VALID_TRANSITIONS` dict; `requirement.py:75-77` validates before transition | Explicit FSM with transition table; typed transition error |
| 9 | Repository pattern | ✓ | `agents/requirement_manager/core/unit_of_work_ports.py:22-30` `RequirementUnitOfWork` Protocol; `requirement_ports.py` defines `RequirementStore` | Port + adapter clean |
| 10 | Application service purity | ✓ | `request_use_cases.py:1-110` no ORM, no SQL, no HTTP client imports; only `domain.transition_to()` and UoW orchestration | Pure |
| 11 | ACL for external systems | ✓ | `app/main.py` binds `FeishuRequirementCardRenderer` through `agents/requirement_manager/adapters/feishu_cards.py`; Feishu bot/event/card handlers import requirement card builders through `agents/requirement_manager/integrations/feishu/cards/requirement.py`; both local shims delegate to the reusable shared Feishu card implementation; `integrations/feishu/acl.py` translates meeting-ended, calendar, bot-message, and card-action Feishu payload trees into local immutable event/message/action objects before handlers call Requirement ingest, mutation APIs, PJM approval APIs, or card renderers; the same ACL module owns `FeishuCardActionResponse` for callback toast/card output payloads; `integrations/feishu/router.py` isolates the shared Feishu webhook router behind a Requirement-local adapter; `core/llm_extraction_response.py` translates raw LLM Gateway extraction JSON, Markdown fences, category labels, priority labels, and malformed list items into local immutable response objects before `core/extractor.py` maps them to extractor DTOs | External Feishu and LLM response shapes now cross local ACL/value-object seams before application workflows consume them |
| 12 | Context-map relationship | ✓ | `agents/requirement_manager/README.md` classifies upstream Anti-Corruption Layer to Interaction Gateway and Feishu, downstream Customer/Supplier to PJM Agent for `requirement.*`, and Conformist relationship to Control Plane; `module-boundaries.md` §2.2 carries the same classifications | Explicit Brandolini relationship types documented locally and in the catalog |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Stage 2 strong; current branch closes the core `RequirementId` persistence/mutation boundary, the `MeetingId` persistence/read boundary, the `OpenQuestionId` answer-question boundary, the `FeedbackRecordId` feedback-store boundary, the Requirement Manager aggregate-consistency policy, feedback-learning, extraction-materialization, and extraction-publication domain services, the runtime-local context-map documentation guard, the local Feishu-card, Feishu-event, Feishu bot-message, Feishu card-action, Feishu card-response, Feishu router, and LLM extraction-response ACL seams, meeting-source metadata, and PRD composition value objects.

### 4.3 Planning / PJM

- Runtime owner: `agents/pjm_agent/`
- Aggregate landed: `Decomposition` (Stage 2 PR #137).
- `core/domain/` contents: `decomposition.py`, `lifecycle/` subdir.
- UoW: `agents/pjm_agent/core/decomposition_ports.py` defines an explicit
  decomposition transaction boundary (P2-6 partial closure).

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `agents/pjm_agent/README.md` defines the runtime owner, owned tables, aggregate root, state machine, UoW, and local vocabulary; `module-boundaries.md` §2.3 names the context | Context and vocabulary documented |
| 2 | Aggregate root explicit | ✓ | `agents/pjm_agent/core/domain/decomposition.py:58-108` `Decomposition` aggregate with typed `WorkPackageId` identity, `transition_to()`, `pull_events()` | Clear aggregate root |
| 3 | Aggregate consistency boundary | ✓ | `decomposition.py:72-98` single transition per call; `decomposition_policy.py` owns the one-meaningful-decomposition-per-`WorkPackageId` intake/retry rule; `agents/pjm_agent/README.md` documents the consistency rule | Cross-record mutation guard documented and enforced through the domain policy before request/recovery workflows delete or retry records |
| 4 | Value objects | ✓ | `shared/core/identifiers.py` exposes `WorkPackageId` and `OpenProjectProjectId`; `core/domain/lifecycle/decomposition_lifecycle.py` defines typed `DecompositionStatus`; `core/domain/decomposition_values.py` defines immutable `DecompositionRejectionReason`; `DecompositionStatusChanged` is frozen and typed | Core PJM decomposition identifiers, status, and rejection reason have value-object coverage |
| 5 | Entities (identity-based) | ✓ | `decomposition.py`, `decomposition_ports.py`, `decomposition_request_workflow.py`, `decomposition_approval_workflow.py`, and `decomposition_recovery_workflow.py` type the aggregate/request/approve/recover/persistence identity as `WorkPackageId`; `DecompositionOrchestrator` converts external `int` IDs before workflow calls | Work-package identity is typed internally while public API/event payloads preserve the OpenProject integer contract |
| 6 | Domain services | ✓ | `core/domain/decomposition_policy.py` `DecompositionWorkflowPolicy` owns intake and retry status decisions; request and recovery workflows call it before skip/replace/retry behavior | Cross-decomposition status rules extracted from application workflows |
| 7 | Domain events | ✓ | `decomposition.py:48-54` `DecompositionStatusChanged` raised by aggregate, drained by caller | Pattern correct |
| 8 | State machine | ✓ | `core/domain/lifecycle/decomposition_lifecycle.py:45-52` `VALID_TRANSITIONS`; `decomposition.py:85-90` enforces; raises `InvalidDecompositionTransitionError` | Typed FSM |
| 9 | Repository pattern | ✓ | `decomposition_ports.py:23-49` `PJMDecompositionTransaction` Protocol; `db/` adapters separate | Port-based |
| 10 | Application service purity | ✓ | `request_use_cases.py:1-40` no DB / SQL / HTTP | Pure |
| 11 | ACL for external systems | ✓ | `adapters/feishu_card_acl.py` defines local immutable Feishu card translation objects for decomposition approval and task refinement and wraps the shared `FeishuPJMCardRenderer`; `service/agent.py` injects `PJMFeishuCardACL(FeishuPJMCardRenderer())` behind `PJMCardRendererPort` | Agent-local Feishu card ACL present; concrete Feishu card schema builders remain shared |
| 12 | Context-map relationship | ✓ | `agents/pjm_agent/README.md` classifies upstream Requirement Manager / Coordinator Customer-Supplier relationships, downstream Dev / QA / Sync Customer-Supplier relationships, OpenProject ACL via Sync, and Control Plane Conformist relationship; `module-boundaries.md` §2.3 carries the catalog entry | Explicit Brandolini relationship types documented locally and in the catalog |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. PJM now has a complete Stage 2 scorecard: typed decomposition identifiers/status/reason value objects, documented context map and consistency rule, aggregate/state-machine enforcement, explicit transaction ports, local Feishu card ACL, and cross-decomposition intake/retry domain policy.

### 4.4 Delivery / Dev

- Runtime owner: `agents/dev_agent/`
- Aggregate root: `Task`.
- `core/domain/` contents: `task.py`, `task_values.py`,
  `delivery_policy.py`, `lifecycle/` subdir.
- UoW: `agents/dev_agent/core/unit_of_work_ports.py` explicit.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `agents/dev_agent/README.md:10-52` defines runtime owner, owned tables, aggregate root, value objects, domain policy, local vocabulary, and context-map relationships; `module-boundaries.md` §2.4 names the context | Context and vocabulary documented |
| 2 | Aggregate root explicit | ✓ | `agents/dev_agent/core/domain/task.py:64-120` `Task` aggregate with typed `DevTaskId`, `TaskStatus`, `transition_to()`, `pull_events()`, `is_active()`, `is_in_progress()` | Clear aggregate root |
| 3 | Aggregate consistency boundary | ✓ | `agents/dev_agent/README.md:38-43` documents one `Task` per `WorkPackageId`, WorkflowLog-as-task-history, and domain policy decisions; `db/repository.py:22-37` enforces one row per `wp_id` with `on_conflict_do_nothing`; `core/repositories.py:86-97` exposes WorkflowLog through the task identity | WorkflowLog boundary is documented as task-owned history, not a separate aggregate |
| 4 | Value objects | ✓ | `shared/core/identifiers.py` exposes `DevTaskId` and `WorkPackageId`; `core/domain/lifecycle/task_lifecycle.py:11-38` defines typed `TaskStatus`; `core/domain/task_values.py:8-23` defines domain `RiskLevel`; `TaskStatusChanged` is frozen and typed | Dev task identity, work-package reference, lifecycle status, and risk level have value-object coverage |
| 5 | Entities (identity-based) | ✓ | `task.py:64-74` normalizes aggregate identity as `DevTaskId`; `core/repositories.py:13-58` types task and work-package identities on records and ports; `workflow_execution_use_cases.py:163-181` converts external sanitized task input to `WorkPackageId` / `DevTaskId` before persistence/logging | Internal Dev task identity is typed while public API/event payloads preserve primitive strings/ints |
| 6 | Domain services | ✓ | `core/domain/delivery_policy.py:33-73` `DevDeliveryWorkflowPolicy` owns CRITICAL automatic-delivery rejection, HIGH approval requirement, capacity decisions, and QA retry; `event_use_cases.py:82-91`, `workflow_execution_use_cases.py:152-188`, and `result_collector.py` consume the policy | Workflow/security/risk tools remain operational helpers behind domain policy decisions |
| 7 | Domain events | ✓ | `task.py:46-52` `TaskStatusChanged` raised by aggregate; `pull_events()` drained by use case | Pattern correct |
| 8 | State machine | ✓ | `core/domain/lifecycle/task_lifecycle.py:26-38` `VALID_TRANSITIONS` (12 states: PENDING, PLANNING, AWAITING_APPROVAL, EXECUTING, …); `task.py:81-104` enforces; raises `InvalidTaskTransitionError` | Most comprehensive FSM in the codebase |
| 9 | Repository pattern | ✓ | `agents/dev_agent/core/repositories.py:25-50` `DevTaskRepositoryPort`; `db/` adapters separate | Port-based |
| 10 | Application service purity | ✓ | `request_use_cases.py`, `workflow_execution_use_cases.py` no SQL / ORM / SDK leaks | Pure |
| 11 | ACL for external systems | ✓ | `adapters/gitlab_client.py:20-50` wraps GitLab API; `adapters/agentforge_client.py` wraps AgentForge SDK; translates external models → domain types | Best-in-class agent-local ACL |
| 12 | Context-map relationship | ✓ | `agents/dev_agent/README.md:45-52` classifies upstream PJM/QA Customer-Supplier relationships, downstream Channel Gateway Customer-Supplier relationship, GitLab/AgentForge ACLs, and Control Plane Conformist relationship; `module-boundaries.md` §2.4 carries the catalog entry | Explicit Brandolini relationship types documented locally and in the catalog |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Dev now has the runtime-local context map, typed identifiers/status/risk values, explicit aggregate consistency boundary, and domain workflow policy.

### 4.5 Quality / QA

- Runtime owner: `agents/qa_agent/`
- Aggregate root: `AcceptanceRun`.
- `core/domain/` contents: `acceptance_run.py`,
  `acceptance_verdict.py`, `acceptance_vocabulary.py`.
- UoW: `agents/qa_agent/core/unit_of_work_ports.py` explicit.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `agents/qa_agent/README.md:10-75` defines runtime owner, owned tables, aggregate root, value objects, ACL, local vocabulary, domain model, and context-map relationships | Vocabulary (`run`, `verdict`, `gate`, L0/L1/L2) is defined in the README and `acceptance_vocabulary.py` |
| 2 | Aggregate root explicit | ✓ | `agents/qa_agent/core/domain/acceptance_run.py` defines `AcceptanceRun` with lifecycle transitions, completion invariants, and an event buffer; `AcceptanceVerdict` remains the immutable verdict value object | Run completion now has an aggregate envelope |
| 3 | Aggregate consistency boundary | ✓ | `acceptance_execution_use_cases.py` generates the `AcceptanceRunId`, completes the aggregate, drains `AcceptanceRunCompleted`, then persists the same run id and stages outbox events in one QA UoW | DB persistence now follows aggregate/event construction instead of reconstructing the completed aggregate after the row write |
| 4 | Value objects | ✓ | `agents/qa_agent/core/domain/acceptance_verdict.py` `AcceptanceVerdict` frozen dataclass with `__post_init__` validation, `from_summary()`, `is_blocking`, and `is_clean` properties | Explicitly immutable, equality-by-value VO; gate/tier/finding vocabulary lives in `acceptance_vocabulary.py` |
| 5 | Entities (identity-based) | ✓ | `shared/core/identifiers.py` defines `AcceptanceRunId`; QA run-store ports/adapters, run-query use cases, API/request ports, service facade, and outbox publisher use that typed identity internally | External API payloads still expose `run_id` as a string, as intended |
| 6 | Domain services | ✓ | `acceptance_runner.py:24-50` runs acceptance framework; `AcceptanceVerdict.from_summary()` computes verdict from L0/L1/L2 status; acceptance execution and notification code ask the domain object/helpers for gate/finding classification; downstream Dev, QA API mapping, and QA stats queries consume QA verdicts through `shared/core/qa_acceptance.py` Published Language helpers/constants instead of duplicating raw string rules | Limited but isolated |
| 7 | Domain events | ✓ | `AcceptanceRunCompleted` is raised by the aggregate lifecycle and drained by `build_acceptance_events_from_run()` before staging `qa.acceptance-completed` / `qa.gate-failed` | Aggregate-raised event pattern present for completed runs |
| 8 | State machine | ✓ | `AcceptanceRunStatus` models requested → running → completed; `AcceptanceRun.start()` and `AcceptanceRun.record_completion()` reject invalid transitions while validating identity, target, counters, and duration | In-flight states are currently transient because the synchronous runner persists the completed projection only |
| 9 | Repository pattern | ✓ | `run_store.py`, `report_store.py`, `unit_of_work_ports.py` separate persistence; transaction boundary explicit | Port-based |
| 10 | Application service purity | ✓ | `api_use_cases.py`, `event_use_cases.py`, `acceptance_execution_use_cases.py` no direct ORM / SQL; `acceptance_runner.py` calls external subprocess | Pure (subprocess call wrapped) |
| 11 | ACL for external systems | ✓ | `adapters/acceptance_request_acl.py` translates `code.committed` / `qa.run-requested` payloads into QA-local `QAAcceptanceRequestEnvelope`, `QARunRequest`, immutable `GitLabMergeRequestContext`, and optional `OpenProjectWorkPackageContext`; `core/event_use_cases.py` consumes `QAAcceptanceRequestTranslatorPort` instead of parsing shared event payload classes; `service/agent.py` injects `QAAcceptanceRequestACL` | Inbound source-system data is translated at the QA adapter boundary before verdict inputs are built |
| 12 | Context-map relationship | ✓ | `README.md` events table classifies consume/publish per event | Strongest context-map evidence in the codebase |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Strong on documentation, identity typing, value objects, lifecycle aggregate modeling, inbound acceptance-request ACL, and UoW-ordered aggregate/event persistence. Durable in-flight requested/running projections are deferred until QA grows asynchronous long-running execution.

### 4.6 Sync — OpenProject Sub-Boundary

- Runtime owner: `shared/capabilities/sync/`
- Sub-boundary code: `shared/capabilities/sync/core/openproject/engine.py`
- `core/domain/` contents: `sync_operation.py`, `sync_values.py`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/capabilities/sync/README.md:10-45` defines runtime owner, owned tables, two sub-boundaries, aggregate root, value objects, FSM, UoW ports, ubiquitous language, and context-map relationships | Sync-side terms and relationships documented |
| 2 | Aggregate root explicit | ✓ | `core/domain/sync_operation.py` defines `SyncOperation` aggregate with `SyncSide.OPENPROJECT`, typed status, `transition_to()`, processed-count tally, and domain-event buffer; `core/openproject/engine.py` instantiates it for each OP-side run | Operation aggregate explicit |
| 3 | Aggregate consistency boundary | ✓ | `core/openproject/engine.py` wraps each OP-side run in `OpenProjectSyncStore.transaction()`, creates a `SyncOperation`, completes the log before publishing staged outbox events, and asks `SyncProjectionPolicy.decide_work_package_projection()` before creating/updating Feishu rows or mappings | Operation/log consistency, mapping identity, and per-work-package mapping conflict checks now live behind the Sync domain policy |
| 4 | Value objects | ✓ | `core/domain/sync_values.py:25-47` defines immutable `WorkPackageData` with typed `WorkPackageId` / `OpenProjectProjectId`, title/progress validation, and equality-by-value semantics; `mapper.py` returns it before Feishu field mapping | OpenProject projection value object present |
| 5 | Entities (identity-based) | ✓ | `SyncMappingRecord` wraps persisted `sync_agent_mappings` rows with `SyncMappingId`, `WorkPackageId`, `FeishuRecordId`, and optional `OpenProjectProjectId`; `OpenProjectSyncOperation.get_mapping_by_op_id()` returns the typed record | Mapping identity is promoted before the row leaves the adapter |
| 6 | Domain services | ✓ | `mapper.py` translates OP payloads into `WorkPackageData` and Feishu fields; `core/domain/sync_operation.py` owns status-combining policy through `combine_side_statuses()`; `locking.py` owns advisory lock boundary | Domain services/helpers isolated |
| 7 | Domain events | ✓ | `core/openproject/engine.py` stages handoff events through `OpenProjectSyncOperation.stage_event()` before publishing; `event_use_cases.py` collects and forwards lifecycle events | Pattern present; events flow through outbox with `trace_id` |
| 8 | State machine | ✓ | `core/domain/sync_operation.py` defines `SyncOperationStatus` and `VALID_TRANSITIONS`; `core/engine.py:117-130` coerces legacy sub-engine result strings into the enum and combines with `combine_side_statuses()` | Typed operation FSM present |
| 9 | Repository pattern | ✓ | `core/sync_ports.py` defines split `OpenProjectSyncStore` / `FeishuBitableSyncStore`; `db/sync_stores.py` returns `SyncMappingRecord` and `SubtaskMappingRecord` from adapters without core importing repositories | Port return shapes are typed domain records for sync log/mapping records |
| 10 | Application service purity | ✓ | `core/openproject/engine.py` uses injected `BitableTablePort`, `OpenProjectWorkPackagePort`; no direct SDK calls | Pure; infrastructure delegated via ports |
| 11 | ACL for external systems | ✓ | `mapper.py` translates OP `work_package` → Feishu fields; `feishu_bitable_sync.py` orchestrates data flow | Bidirectional translation isolated to mapper |
| 12 | Context-map relationship | ✓ | `README.md:38-45` classifies PJM Customer/Supplier, OP/Feishu ACL, internal Partnership, and Control Plane Conformist relationships | Formal context map present |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. OpenProject-side Sync now has a documented context map, operation aggregate/FSM, immutable work-package value object, typed mapping identity, typed persistence ports, and domain-owned per-work-package mapping conflict decisions.

### 4.7 Sync — Feishu Bitable Sub-Boundary

- Runtime owner: `shared/capabilities/sync/`
- Sub-boundary code: `shared/capabilities/sync/core/feishu_bitable/engine.py`
- `core/domain/` contents: `sync_operation.py`, `sync_values.py`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/capabilities/sync/README.md:10-45` defines the Feishu Bitable side, local vocabulary for Feishu record data/subtask status/progress back-flow, and relationship classifications | Feishu-side vocabulary documented |
| 2 | Aggregate root explicit | ✓ | `core/domain/sync_operation.py` defines `SyncOperation` aggregate with `SyncSide.FEISHU_BITABLE`, typed status, `transition_to()`, processed-count tally, and domain-event buffer; `core/feishu_bitable/engine.py` instantiates it for each Bitable-side run | Operation aggregate explicit |
| 3 | Aggregate consistency boundary | ✓ | `core/feishu_bitable/engine.py` wraps each Bitable-side run in `FeishuBitableSyncStore.transaction()`, creates a `SyncOperation`, completes the log after parent progress updates, persists subtasks through `SubtaskMappingRecord` normalization, and asks `SyncProjectionPolicy` for parent/subtask rollups | Operation/log consistency, mapping identity, and parent progress rollup rules now live behind the Sync domain policy |
| 4 | Value objects | ✓ | `core/domain/sync_values.py:49-86` defines immutable `FeishuRecordData`, typed `FeishuRecordId`, typed `FeishuSubtaskStatus`, and completion-status helper; `mapper.py` returns those values before progress calculation | Status and record projection value objects present |
| 5 | Entities (identity-based) | ✓ | `SubtaskMappingRecord` wraps persisted `sync_agent_subtask_mappings` rows with `SyncSubtaskMappingId`, `WorkPackageId`, `FeishuRecordId`, and typed `FeishuSubtaskStatus` | Subtask mapping identity is promoted before the row leaves the adapter |
| 6 | Domain services | ✓ | `shared/capabilities/sync/core/progress.py` `calculate_progress_from_subtasks` encodes percentage-done logic | Pure domain logic isolated |
| 7 | Domain events | ✓ | `SyncOperationStatusChanged` is raised by the aggregate; `core/feishu_bitable/engine.py` stages `sync.progress-updated` after successful OpenProject parent progress writes and publishes after the local transaction | Aggregate and Feishu progress-update integration events both flow through outbox-backed boundaries |
| 8 | State machine | ✓ | `core/domain/sync_operation.py` defines the operation FSM; `core/domain/sync_values.py` types Feishu subtask status and `progress.py` classifies completion via `is_completed_subtask_status()` | Operation status and subtask-status classification typed |
| 9 | Repository pattern | ✓ | `core/sync_ports.py` defines `FeishuBitableSyncOperation.upsert_subtask(...) -> SubtaskMappingRecord`; `db/sync_stores.py` converts status at the adapter boundary and returns the typed record | Status and identity value objects reach the port boundary |
| 10 | Application service purity | ✓ | `core/feishu_bitable/engine.py` uses `BitableTablePort`, `OpenProjectWorkPackagePort` only | Pure use case |
| 11 | ACL for external systems | ✓ | `mapper.feishu_to_record_data` extracts Feishu records into immutable `FeishuRecordData`; `progress.py` maps `FeishuSubtaskStatus` completion to OP `percentageDone`; README publishes this relationship | Published translation contract present |
| 12 | Context-map relationship | ✓ | `README.md:38-45` classifies PJM Customer/Supplier, OP/Feishu ACL, internal Partnership, and Control Plane Conformist relationships | Formal context map present |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Feishu-side Sync now has a documented context map, operation aggregate/FSM, immutable record/status value objects, typed persisted mapping identity, typed status port, parent/subtask rollup policy, and outbox-backed progress-update integration events.

### 4.8 Interaction Gateway

- Runtime owner: `services/gateways/user_interaction/`
- Gateway code shape: webhook intake/processing, Feishu card transport
  ports, HTTP API proxies, and the `ChatAgentClient` adapter.
- No `core/domain/` directory. Gateways own gateway concerns, not
  product-domain records; dimensions 2, 3, 5, 6, 7, 8, and 9 are `n/a`
  after DDD-016 because the gateway no longer owns chat-agent records.

**Boundary status**: User Interaction historically owned
`chat_agent_conversation_histories`, `chat_agent_card_operations`, and
`chat_agent_daily_progress` through gateway-local models. ADR-0010
Steps 2-7 moved the canonical table metadata, repositories, adapters,
ports, chat use cases, runtime service composition, scheduler, outbox
dispatching, and internal HTTP APIs into `agents/chat_agent/`. The
gateway-local chat-agent `core/`, `db/`, and `models/` compatibility
aliases have been removed. Production gateway code calls chat-agent only
through `services/gateways/user_interaction/adapters/chat_agent_client.py`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `services/gateways/user_interaction/README.md` defines inbound user-interaction gateway and chat-agent HTTP boundary | Gateway concerns clear; product records live in chat-agent |
| 2 | Aggregate root explicit | n/a | Gateway owns no product aggregates | Chat aggregates are tracked under `agents/chat_agent/` |
| 3 | Aggregate consistency boundary | n/a | Gateway owns no product aggregates | Chat-agent owns product consistency |
| 4 | Value objects | ✓ | `services/gateways/user_interaction/core/webhook_intake.py` `FeishuWebhookMessage` is a frozen slotted value object that translates Feishu webhook bodies into immutable local fields and owns text/mention normalization through `text_content()` | Gateway transport values are immutable and normalize external Feishu shape before the API handler calls chat-agent |
| 5 | Entities (identity-based) | n/a | Gateway owns no product entities | Product entities live in chat-agent |
| 6 | Domain services | n/a | Gateway owns no product domain services | Chat/domain use cases live in chat-agent |
| 7 | Domain events | n/a | Gateway owns no product event outbox for chat-agent state | `chat_agent_event_outbox` lives in chat-agent |
| 8 | State machine | n/a | Gateway owns no product state machine | Card/daily-progress states are chat-agent concerns |
| 9 | Repository pattern | n/a | Gateway owns no chat-agent repositories | Repositories live in `agents/chat_agent/db/` |
| 10 | Application service purity | ✓ | Gateway production code calls `ChatAgentClient`; chat service/application facade live in `agents/chat_agent/core/` | HTTP boundary replaces in-process imports |
| 11 | ACL for external systems | ✓ | `core/webhook_intake.py` / `core/webhook_processing.py` normalize Feishu traffic; `adapters/chat_agent_client.py` is the downstream ACL to chat-agent | ACL placement explicit |
| 12 | Context-map relationship | ✓ | `module-boundaries.md` §2.7 classifies Interaction Gateway as ACL to external users and conformist to chat-agent payloads | Relationship documented |

**Summary**: 5 ✓ / 0 ⚠ / 0 ✗ / 7 n/a. ADR-0010 is closed for the
gateway code boundary. Remaining chat-domain tactical DDD work belongs
inside `agents/chat_agent/`, not in the gateway.

### 4.9 Channel Gateway

- Runtime owner: `services/gateways/channel/`
- Application facade landed: `core/application_facade.py` (recent commit
  `50cde3f52 refactor(channel-gateway): extract application facade`).
- No `core/domain/` directory because gateways own no product aggregates.
  Gateway infrastructure state is guarded by `core/outbox_lifecycle.py`.

Gateway-specific grading: dimensions 2–6 default to `n/a` for gateways (they own no product-domain records). The audit confirms Channel Gateway does NOT own product tables (unlike User Interaction). Outbox `channel_gateway_event_outbox` is gateway infrastructure, not a product record.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `services/gateways/README.md` "Multi-channel gateway for `channel.message.outbound` delivery through registered adapters" | Gateway concern clear; channel routing isolated |
| 2 | Aggregate root explicit | n/a | Gateway owns no product-domain records | — |
| 3 | Aggregate consistency boundary | n/a | — | — |
| 4 | Value objects | n/a | — | — |
| 5 | Entities (identity-based) | n/a | `ChannelGatewayEventOutbox` is infrastructure entity | — |
| 6 | Domain services | n/a | — | — |
| 7 | Domain events | ✓ | `core/event_use_cases.py` emits `delivery_succeeded`, `delivery_failed`; `outbox_delivery_use_cases.py` publishes | Events typed; outbox transactional |
| 8 | State machine | ✓ | `core/outbox_lifecycle.py` `ChannelGatewayOutboxLifecycle` guards pending retry, pending publish, and terminal published rows; `db/repository.py` uses it before add/mark-published/mark-failed writes | Gateway infrastructure outbox transitions are guarded without promoting a product aggregate |
| 9 | Repository pattern | ✓ | `db/outbox_store.py` adapter; `outbox_ports.py:14` port; `db/repository.py` adapter | Clean separation |
| 10 | Application service purity | ✓ | `core/event_use_cases.py` depends only on adapter registry port; no SDK in use case | Pure |
| 11 | ACL for external systems | ✓ | `core/provider_acl.py` defines `ChannelProviderACL`, provider adapter/registry Protocols, and delivery request/response values; `core/event_use_cases.py` routes missing adapters and provider exceptions through the ACL before emitting `channel.message.delivered` | Provider failure translation is explicit and local to the gateway boundary |
| 12 | Context-map relationship | ✓ | `services/gateways/channel/README.md` and `module-boundaries.md` classify Open-Host Service for `channel.message.outbound`, Customer/Supplier producers, adapter ACLs, and Conformist relationship to shared outbound payloads | Relationship types documented locally and in the catalog |

**Summary**: 7 ✓ / 0 ⚠ / 0 ✗ / 5 n/a. Clean gateway boundary. Outbound provider ACL coverage is explicit through `ChannelProviderACL`; product aggregate work belongs in the producing runtimes, not this gateway.

### 4.10 Coordination / Orchestration

- Runtime owner: `services/orchestration/coordinator/`
- Application facade landed: `core/application_facade.py` (recent commit
  `a109d4320 refactor(coordinator): extract application facade`).
- Domain layer: `core/domain/dispatch.py` owns target routing and dispatch
  envelope selection; `core/domain/workflow_state.py` owns workflow lifecycle
  rules; `core/domain/scratchpad.py` owns scratchpad projection ordering.
  Coordinator also owns a port-backed scratchpad / state store. Scratchpad is
  treated as a derived reasoning projection after decision persistence, while
  agent-state and pending-decision read models hydrate through
  `core/domain/state_records.py`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `services/orchestration/coordinator/README.md` defines the Coordinator context, vocabulary, state store, scratchpad, thinker, and dispatch envelope | Context charter is local |
| 2 | Aggregate root explicit | ✓ | `core/domain/workflow_state.py` `CoordinatorWorkflowState` owns workflow lifecycle; `core/domain/dispatch.py` `CoordinatorDispatchPolicy` owns dispatch routing; `core/domain/scratchpad.py` owns scratchpad projection ordering | Workflow lifecycle, dispatch routing, and scratchpad projection have domain owners |
| 3 | Aggregate consistency boundary | ✓ | `CoordinatorEventUseCase` routes progress and decision persistence through `CoordinatorUnitOfWorkFactory` when wired; workflow-state upserts in both state-store adapters validate through `CoordinatorWorkflowState`; dispatch envelope consistency is guarded by `CoordinatorDispatchPolicy`; `CoordinatorScratchpadConsistencyPolicy` requires decisions to persist before the scratchpad projection is updated and compaction can run | Scratchpad is a derived projection after decision persistence; state-store/UoW remains the consistency source |
| 4 | Value objects | ✓ | `CoordinatorDispatchRoute`, `CoordinatorDispatchEnvelope`, `CoordinatorDispatchTarget`, `CoordinatorTargetRelationship`, `CoordinatorWorkflowStatus`, `CoordinatorAgentStatus`, `CoordinatorAgentId`, `CoordinatorDecisionId`, `CoordinatorWorkflowId`, and `CoordinatorTaskId` are typed domain values; `Decision` remains mutable Pydantic input at the thinker ACL boundary | Core dispatch/workflow/state identity values are typed; thinker DTO remains transport-facing |
| 5 | Entities (identity-based) | ✓ | `CoordinatorWorkflowState` has `workflow_id`; `CoordinatorAgentStateRecord` wraps agent-state rows with `CoordinatorAgentId`; `CoordinatorDecisionRecord` wraps pending decisions with `CoordinatorDecisionId`, `CoordinatorWorkflowId`, target `CoordinatorAgentId`, and optional `CoordinatorTaskId` | Workflow, agent-state, and pending-decision identities are promoted before rows leave adapters |
| 6 | Domain services | ✓ | `core/domain/dispatch.py` `CoordinatorDispatchPolicy.envelope_for()` centralizes target-specific event-contract selection | Dispatch target rules no longer live in the EventBus adapter |
| 7 | Domain events | ✓ | `CoordinatorWorkflowStatusChanged` is raised by the workflow aggregate; `core/event_use_cases.py` handles classified events; `outbox_delivery_use_cases.py` publishes via EventBus | Aggregate-local and integration-event patterns present |
| 8 | State machine | ✓ | `CoordinatorWorkflowStatus` guards `active -> paused/completed/failed` and `paused -> active/failed`, with completed/failed terminal; dispatch route classification is explicit | Workflow lifecycle now has transition guards |
| 9 | Repository pattern | ✓ | `db/outbox_store.py:10` `SqlAlchemyCoordinatorEventOutboxStore`; `db/state_store.py:13` `CoordinatorStateStore` (in-memory adapter); ports `outbox_ports.py:8`, `state_ports.py:6` | Port + adapter; ORM isolated |
| 10 | Application service purity | ✓ | `CoordinatorEventUseCase` depends on `CoordinatorThinkerPort`, state/scratchpad ports, UoW factory, and `decision_to_event()`; LLM SDK calls live in `core/think.py` behind the port | Use case is port-driven |
| 11 | ACL for external systems | ✓ | `CoordinatorThinkerPort` defines the LLM ACL; `core/think.py` wraps untrusted context and parses raw LLM output into typed `Decision` objects before returning | Raw LLM output does not cross the port |
| 12 | Context-map relationship | ✓ | `README.md` and `module-boundaries.md` classify upstream Open-Host Service, downstream Customer/Supplier, LLM ACL, and Control Plane Conformist relationships; dispatch target contracts live in `CoordinatorDispatchPolicy` | Relationship types are documented and backed by code |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Coordinator now has a workflow-state aggregate/FSM, dispatch-domain policy, scratchpad projection consistency policy, typed state-record identities, explicit target relationship value objects, LLM thinker ACL, and documented context-map relationships.

### 4.11 Analytics / Reporting

- Runtime owner: `shared/capabilities/analysis/`
- Domain layer: `core/domain/projection.py`, `core/domain/report.py`,
  `core/domain/report_log.py`, and `core/domain/feishu_task.py`.
- Current state: report and milestone reads use the Analysis-owned
  work-package/subtask projection. Feishu Bitable task reads are concentrated
  in the projection updater and translated into Analysis-owned snapshots before
  report generation or risk checks consume them.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `README.md` defines reports, generated reports, report stats, risk signals, quality verdicts, milestones, and projections | Bounded-context vocabulary is now local |
| 2 | Aggregate root explicit | ✓ | `core/domain/report.py` `GeneratedAnalysisReport` owns generated report content, summary, stats, status, and event buffer | Report-generation invariants are aggregate-owned |
| 3 | Aggregate consistency boundary | ✓ | Daily and weekly generators construct `GeneratedAnalysisReport` with immutable `AnalysisReportStats`; `core/report_delivery_use_cases.py` `AnalysisReportDeliveryUseCase` owns the generate → chat push → report-event payload command boundary | Report generation and delivery consistency is explicit at the application boundary |
| 4 | Value objects | ✓ | `AnalysisReportStats`, `TaskSourceStats`, `AnalysisReportKind`, `AnalysisReportStatus`, `AnalysisFeishuTaskSnapshot`, `AnalysisFeishuTaskStatus`, `MilestoneRiskSignal`, `AnalysisRiskSeverity`, `AnalysisRiskType`, `DeliverableQualityTask`, `QualityEvaluation`, `AnalysisQualityVerdict`, and `DeliverableQualityResult` model report content/status, source snapshots, risk signals, quality verdicts, prompt metadata, and Feishu write-back fields | Report, risk, quality, projection, and Feishu task value objects are present |
| 5 | Entities (identity-based) | ✓ | `core/domain/report_log.py` `AnalysisReportLogRecord` wraps persisted `analysis_agent_report_logs` rows with typed `AnalysisReportLogId`, kind, content, status, and timestamps | Report-log identity is promoted before rows leave the DB adapter |
| 6 | Domain services | ✓ | `MilestoneChecker.check()`, `QualityEvaluator.evaluate_all()` encapsulate domain logic | Risk and quality assessment logic isolated |
| 7 | Domain events | ✓ | `GeneratedAnalysisReport` raises `AnalysisReportGenerated`; `event_use_cases.py:86-155` stages `REPORT_DAILY_GENERATED`, `ANALYSIS_RISK_DETECTED`, `ANALYSIS_QUALITY_EVALUATED` | Aggregate-local and integration-event patterns present |
| 8 | State machine | ✓ | `AnalysisReportStatus` guards generated/pushed/failed transitions on `GeneratedAnalysisReport`; `AnalysisReportLogRecord.mark_pushed()` validates generated→pushed before repository writes | Domain status now gates both generated-report and persisted report-log paths |
| 9 | Repository pattern | ✓ | `ReportLogRepository.create()` and `get_latest()` return `AnalysisReportLogRecord`; SQLAlchemy `ReportLog` stays inside the adapter | ORM row no longer crosses the repository boundary |
| 10 | Application service purity | ✓ | Daily/weekly generators and `MilestoneChecker` read work-package and Feishu task data through `WorkPackageProjectionPort`; source-system reads stay in `ProjectionUpdater` and quality write-back stays behind `BitableTablePort` | Report and milestone use cases are projection-only; quality evaluation retains an explicit write-back port |
| 11 | ACL for external systems | ✓ | `core/domain/projection.py` provides the OP/SYNC published-language projection; `core/domain/feishu_task.py` `AnalysisFeishuTaskACL` translates projected Feishu task rows into `AnalysisFeishuTaskSnapshot` before daily/weekly report stats or formatting consume them | OP and Feishu task source records cross through Analysis-owned published-language objects |
| 12 | Context-map relationship | ✓ | `README.md` and `module-boundaries.md` classify Sync/PJM projection Customer/Supplier, reporting consumers, Feishu Bitable ACL, and Control Plane Conformist relationships | Relationship types are documented |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Analysis now has a generated-report aggregate, report-log domain record, typed report stats/status/kind vocabulary, Feishu task ACL snapshots, risk/quality assessment value objects, an explicit report-delivery command boundary, and report/milestone reads fully routed through the durable Analysis projection.

### 4.12 Evolution

- Runtime owner: `shared/capabilities/evolution/` (+ historical
  `shared/evolution/` split per `module-boundaries.md` §2.10).
- Local domain values: `shared/capabilities/evolution/core/domain/`.
  Control Plane remains the aggregate owner for durable
  `EvolutionProposal` records.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/capabilities/evolution/README.md` defines the bounded context, ubiquitous language for proposal/scope/tier/approval/rollout terms, and local ownership boundaries | Evolution terms now have a local glossary |
| 2 | Aggregate root explicit | ✓ | `shared/control_plane/domain/evolution_proposal.py` owns the durable `EvolutionProposal` aggregate; `shared/evolution/domain/experiment.py` owns the L1 mini-canary `EvolutionExperiment` aggregate for traffic routing, score summaries, minimum-sample checks, promotion thresholds, and rollback decisions; `canary_router.py` and `skill_optimizer.py` call the aggregate before repository writes | `EvolutionTrace` and `Reflection` remain evidence/analysis records until they grow non-trivial lifecycle invariants |
| 3 | Aggregate consistency boundary | ✓ | `proposal_approval_use_cases.py` validates approval context and writes one Control Plane proposal/audit path through injected stores | Approval gate guards rollout; audit trail maintained |
| 4 | Value objects | ✓ | `shared/capabilities/evolution/core/domain/proposal.py` defines frozen `EvolutionProposalScope`, `EvolutionProposalApprovalContext`, and `EvolutionProposalOperation`; approval use cases derive scope, evidence, risk, benefit, and metadata through those values | Proposal approval payload construction is immutable before primitive event/API serialization |
| 5 | Entities (identity-based) | ✓ | `EvolutionProposal` has `proposal_id`; `ApprovalGate` tracks `approval_id` | Identity-based entities with lifecycle |
| 6 | Domain services | ✓ | `ApprovalGate` (Control Plane), `skill_seed_store` (capability) encode workflow | Domain-specific logic isolated |
| 7 | Domain events | ✓ | `event_use_cases.py` collects and stages `AuditEvent`; outbox dispatches | Audit trail captured via events |
| 8 | State machine | ✓ | `shared/control_plane/domain/evolution_proposal.py` enforces rollout transitions through `EvolutionRolloutState`; `ApprovalStatus` remains the approval-state vocabulary | Typed state with explicit transition owner |
| 9 | Repository pattern | ✓ | `core/control_plane_ports.py` defines `EvolutionControlPlaneProposalStore`; implementations in `db/` hide ORM | Port-based; no ORM leak |
| 10 | Application service purity | ✓ | `proposal_approval_use_cases.py` accepts injected stores; no direct DB / SDK | Pure |
| 11 | ACL for external systems | ✓ | `analysis_ports.py`, `control_plane_ports.py` define external context contracts | Explicit ports for cross-context integration |
| 12 | Context-map relationship | ✓ | `README.md` and `module-boundaries.md` classify Control Plane Conformist/Customer-Supplier, `shared/evolution` Partnership, runtime-agent Open-Host Service/Published Language, LLM ACL, and human-review Open-Host Service relationships | Formal context map present locally and in the catalog |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Evolution now has a local bounded-context glossary, proposal scope/approval value objects, an operation whitelist in the domain layer, documented context-map relationships, the Control Plane-owned rollout aggregate, and a runtime `EvolutionExperiment` aggregate for mini-canary routing and rollout decisions. `EvolutionTrace` and `Reflection` remain evidence/analysis records until they grow non-trivial lifecycle invariants.

### 4.13 Identity / User

- Runtime owner: `shared/messaging/inbound/user_service.py`,
  `shared/db/user_store.py`.
- Foundation doc landed: [`identity-boundary.md`](./identity-boundary.md).
- Architecture-boundary test enforces port-based access:
  `tests/unit/test_architecture_boundaries.py::test_inbound_user_service_uses_identity_store_port`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/core/identity_ports.py:10-30` defines `UserIdentityStore` Protocol; `identity-boundary.md` is the contract doc | Boundary defined |
| 2 | Aggregate root explicit | ✓ | `shared/models/user.py` `User.create_identity()`, `link_platform_account()`, `record_activity()`, and `identity_state` make `User` the transition owner | Aggregate methods own identity invariants |
| 3 | Aggregate consistency boundary | ✓ | `User.link_platform_account()` rejects conflicting same-platform links; `User.record_activity()` requires a prior platform link | Platform-link/activity invariants no longer live in app-service field mutation |
| 4 | Value objects | ✓ | `shared/core/identity_domain.py` defines `PlatformUserRef`, `EmailAddress`, `PhoneNumber`, and `IdentityState` | Contact and platform identity primitives are normalized before persistence |
| 5 | Entities (identity-based) | ✓ | `User` has primary key id; mutable state (`last_active_at`); tracked by identity not value | Clear entity |
| 6 | Domain services | ✓ | `shared/core/identity_resolution.py` owns platform-directory lookup, email normalization, get/link/create/update flow, and aggregate-event collection through `UserIdentityStore` and `IdentityPlatformDirectoryPort`; `UserService` keeps cache/session/serialization concerns as the inbound shell | Identity-resolution application logic has a core boundary home |
| 7 | Domain events | ✓ | `UserCreated`, `PlatformLinked`, and `UserActivated` are raised in-memory, drained by `UserService`, mapped through `shared/core/identity_event_outbox.py`, and staged in `identity_event_outbox`; `docs/guides/event-catalog.md` documents the PII-safe `identity.*` payloads | Aggregate-raised identity events now have a durable outbox staging path |
| 8 | State machine | ✓ | `IdentityState` derives `unlinked` → `linked` → `active`; aggregate methods enforce link-before-activity | Explicit lifecycle vocabulary and transition guards |
| 9 | Repository pattern | ✓ | `UserRepository` implements port `UserIdentityStore`; per `identity-boundary.md` §2 single write path | Clean ACL boundary |
| 10 | Application service purity | ✓ | `shared/core/identity_resolution.py` owns platform-directory lookup, email normalization, get/link/create/update flow, and aggregate-event collection through `UserIdentityStore` and `IdentityPlatformDirectoryPort`; `UserService.resolve_user()` delegates to it and keeps cache/session/serialization as the shell boundary | Identity resolution application logic is port-driven and cache/session concerns remain outside the use case |
| 11 | ACL for external systems | ✓ | `UserService.resolve_user()` translates inbound platform identifiers into `PlatformUserRef`; `EmailAddress` / `PhoneNumber` normalize adapter contact values; OpenClaw remains translated but has no persisted lookup column yet | Platform primitives cross the boundary through local value objects |
| 12 | Context-map relationship | ✓ | `module-boundaries.md` §2.11 classifies platform identifiers as ACL and `UserIdentityStore` as the published language for downstream runtimes | Integrations and consumers have explicit relationship labels |

**Summary**: 12 ✓ / 0 ⚠ / 0 ✗. Identity now has aggregate-owned platform linking/activity transitions, contact/platform value objects, a core port-driven identity-resolution use case, and durable PII-safe integration-event staging. Remaining product work: public user/profile API ownership and downstream consumer activation.

### 4.14 Integration Plane (Adapter Library)

Integrations are not a bounded context. They are graded against the ACL
sub-rubric (§1.2 dimension 11 + the five ACL questions in the evidence
brief):

| Integration | Port file | Adapter file | ACL clean? | Leaks (file:line) |
|-------------|-----------|--------------|------------|-------------------|
| Feishu | `shared/core/integration_ports.py:102-134` (`FeishuMessengerPort`, `FeishuContactLookupPort`) | `shared/integrations/feishu/adapter.py:25` `FeishuChannelAdapter` | ✓ | Card builders imported into agents (`agents/qa_agent/adapters/feishu_cards.py`, `agents/pjm_agent/adapters/feishu_cards.py`) but wrapped in local renderer classes; `lark_oapi` SDK stays isolated in `client.py` |
| WeCom | `shared/core/integration_ports.py` (`WecomMessengerPort`) | `shared/integrations/wecom/adapter.py:21` `WecomChannelAdapter` | ✓ | Named messenger port exists; card-builder usage stays inside WeCom integration/adapter code |
| OpenProject | `shared/core/integration_ports.py` (`OpenProjectWorkPackagePort`) | `shared/integrations/openproject/client.py` `OpenProjectClient` | ✓ | Port returns `OpenProjectWorkPackage` TypedDict records; service shells may construct the concrete adapter, while core services consume the port |
| GitLab | `shared/core/integration_ports.py:150-177` `GitLabMergeRequestPort`, `GitLabMergeRequestNotePort` | (client only) | ✓ | httpx client used through port; external schema isolated |
| OpenClaw | `shared/core/integration_ports.py` (`OpenClawIntegrationPort`) | `shared/integrations/openclaw/adapter.py:23` `OpenClawChannelAdapter` | ✓ | Named port consumes `ChannelMessage` / `ChannelCard`; raw JSON-RPC params stay inside the adapter/client boundary |
| AgentForge | n/a | n/a | n/a | No `shared/integrations/agentforge/` module; AgentForge integration lives inside `dev_agent` adapters (audit follow-up) |

**Cross-cutting integration checks** (key questions A–E from §1.2 dimension 11):

- A. **Port-typed access**: Feishu, WeCom, OpenProject, GitLab, and OpenClaw now expose named Protocol boundaries in `shared/core/integration_ports.py`.
- B. **External-type leaks**: `OpenProjectWorkPackagePort` returns `OpenProjectWorkPackage` TypedDict records; OpenClaw raw JSON-RPC dictionaries stay inside the adapter/client boundary.
- C. **Auth/token caches**: handled in `client.py` constructors (e.g. `feishu/client.py`); not exposed to shared code (✓).
- D. **Port contract coverage**: `integration_ports.py` covers all declared shared integrations that have a shared adapter surface: Feishu, WeCom, OpenProject, GitLab, and OpenClaw.
- E. **Card builders**: Feishu/WeCom card builders stay in integration or agent-local adapter code; core services consume ports and domain-friendly channel/card types.

**Summary**: Integration Plane ACL coverage is aligned with DDD-013 and DDD-022: OpenProject has typed work-package records, WeCom has a named messenger port, OpenClaw has a named integration port, and adapter-specific SDK/JSON-RPC shapes stay behind integration adapters.

---

## 5. Cross-Cutting Findings

Patterns that appear across multiple contexts. These are the highest-
leverage opportunities because a single binding rule closes the pattern
everywhere at once.

### 5.1 Inconsistent `core/domain/` Adoption

This finding is closed for the tracked code-architecture scope.
Business agents, chat-agent, Sync, Analysis, and Control Plane now have
explicit domain packages or documented gateway exclusions. Gateways are
excluded because they do not own product-domain records.

Every product-owning runtime requires a domain package under
[Architecture Principles §1](./architecture-principles.md#1-layering-rules).
Gateway contexts remain transport/ACL boundaries and do not own product records.

### 5.2 Lifecycle Module Location Drift

Two legitimate locations exist today:
- `core/<aggregate>_lifecycle.py` (Dev agent: `task_lifecycle.py`).
- `core/domain/lifecycle/` (Requirement, PJM, Dev, Control Plane —
  co-located with the aggregate module).

The intent in `migration-plan.md` §Stage 1 item 2 is `core/domain/lifecycle/`
for every aggregate. The audit recommends finishing the move in one PR
per runtime and adding an architecture-boundary test that forbids
`*_lifecycle.py` outside the canonical path. The top-level shim at
`shared/control_plane/agent_run_lifecycle.py` was removed in DDD-001
follow-up.

### 5.3 QA Domain Vocabulary Consolidation

The earlier `acceptance_verdicts.py` duplicate was consolidated into
`acceptance_vocabulary.py` by DDD-012. Current QA code keeps the immutable
`AcceptanceVerdict` value object separate from the string vocabulary, and
the vocabulary now matches the runtime schema: L0 gate values, L1
`PASS`/`WARN`/`ERROR`, L2 `INFO`, and L0/L1/L2 finding classifications.

### 5.4 `application_facade.py` as an Emerging Pattern

Recent commits (`refactor(<runtime>): extract application facade`) added
`core/application_facade.py` to every business runtime and capability
plus gateways and coordinator. The pattern composes use cases for a
consistent service-shell entry point. It is not yet documented in
`architecture-principles.md`.

Documented in `architecture-principles.md` §4.7 (Application Facade) by
this audit PR. Architecture-boundary test pending in DDD-011.

### 5.5 Unit-of-Work Coverage Uneven

Explicit `unit_of_work_ports.py` is present in `agents/qa_agent/core/`,
`agents/dev_agent/core/`, and `shared/control_plane/`. Requirement
Manager has a runtime UoW adapter for core command paths. PJM has an
explicit decomposition transaction port (`decomposition_ports.py`) but
not a generalized UoW. Dev Agent event/request handling and scheduler
maintenance now share the Dev UoW boundary, including task/log/outbox
stores and the reconcile advisory lock. Sync, Analysis, Evolution,
Coordinator, and the gateways still have write paths that rely on
implicit session context boundaries (P2-6 partial).

Recommendation: extend explicit UoW to every runtime that can perform a
multi-aggregate write (Requirement, Sync, Evolution, Coordinator). Use
cases that touch only one aggregate may keep the implicit boundary.

### 5.6 Domain Events Are Not Raised by Aggregates

The repository publishes integration events through per-runtime outboxes,
but the audit found few cases where the aggregate itself raises an
in-memory domain event collected by the use case (Vernon 2013 Chapter 8,
Cosmic Python Chapter 8). Most use cases construct the outbox payload
inline. This couples the application layer to the event schema and
makes the aggregate's behavior less self-describing.

Recommendation: standardize on a `<Aggregate>.events` collection raised
by aggregate methods and drained by the application service into the
outbox in the same transaction. Documented in
`architecture-principles.md` §4.8 (Aggregate-Raised Domain Events) by
this audit PR.

### 5.7 String-Status Behavior Outside FSMs

Known gap H4 / P1-2: `shared/capabilities/sync/core/engine.py:74-87`
drives behavior off `op_status == "failed" or feishu_status == "failed"`.
Analysis previously carried the same anti-pattern in
`AnalysisReportLog.status`; the current branch maps persisted report-log rows
through `AnalysisReportLogRecord` and `AnalysisReportStatus` before status
writes (see §4.11). Evolution remains the positive counter-example:
`EvolutionRolloutState` and `ApprovalStatus` are typed enums with transition
checks (§4.12).

Recommendation: replace each `status: str` field whose value drives
behavior with a typed enum + transition table inside the aggregate.
Raise a typed `IllegalTransitionError` on disallowed moves. Add an
architecture-boundary test that flags string-equality on `*_status`
fields outside test fixtures.

### 5.8 Value-Object Underuse

Aggregates use plain `str` and `UUID` for identifiers (`work_item_id`,
`run_id`, `approval_id`, etc.). Without `NewType` or value-object
wrappers, the type system cannot stop one identifier being passed where
another is expected. Cosmic Python Chapter 5 and Vernon 2013 Chapter 6
both recommend identity types.

Recommendation: introduce `shared/control_plane/identifiers.py` (or
`shared/core/identifiers.py`) with `NewType` wrappers for the canonical
identifier set. Adopt one identifier per PR to avoid mass changes.

### 5.9 Repository Pattern Drift

Most stores return Pydantic domain models. Two known leaks were closed
this year (`ApprovalRequestTable` removed from `approval_gate.py`;
`CompanyContextTable` removed from `create_company`). The audit found
no new leaks but recommends adding an architecture-boundary test that
forbids `Table` return types in any `*_store.py` public method.

### 5.10 Anti-Corruption Layers Are Mixed

Integrations under `shared/integrations/` expose port interfaces through
`shared/core/integration_ports.py`: OpenProject returns typed
`OpenProjectWorkPackage` records, WeCom has `WecomMessengerPort`,
OpenClaw has `OpenClawIntegrationPort`, and adapter-specific SDK/JSON-RPC
shapes stay behind integration adapters. Per-integration evidence is
tabulated in §4.14; DDD-013 and DDD-022 are code-complete.

### 5.11 Ubiquitous Language Documentation Gap

Only the Control Plane has its vocabulary captured in
[`docs/overview/glossary.md`](../overview/glossary.md) and
[`docs/overview/product-model.md`](../overview/product-model.md).
Business agents and capabilities do not have per-context glossary
sections; the audit recommends one glossary subsection per context,
linked from each runtime's README — satisfying
`backend-evolution-plan.md` §5 item 3.

### 5.12 Gateway-Owned Product Tables (Boundary Violation)

User Interaction Gateway historically owned three product-domain
tables prefixed `chat_agent_*`. The table prefix itself signals the
intended owner: a `chat-agent` runtime, not a gateway.
`module-boundaries.md` §2.7 states "Gateway must not own
product-domain records." DDD-016 Steps 2-7 moved canonical
persistence, ports, use cases, runtime composition, scheduler, outbox
dispatching, and HTTP APIs into `agents/chat_agent/`, then removed the
legacy gateway `core/`, `db/`, and `models/` compatibility aliases for
chat-agent product state. The gateway now keeps only transport,
webhook intake, card rendering/transport, and chat-agent HTTP client
adapters. Channel Gateway remains the reference for how a clean gateway
looks (§4.9).

### 5.13 Infrastructure Leaks Into Gateway and Coordinator Cores

This finding is closed for the previously affected contexts:

- User Interaction / chat-agent extraction: `ConversationEnginePort` and
  `ConversationEngineFactory` live in `agents/chat_agent/core/chat_ports.py`,
  concrete composition happens in the chat-agent service layer, and gateway
  production code no longer imports chat-agent internals.
- Coordinator: `services/orchestration/coordinator/core/event_use_cases.py`
  uses `CoordinatorThinkerPort`, so raw LLM output cannot cross the
  application boundary without typed translation into `Decision` records.

Keep the rule active for new use cases: infrastructure, SDK, and LLM
composition must enter cores through named ports.

### 5.14 Coordinator Durability Is Implicit

`services/orchestration/coordinator/db/state_store.py:13`
`CoordinatorStateStore` is an in-memory adapter behind a port. The
state-port design allows a durable adapter (Postgres-backed or
Redis-backed) but none ships. Operator replay is therefore not possible
for in-flight coordination decisions. DDD-018 closes the Phase 1 audit
§11 open question 2.

### 5.15 Context-Map Relationships Are Implicit

`module-boundaries.md` §2 lists outbound dependencies per context but
does not classify the relationship (upstream/downstream, customer/supplier,
conformist, ACL, partnership, separate ways). Brandolini context-mapping
notation is industry-standard for big-tech architecture decks.

Recommendation: extend each context section in `module-boundaries.md`
with a "Context-map relationships" sub-row using Brandolini terminology.

---

## 6. Remediation Roadmap

Each gap is one ticket-shaped row. Severity reflects DDD-compliance risk,
not operational risk. Stage mapping is to
[`migration-plan.md`](./migration-plan.md).

| ID | Context | Dimension | Severity | Suggested PR | Stage | Blocks |
|----|---------|-----------|----------|--------------|-------|--------|
| DDD-001 | Control Plane | 2 / 8 | high | ✅ Seed + impl steps merged (#243 + #248 + #264 + this PR). `shared/control_plane/domain/agent_run.py` exposes the `AgentRun` aggregate class wrapping the existing Pydantic record + `VALID_TRANSITIONS` FSM + typed `InvalidAgentRunTransitionError` + `AgentRunStatusChanged` domain event. `shared/control_plane/domain/lifecycle/agent_run_lifecycle.py` (wakeup) and `shared/control_plane/runtime_plugin_use_cases.py` (event-handler) gate transitions through the aggregate FSM before persistence. The legacy shim at `shared/control_plane/agent_run_lifecycle.py` was deleted; `shared/control_plane/agent_runner.py` now imports the lifecycle helpers directly from their canonical `domain/lifecycle/` location. | 2 | DDD-006 follow-up |
| DDD-002 | Business agents (Stage 1 slice) | 1 | medium | ✅ **Complete** for business agents + Control Plane. `tests/unit/test_architecture_boundaries.py::test_lifecycle_modules_live_in_canonical_domain_path` blocks `*_lifecycle.py` at `core/` top level OR at bare `core/domain/` across the four business agents AND `shared/control_plane/domain/` — canonical location is `core/domain/lifecycle/`. Control Plane FSM consolidation landed alongside: the older duplicate `AgentRunLifecycle` aggregate was deleted; `TERMINAL_STATUSES` promoted to the canonical `shared/control_plane/domain/agent_run.py`; the only AgentRun aggregate now owns the FSM. `core/domain/` mandatory enforcement for capabilities + coordinator + identity is deferred to Stage 2 when aggregates land in those contexts. | 1 | done |
| DDD-003 | Sync (both sub-boundaries) | 2 / 3 / 8 | high | ✅ Seed + impl steps merged (#244 + #249 + #273 + #274). `shared/capabilities/sync/core/domain/sync_operation.py` exposes `SyncOperation` aggregate + `SyncOperationStatus` enum + `VALID_TRANSITIONS` FSM + `SyncSide` discriminator + `combine_side_statuses()`. `core/engine.py`, `core/feishu_bitable_sync.py`, and `core/openproject_sync.py` all gate state transitions through the aggregate FSM (PENDING → RUNNING → SUCCEEDED/FAILED). Illegal in-engine transitions now raise `InvalidSyncOperationTransitionError` instead of silently passing. External dict contract (\`"success"\` / \`"failed"\` / \`"skipped"\`) is preserved for backward compatibility with all callers and tests. Remaining DDD-003 scope folds into DDD-014 (runtime extraction). | 2 | DDD-014 (extraction) |
| DDD-004 | Analysis | 9 / 10 / 11 | high | ✅ **Complete** — seed + full follow-up sequence merged (`<DDD-004 PR>` + #252 + #276 + #278 + #279 + #280 + current branch). `shared/capabilities/analysis/core/domain/projection.py` exposes `WorkPackageProjection` + `SubtaskProgressProjection` frozen value objects + `WorkPackageProjectionPort` Protocol. `core/domain/in_memory_projection.py` ships the in-memory adapter (#252). `db/projection_store.py` + `models/projection.py` + `migrations/versions/20260524_analysis_projection_tables.py` ship the Postgres adapter with `ON CONFLICT DO UPDATE` upserts (#276; idempotent replay-safe per `data-ownership.md` §1.8). `core/projection_updater.py` consumes OpenProject + Feishu Bitable into projection rows (#278) and is wired into `core/event_use_cases.py::AnalysisEventUseCase` so `sync.completed` triggers a refresh (#279). `core/daily_report.py`, `core/weekly_report.py`, and `core/milestone_checker.py` now read task data from `WorkPackageProjectionPort` instead of `OpenProjectWorkPackagePort` / `BitableTablePort` directly, closing the §2.9 broken Customer/Supplier finding in `module-boundaries.md` and the remaining Analysis application-service purity gap. | 3 | done |
| DDD-005 | Evolution | 2 / 9 | medium | ✅ Documented (#240) + EvolutionProposal aggregate landed (this PR). Package split between `shared/capabilities/evolution/` (L2 capability service) and `shared/evolution/` (L1/L2/L3 runtime primitives) is intentional per the [project layout](../overview/project-layout.md). `shared/control_plane/domain/evolution_proposal.py` now exposes the `EvolutionProposal` aggregate class wrapping the existing Pydantic record + `VALID_ROLLOUT_TRANSITIONS` FSM (proposed → shadow/canary/rejected; shadow → canary/rolled_back; canary → active/rolled_back; active → rolled_back; rolled_back/rejected terminal) + typed `InvalidEvolutionRolloutTransitionError` + `EvolutionRolloutStatusChanged` domain event. 13 unit tests covering FSM + event semantics; `test_business_aggregates_have_unit_tests` extended. Approval state remains owned by `approval_gate.py`. Remaining: aggregate promotion for `EvolutionTrace`, `Reflection`, `Experiment` as those records grow non-trivial state. | 2 | trace/reflection/experiment aggregates |
| DDD-006 | All product-owning runtimes | 7 | medium | ✅ **Complete** — pattern landed in every product-owning runtime. Status by runtime: Requirement (`requirement.py:41-48` `RequirementStatusChanged` raised + drained ✓), PJM (`decomposition.py:48-54` `DecompositionStatusChanged` ✓), Dev (`task.py:46-52` `TaskStatusChanged` ✓), QA (n/a — DDD-021 records no-aggregate decision), Control Plane (`shared/control_plane/domain/agent_run.py:59-68` `AgentRunStatusChanged` raised on every `transition_to()`; drained via `pull_events()`. Wakeup path gated by aggregate in #248, runtime-plugin event-handler path in #264; both call `_validate_run_transition_via_aggregate` / `_gate_agent_run_transition` before persistence so illegal transitions raise `InvalidAgentRunTransitionError` and audit-event writes carry the same intent.) Pattern is binding via `architecture-principles.md` §4.8 (landed with the foundation audit PR). | 2 | done |
| DDD-007 | All contexts | 4 / 5 | medium | ✅ **Complete** for the current public Protocol surface. `shared/core/identifiers.py` exposes `NewType` wrappers + factories (#233). Per-identifier adoption across control-plane ports/stores: `WorkItemId` (#251), `GoalId` (#256), `AgentRunId` (#257), `ApprovalRequestId` (#259), `DecisionId` (#261), `ArtifactId` (#262), `BudgetPolicyId` (#263), `CompanyId` (#265 + #266 + #267 + #268 + #269 — full Protocol coverage across all 17 control-plane port/store pairs), current-branch `EvolutionProposalId` coverage for evolution-proposal get/status persistence boundaries, current-branch `AgentRoleId` coverage for agent-registry role lookup/update persistence boundaries, and current-branch Requirement Manager `RequirementId` + `MeetingId` + `OpenQuestionId` coverage for requirement/meeting/question store and lifecycle/read/answer boundaries. The rule (`architecture-principles.md` §4.9) is binding for new code; remaining identifiers (`BudgetUsageId`, `AuditEventId`, `AgentPromptConfigId`) are model fields only with no public Protocol surface consuming them as input today. | 2 | done |
| DDD-008 | All product-owning runtimes | 12 | low | ✅ Landed DDD-008 (this PR). Every §2.X subsection in `module-boundaries.md` now has a Brandolini-style "Context-map relationships" row classifying upstream/downstream with Customer/Supplier, Conformist, ACL, Open-Host Service, Published Language, Partnership, Separate Ways terminology | 1 | done |
| DDD-009 | All product-owning runtimes | 1 | low | ✅ Merged across two PRs (#231 + #238). Every product-owning runtime now has a DDD-shaped README with Bounded Context, Ubiquitous Language, Context-Map Relationships sections. requirement_manager, pjm_agent, dev_agent (new in #231); QA (extended in #234); sync, analysis, coordinator, user_interaction (new in #238); Evolution + Channel already had READMEs. | 1 | done |
| DDD-010 | Coordinator, Evolution | 3 / Application | medium | ✅ **Complete** — seed + impl steps + first per-caller migration merged (#242 + #253 + #254 + #298). `services/orchestration/coordinator/core/unit_of_work_ports.py` + `shared/capabilities/evolution/core/unit_of_work_ports.py` define `CoordinatorUnitOfWork` / `EvolutionUnitOfWork` Protocols + factories; `db/in_memory_unit_of_work.py` provides concrete adapters + async-context factories. `CoordinatorEventUseCase` (#298) routes both write modes (progress agent-state update + decision persist) through the UoW when wired; `service/agent.py` builds the factory from the current state + outbox stores. Evolution UoW infra is in place; per-caller migration follows when `EvolutionEventUseCase` adds write paths beyond the current seed bootstrap. Requirement Manager already had `RequirementUnitOfWork`. | 2 | done |
| DDD-011 | Cross-cutting | application | low | ✅ Landed `<DDD-011 PR>`. `tests/unit/test_architecture_boundaries.py::test_application_facade_depends_on_ports_and_use_cases_only` blocks imports from `shared.db`, `shared.infra`, `shared.integrations`, `shared.messaging.inbound/outbound`, and any relative `db`/`adapters`/`service`/`app` modules across all 10 facade files | 1 | done |
| DDD-012 | QA | 4 | low | ✅ Merged (#229). Renamed `acceptance_verdicts.py` → `acceptance_vocabulary.py` (and matching test). QA `core/domain/` now has distinct names: `acceptance_verdict.py` (value object), `acceptance_vocabulary.py` (constants vocabulary). 5 caller imports migrated. | 1 | done |
| DDD-013 | All adapters | 11 | medium | ✅ **Complete** — merged (#237 + #285 + #296). `OpenClawIntegrationPort` typed-shape (#237) + agent-local adapter SDK-leak audit (#285) confirmed the 5 agent-local adapters do not leak vendor SDK types at their public surface. `OpenProjectWorkPackagePort` now returns the typed `OpenProjectWorkPackage` TypedDict (#296) — runtime shape unchanged but mypy can flag field-name typos at every `wp.get("...")` call site. | 2 | done |
| DDD-014 | Sync runtime | service-boundary | high | ✅ **Code complete** — decision + Step 1 internal split landed (#247 + #290 + #291 + #292). [`docs/adr/0009-sync-sub-runtime-split.md`](../adr/0009-sync-sub-runtime-split.md) records the two-step split. The CODE architecture conforms to DDD: `core/openproject/engine.py` + `core/feishu_bitable/engine.py` own the sub-engines via sub-packages (#290, #291); per-side `OpenProjectSyncStore` / `FeishuBitableSyncStore` Protocols + SQLAlchemy adapters are already split (sub-step 3); per-side `sync_openproject_event_outbox` + `sync_feishu_bitable_event_outbox` tables + Alembic migration shipped (#292). **Remaining is deployment cutover (Step 2 of ADR-0009)**: dual-write enable → per-side dispatcher plugin enable → runtime container split → legacy single sync-module retire. The cutover is operator-scheduled per ADR with a two-week bake window in staging; no further code refactor is required to close the DDD compliance dimension. | 4 | done (code); deployment cutover scheduled per ADR-0009 |
| DDD-015 | Cross-cutting | testing | medium | ✅ **Complete** for landed aggregates — `<DDD-015 PR>` + this PR. Every landed aggregate has a matching unit-test file: `agents/{requirement_manager,pjm_agent,dev_agent,qa_agent,chat_agent}` including chat-agent `ConversationTranscript`, `CardOperationLogEntry`, and `DailyProgressEntry`; `shared/control_plane/domain/agent_run.py` (DDD-001); `shared/control_plane/domain/approval_request.py`, `shared/control_plane/domain/goal.py`, `shared/control_plane/domain/work_item.py`, `shared/control_plane/domain/decision.py`, `shared/control_plane/domain/artifact.py`, `shared/control_plane/domain/budget_policy.py`, `shared/control_plane/domain/budget_usage.py`, and `shared/control_plane/domain/company_context.py`; `shared/control_plane/domain/evolution_proposal.py` (DDD-005); `shared/capabilities/sync/core/domain/sync_operation.py` (DDD-003); `shared/capabilities/analysis/core/domain/projection.py` (DDD-004). `tests/unit/test_architecture_boundaries.py::test_business_aggregates_have_unit_tests` now enforces this as a binding rule by asserting each aggregate→test pair exists; future aggregates must extend the expected list, blocking aggregate landings without unit tests. | 2 | done |
| DDD-016 | User Interaction Gateway | boundary | **high** | ✅ **Complete for the gateway code boundary** — decision + Steps 1-7 landed (#247 + #293 + #299 + this branch). `chat_service.py`, `tools.py`, `bitable_operations.py`, `daily_tasks.py`, application facade/request/event/outbox/health/scheduler use cases, core ports, repositories, SQLAlchemy adapters, service runtime composition, scheduler, and the outbox dispatcher live under `agents/chat_agent/`. The default `chat-agent` runtime entrypoint resolves to `agents.chat_agent.app.main:app`; `/api/v1/chat-agent/conversation/{user_id}` and `/api/daily-progress` provide read boundaries, `/api/v1/chat-agent/requests` is the webhook chat request boundary, and `/api/bitable/*` belongs to chat-agent API. Gateway app/service/webhook paths and compatibility daily-progress/Bitable API routes use `ChatAgentClient` HTTP adapters. Legacy gateway `core/`, `db/`, and `models/` aliases for chat-agent product state were removed, and architecture tests forbid production gateway imports of `agents.chat_agent.*`. | 3 | done |
| DDD-017 | User Interaction Gateway | application purity | **high** | ✅ **Complete for gateway purity** — `ConversationEnginePort` / `ConversationEngineFactory` live in `agents/chat_agent/core/chat_ports.py`; concrete engine composition is bound in `agents/chat_agent/service/agent.py`; gateway production code no longer imports chat-agent internals or composes the conversation engine in-process. | 2 | done |
| DDD-018 | Coordinator | durability | **high** | ✅ **Complete** — decision + full follow-up sequence merged (#241 + #260 + #282 + this PR). [`docs/adr/0008-coordinator-durable-state-store.md`](../adr/0008-coordinator-durable-state-store.md) records the Postgres-backed adapter choice; same persistence boundary as `coordinator_event_outbox` per ADR-0002. Schema migration + `PostgresCoordinatorStateStore` adapter shipped in #260; replay tooling shipped in #282 (`services/orchestration/coordinator/app/replay.py` reads workflow + decisions + agent states, prints summary, and runs referential consistency checks; exit codes 0 OK / 1 inconsistent / 2 IO error). Replay runbook now lives in `services/orchestration/coordinator/README.md` § Runbook: Replay Tool with escalation criteria. In-memory adapter kept for unit tests; production flipped on via `COORDINATOR_DURABLE_STATE`. Closes Phase 1 audit §11 open question 2. | 2 | done |
| DDD-019 | Coordinator | ACL | medium | ✅ Landed `<DDD-019 PR>`. `services/orchestration/coordinator/core/event_use_cases.py` promotes `CoordinatorThinker` from a Callable type alias to `CoordinatorThinkerPort` Protocol with explicit `__call__` signature returning typed `list[Decision]`. ACL boundary now named per `architecture-principles.md` §4.6; raw LLM output cannot escape the port. Architecture-boundary test updated to require the Protocol class. | 2 | done |
| DDD-020 | Requirement Manager, Dev Agent | layering | medium | ✅ Landed `27a5a5d24`. Six callers migrated to `core/domain/lifecycle/`; both shims deleted; architecture-boundary tests updated to require the canonical path | 1 | done |
| DDD-021 | QA Agent | aggregate | medium | ✅ Landed `<DDD-021 PR>` + current branch follow-up. `agents/qa_agent/core/domain/acceptance_run.py` now models `AcceptanceRun` as a lifecycle aggregate with `AcceptanceRunId`, `AcceptanceRunStatus`, requested/running/completed transitions, completion invariants, `AcceptanceRunCompleted`, blocking-finding selection, and an event buffer; `AcceptanceVerdict` remains the immutable verdict value object. `acceptance_execution_use_cases.py` completes the aggregate and drains events before persisting the completed projection with the same run id inside the QA UoW. | 2 | done |
| DDD-022 | Integration Plane | port coverage | medium | ✅ **Complete** — merged (#236 + #296). `WecomMessengerPort` Protocol added (#236). `OpenProjectWorkPackagePort` typed-record return shipped in #296 via the `OpenProjectWorkPackage` TypedDict; this closes the row dependency on DDD-013. | 2 | done |

Severity legend: **high** = closes a known H#/P# gap; **medium** = closes
a known M# gap or removes a cross-context anti-pattern; **low** =
documentation or test additions.

PR-shape constraint: every remediation row above fits inside the
existing migration-plan stage cadence (no new stage, no new framework,
no new runtime identifier). Each row is one reviewable PR under the
`architecture-principles.md` §3 constraints.

---

## 7. Sibling-Doc Reconciliation

Changes applied in the audit PR:

| Document | Section | Change |
|----------|---------|--------|
| `architecture-principles.md` | §1 Domain row | Made `core/domain/` mandatory for every product-owning runtime; gateways excluded. |
| `architecture-principles.md` | §4 Tactical Guidance | Added §4.7 Application Facade, §4.8 Aggregate-Raised Domain Events, §4.9 Identifier Value Objects, §4.10 State Machines (Security renumbered to §4.11). |
| `module-boundaries.md` | §1 how-to-read | Added "Context-map relationships" schema field (Brandolini); per-context population is DDD-008. |
| `module-boundaries.md` | §3 cross-context rules | Added rule 7 (every product-owning context has a `core/domain/` package) and rule 8 (gateways must not own product-domain records — references DDD-016). |
| `backend-evolution-plan.md` | §3 gap table | Added rows for the User Interaction product-table violation (DDD-016), infra leak (DDD-017), coordinator durability (DDD-018), anemic aggregates (DDD-001/003/005); existing "Agent core/ mixes use cases with domain rules" row now points to this audit. |
| `backend-evolution-plan.md` | §4 phases | Phase B exit criteria reference DDD-001 through DDD-022. |
| `backend-evolution-plan.md` | §5 tasks | Rewrote to cross-link this audit's DDD-### rows so the two documents stop drifting. |
| `docs/INDEX.md` | §Architecture | Appended link to this document. |
| `AGENTS.md` | Historical Part 3 Architecture Boundary Rules | Added rule 14: "Every product-owning runtime materializes an explicit `core/domain/` package per `architecture-principles.md` §1." The current rule lives in [Architecture Principles §1](./architecture-principles.md#1-layering-rules). `CLAUDE.md` remains a symlink to `AGENTS.md`. |

Reconciliation runs in the same PR per `architecture-principles.md`
§5 — sibling-doc drift is the most common source of confusion for new
contributors and agents.

---

## 8. Verification

This document is verifiable against the repository's current state:

- `git diff --check` clean on this branch.
- Every internal link resolves to an existing file on disk.
- File-and-line citations in §4 reflect the tree at the commit this PR
  targets. When a remediation PR moves a file, it updates the citation
  in this audit in the same change.
- No file under `agents/`, `services/`, `shared/`, `migrations/`,
  `rust/`, `frontend/`, `docker/`, `infra/`, `scripts/`, `tests/`, or
  `plugins/` is modified by this audit PR.

Re-audit cadence: every Stage 2/3 PR updates the relevant per-context
scorecard row. A full re-audit runs when migration-plan §Stage 4 begins.

---

## 9. Maintenance

When this document changes, the following must be reconciled in the same PR:

- `architecture-principles.md` (§1 layering, §4 tactical, §5 PR compliance).
- `module-boundaries.md` (§2 catalog and §3 rules).
- `backend-evolution-plan.md` (§3 gap table, §4 phases, §5 tasks).
- `backend-target-architecture.md` (§5 stages — verify no scope conflict).
- `docs/INDEX.md` (architecture section).
- [AGENTS.md](../../AGENTS.md#boundaries) (core rules and reading paths).

When a remediation row in §6 lands, mark it complete in this document or
remove it from the table; do not let completed rows accumulate.
