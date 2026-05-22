# DDD Compliance Audit

Last updated: 2026-05-22

Status: Foundation document. Joins the Stage 0 architecture doc set under
`docs/architecture/`. Reconciles with
[`architecture-principles.md`](./architecture-principles.md),
[`module-boundaries.md`](./module-boundaries.md),
[`backend-evolution-plan.md`](./backend-evolution-plan.md),
[`backend-target-architecture.md`](./backend-target-architecture.md), and
[`backend-architecture-analysis.md`](./backend-architecture-analysis.md).
When this file changes, those four siblings plus `AGENTS.md` Part 3 must be
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

No code or schema changes are made by this PR.

---

## 2. Executive Summary

The repository implements **strategic** DDD well: bounded contexts are
named, owned, and reconciled to runtime ownership in
[`module-boundaries.md`](./module-boundaries.md). Inter-context contracts
flow through HTTP, RPC, and the outbox-backed EventBus. ORM rows do not
cross boundaries. The Identity boundary has a single write owner per
[`identity-boundary.md`](./identity-boundary.md).

**Tactical** DDD is uneven. Four of twelve contexts have an explicit
`core/domain/` directory; one (Control Plane) has both a `domain/`
subdirectory and a top-level lifecycle module. The remaining contexts
hold domain logic inside use-case or lifecycle modules. State-machine
modeling is partial: aggregates have begun to land (Decomposition, Task,
Requirement, AcceptanceVerdict, AgentRunLifecycle) but string-status
patterns persist in Sync and parts of the capabilities. Domain events
are not consistently raised by aggregates — many use cases write
directly to the outbox.

Big-tech-standard remediation is achievable inside the existing migration
plan without introducing a new framework, new stage, or new runtime
identifier. The remediation in §6 packages remaining work as ten
review-friendly PRs distributed across migration-plan Stages 2 through 5.

Aggregate compliance score across the thirteen contexts (gateways score
several dimensions as `n/a` by design — see §4.9):

| Status | Count | % of 156 cells | % excluding n/a |
|--------|-------|----------------|-----------------|
| ✓ Fully compliant | 50 | 32% | 33% |
| ⚠ Partial | 55 | 35% | 37% |
| ✗ Missing | 46 | 29% | 30% |
| n/a | 5 | 3% | — |

Highest-compliance context: **Evolution** (8 ✓ / 4 ⚠ / 0 ✗). Driven by an
explicit `EvolutionRolloutState` FSM, port-based stores, pure use cases,
and an established `ApprovalGate` domain service.

Lowest-compliance contexts: **Sync (both sub-boundaries)** and **Analysis**
(2 ✓ / 4 ⚠ / 6 ✗ each). Sync has no aggregate root and runs on string-status
comparisons; Analysis reads source-domain data directly without a
projection.

Highest-risk single finding: **User Interaction gateway owns product-domain
tables** (`chat_agent_conversation_histories`, `chat_agent_card_operations`,
`chat_agent_daily_progress`). This is a `module-boundaries.md` §2.7
violation and is tracked as **DDD-016** (high severity).

Three further sleeper findings (not previously catalogued):

- User Interaction `core/chat_service.py` imports `ConversationEngine` from
  `shared.infra.conversation_engine` — breaks application-layer purity
  (DDD-017).
- `CoordinatorStateStore` is in-memory by default; the port-backed design
  allows a durable adapter but none ships — durability is implicit
  (DDD-018; closes Phase 1 audit §11 open question 2).
- Requirement Manager and Dev Agent each ship **two** copies of their
  lifecycle module (legacy at `core/<aggregate>_lifecycle.py` and modern
  at `core/domain/lifecycle/<aggregate>_lifecycle.py`) (DDD-020).

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
- Aggregates inventory: Company, Goal, AgentRole, WorkItem, AgentRun, Decision, ApprovalRequest, BudgetPolicy, BudgetUsage, Artifact, AuditEvent, EvolutionProposal, AgentPromptConfig.
- `core/domain/` present: yes — `shared/control_plane/domain/` exists plus `agent_run_lifecycle.py` at top level (inconsistent location for one aggregate).
- UoW: `ControlPlaneUnitOfWork` in `shared/control_plane/unit_of_work.py` spans command routes only.
- Notable: per-aggregate `*_store.py` + `*_ports.py` + `*_use_cases.py` split landed in PR #121; legacy `repository.py` facade retired (per `backend-architecture-analysis.md` §H2 closed).

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | `SPEC.md` §3.1 names the ledger; `shared/control_plane/domain/__init__.py` declares the layer | No per-context ubiquitous-language glossary; product vocabulary lives in `docs/overview/product-model.md` but is not pulled into a per-runtime glossary |
| 2 | Aggregate root explicit | ✗ | `shared/control_plane/models.py:20-90` defines 13 Pydantic records (Company, Goal, WorkItem, AgentRun, Decision, ApprovalRequest, Artifact, BudgetPolicy, BudgetUsage, AuditEvent, EvolutionProposal, AgentRole, AgentPromptConfig); none expose invariant-enforcing methods | All 13 aggregates are anemic Pydantic records; invariants live in `*_use_cases.py` and `domain/lifecycle/` |
| 3 | Aggregate consistency boundary | ⚠ | `shared/control_plane/unit_of_work.py` `ControlPlaneUnitOfWork` spans 14 aggregates in one transaction; `shared/control_plane/approval_use_cases.py:43-53` writes both `ApprovalRequest` and `EvolutionProposal` in one flush | Vernon 2013 rule "one aggregate per transaction" violated for the approval→proposal flow; needs explicit domain service or eventual-consistency seam |
| 4 | Value objects | ✗ | `BudgetPolicy.limit_usd`, `BudgetUsage.cost_usd` are plain `float`; `models.py` has no frozen dataclasses or `model_config = ConfigDict(frozen=True)` | No `Money`/`BudgetAmount`/`Email` value objects; equality-by-value not modeled |
| 5 | Entities (identity-based) | ⚠ | `shared/core/ids.py` `IDPrefix` enum gives typed prefixes; aggregates use string IDs generated via `generate_id(IDPrefix.*)` | IDs remain `str`; no `NewType` wrappers so `work_item_id` and `goal_id` are interchangeable to the type system |
| 6 | Domain services | ⚠ | `shared/control_plane/approval_gate.py:28-112` `ApprovalGate` orchestrates multi-step approval; `decision_use_cases.py:171-205` `_validate_execution_links()` reads three aggregates for consistency | Services exist but are unmarked (no `DomainService` base or naming convention); cross-aggregate logic is buried in use-case helpers |
| 7 | Domain events | ✗ | No `DomainEvent` class; aggregates do not raise events; `domain/lifecycle/agent_run_lifecycle.py:63-76` writes `AuditEvent` rows directly to store | Audit is persisted as fact, not collected as in-memory domain event; no aggregate-raised event pattern |
| 8 | State machine | ⚠ | `models.py:20-90` defines `AgentRunStatus`, `WorkItemStatus`, `ApprovalStatus`, `DecisionStatus`, `EvolutionRolloutState` as StrEnum; `approval_gate.py:103` compares `row.status != ApprovalStatus.APPROVED.value` | Enums exist but no transition table; no `IllegalTransitionError`; string `.value` comparisons throughout |
| 9 | Repository pattern | ✓ | `shared/control_plane/*_store.py` return domain records via `shared/control_plane/domain_records.py` mappers (e.g. `approval_store.py:9,33`); private `_*_row()` helpers stay internal | Ports return domain models; ORM `*Table` types do not escape |
| 10 | Application service purity | ✓ | `*_use_cases.py` import only models, ports, `shared.schemas.event`; `budget_use_cases.py:61-99` delegates to store ports; no SQLAlchemy or SDK imports | Use cases are pure |
| 11 | ACL for external systems | ⚠ | `ApprovalGate` provides an approval sync boundary; `agent_registry_store.py` has `adapter_type` / `adapter_config` fields | No documented ACL between control plane and EventBus / LLM gateway consumers |
| 12 | Context-map relationship | ✗ | `SPEC.md` names ownership; `module-boundaries.md` §2.1 lists outbound deps | No Brandolini-typed relationships (customer/supplier, conformist, ACL) classified |

**Summary**: 2 ✓ / 6 ⚠ / 4 ✗ (out of 12). Strong technical hygiene (repository + use-case purity) but weak tactical DDD (anemic aggregates, missing FSM/domain-event patterns, UoW too wide).

### 4.2 Requirement Management

- Runtime owner: `agents/requirement_manager/`
- Aggregate landed: `Requirement` (Stage 2 PR #139).
- `core/domain/` contents: `requirement.py`, `lifecycle/` subdir.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | `module-boundaries.md` §2.2 names the context | No per-runtime README or glossary; ubiquitous-language for `Meeting`, `Requirement`, `OpenQuestion`, `FeedbackRecord` not documented |
| 2 | Aggregate root explicit | ✓ | `agents/requirement_manager/core/domain/requirement.py:52-101` `Requirement` aggregate with `transition_to()`, `pull_events()`, `InvalidRequirementTransitionError` | Clear aggregate; raises typed transition error |
| 3 | Aggregate consistency boundary | ⚠ | `requirement.py:66-91` one event per transition; `request_use_cases.py:57-68` wraps in UoW context | UoW pattern present but no explicit cross-aggregate write rule documented |
| 4 | Value objects | ✗ | `RequirementStatusChanged` is frozen dataclass; no other immutable types; `requirement_id` is `str` | No `RequirementId`, `MeetingId`, `OpenQuestionId` value objects |
| 5 | Entities (identity-based) | ⚠ | `requirement.py:55` uses raw string `requirement_id` | No `NewType` identity wrappers |
| 6 | Domain services | ✗ | Logic spread across `request_use_cases.py`, `feedback_use_cases.py`; no `DomainService` class | Cross-aggregate logic (e.g. feedback learning that updates requirements) lives in use cases |
| 7 | Domain events | ✓ | `requirement.py:41-48` `RequirementStatusChanged` frozen domain event; `pull_events()` drained by use case for outbox | Events raised by aggregate, collected by UoW, staged in outbox |
| 8 | State machine | ✓ | `core/domain/lifecycle/requirement_states.py:31-36` `VALID_TRANSITIONS` dict; `requirement.py:75-77` validates before transition | Explicit FSM with transition table; typed transition error |
| 9 | Repository pattern | ✓ | `agents/requirement_manager/core/unit_of_work_ports.py:22-30` `RequirementUnitOfWork` Protocol; `requirement_ports.py` defines `RequirementStore` | Port + adapter clean |
| 10 | Application service purity | ✓ | `request_use_cases.py:1-110` no ORM, no SQL, no HTTP client imports; only `domain.transition_to()` and UoW orchestration | Pure |
| 11 | ACL for external systems | ⚠ | `agents/requirement_manager/adapters/feishu_cards.py` delegates to `shared.integrations.feishu.cards.requirement`; no agent-local Feishu→domain translation | ACL lives in shared/, not agent-local; weaker than Dev agent pattern |
| 12 | Context-map relationship | ✗ | No agent README; upstream (`meeting_uploaded`) and downstream (`requirement.*` events) not classified | Implicit; no Brandolini relationship type |

**Summary**: 5 ✓ / 5 ⚠ / 2 ✗. Stage 2 strong; major remaining: legacy `core/requirement_lifecycle.py` duplicates `core/domain/lifecycle/requirement_lifecycle.py` (DDD-020).

### 4.3 Planning / PJM

- Runtime owner: `agents/pjm_agent/`
- Aggregate landed: `Decomposition` (Stage 2 PR #137).
- `core/domain/` contents: `decomposition.py`, `lifecycle/` subdir.
- UoW: `agents/pjm_agent/core/decomposition_ports.py` defines an explicit
  decomposition transaction boundary (P2-6 partial closure).

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | `module-boundaries.md` §2.3 names the context | No PJM README or glossary; `decomposition`, `approval`, `work-package` vocabulary not formalized |
| 2 | Aggregate root explicit | ✓ | `agents/pjm_agent/core/domain/decomposition.py:58-108` `Decomposition` aggregate with `wp_id` identity, `transition_to()`, `pull_events()` | Clear aggregate root |
| 3 | Aggregate consistency boundary | ⚠ | `decomposition.py:72-98` single transition per call; `decomposition_orchestrator.py` coordinates multiple aggregates via events | No documented rule preventing cross-aggregate mutations |
| 4 | Value objects | ✗ | `DecompositionStatusChanged` frozen; other types plain strings | No other VOs |
| 5 | Entities (identity-based) | ⚠ | `wp_id` (raw OpenProject int) is identity | No `DecompositionId` / `WorkPackageId` wrapper |
| 6 | Domain services | ✗ | `decomposition_orchestrator.py` orchestrates decompose, approve, recover workflows | Cross-decomposition logic lives in orchestrator (application), not in a domain service |
| 7 | Domain events | ✓ | `decomposition.py:48-54` `DecompositionStatusChanged` raised by aggregate, drained by caller | Pattern correct |
| 8 | State machine | ✓ | `core/domain/lifecycle/decomposition_lifecycle.py:45-52` `VALID_TRANSITIONS`; `decomposition.py:85-90` enforces; raises `InvalidDecompositionTransitionError` | Typed FSM |
| 9 | Repository pattern | ✓ | `decomposition_ports.py:23-49` `PJMDecompositionTransaction` Protocol; `db/` adapters separate | Port-based |
| 10 | Application service purity | ✓ | `request_use_cases.py:1-40` no DB / SQL / HTTP | Pure |
| 11 | ACL for external systems | ⚠ | `adapters/feishu_cards.py` delegates to `shared.integrations.feishu.cards` | No agent-local Feishu→Decomposition ACL |
| 12 | Context-map relationship | ✗ | No README; upstream (`decomposition.request`) and downstream (`decomposition.*`) implicit | No Brandolini classification |

**Summary**: 5 ✓ / 4 ⚠ / 3 ✗. Most consistent Stage 2 layout (no legacy lifecycle duplicate).

### 4.4 Delivery / Dev

- Runtime owner: `agents/dev_agent/`
- Aggregate landed: `Task` (Stage 2 PR #138).
- `core/domain/` contents: `task.py`, `lifecycle/` subdir.
- Open inconsistency: `agents/dev_agent/core/task_lifecycle.py` still lives
  at top level alongside `core/domain/lifecycle/`.
- UoW: `agents/dev_agent/core/unit_of_work_ports.py` explicit.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | `module-boundaries.md` §2.4 names the context | No agent README or glossary; `task`, `workflow`, `risk`, `approval` vocabulary not documented |
| 2 | Aggregate root explicit | ✓ | `agents/dev_agent/core/domain/task.py:56-110` `Task` aggregate with `task_id`, `transition_to()`, `pull_events()`, `is_active()`, `is_in_progress()` | Clear aggregate root |
| 3 | Aggregate consistency boundary | ⚠ | `task.py:70-92` single transition per call; `workflow_execution_use_cases.py` coordinates Task + WorkflowLog | Unclear whether WorkflowLog is a separate aggregate or part of Task |
| 4 | Value objects | ✗ | `TaskStatusChanged` frozen; `risk_level`, `status` plain strings | No `RiskLevel`, `TaskId`, `WorkPackageId` VOs |
| 5 | Entities (identity-based) | ⚠ | `task_id` (str) + `wp_id` (int); two raw types | No identity wrappers |
| 6 | Domain services | ✗ | `workflow_validator.py`, `security_scanner.py`, `risk_assessor.py` are tools, not unified domain services | Tools scattered in `core/`; no domain-service layer |
| 7 | Domain events | ✓ | `task.py:46-52` `TaskStatusChanged` raised by aggregate; `pull_events()` drained by use case | Pattern correct |
| 8 | State machine | ✓ | `core/domain/lifecycle/task_lifecycle.py:20-33` `VALID_TRANSITIONS` (12 states: PENDING, PLANNING, AWAITING_APPROVAL, EXECUTING, …); `task.py:77-84` enforces; raises `InvalidTaskTransitionError` | Most comprehensive FSM in the codebase |
| 9 | Repository pattern | ✓ | `agents/dev_agent/core/repositories.py:25-50` `DevTaskRepositoryPort`; `db/` adapters separate | Port-based |
| 10 | Application service purity | ✓ | `request_use_cases.py`, `workflow_execution_use_cases.py` no SQL / ORM / SDK leaks | Pure |
| 11 | ACL for external systems | ✓ | `adapters/gitlab_client.py:20-50` wraps GitLab API; `adapters/agentforge_client.py` wraps AgentForge SDK; translates external models → domain types | Best-in-class agent-local ACL |
| 12 | Context-map relationship | ✗ | No README; upstream (`pjm` decomposition events, `qa.acceptance-completed`) and downstream (`mr.created`) implicit | No classification |

**Summary**: 6 ✓ / 3 ⚠ / 3 ✗. Best-in-class on ACL and FSM. Legacy `core/task_lifecycle.py` duplicates `core/domain/lifecycle/task_lifecycle.py` (DDD-020).

### 4.5 Quality / QA

- Runtime owner: `agents/qa_agent/`
- Value object landed: `AcceptanceVerdict` (Stage 2 PR #140).
- `core/domain/` contents: `acceptance_verdict.py` plus
  `acceptance_verdicts.py` (pluralized duplicate; suspect refactor
  in flight — flagged in §5).
- UoW: `agents/qa_agent/core/unit_of_work_ports.py` explicit.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `agents/qa_agent/README.md:3-6` describes automated acceptance verification; events table documents `code.committed`, `qa.run-requested`, `qa.acceptance-completed`, `qa.gate-failed` | Only business agent with a README; vocabulary (`run`, `verdict`, `gate`, L0/L1/L2) defined in `acceptance_verdicts.py` |
| 2 | Aggregate root explicit | ⚠ | `AcceptanceVerdict` is a value object, not an aggregate; `agents/qa_agent/core/run_store.py:13-20` `QAAcceptanceRunRecord` is mutable state outside any aggregate; `acceptance_runner.py:24-50` lacks aggregate coordination | No `AcceptanceRun` aggregate to enforce run invariants |
| 3 | Aggregate consistency boundary | ✗ | Run state updated directly in `run_store` without aggregate envelope | No transactional invariant enforcement |
| 4 | Value objects | ✓ | `agents/qa_agent/core/domain/acceptance_verdict.py:36-90` `AcceptanceVerdict` frozen dataclass with `__post_init__` validation, `is_blocking` and `is_clean` properties | Explicitly immutable, equality-by-value VO; constants in `acceptance_verdicts.py` are plain strings (not VOs) — see DDD-012 |
| 5 | Entities (identity-based) | ✗ | `QAAcceptanceRunRecord` uses raw id fields | No identity type |
| 6 | Domain services | ✓ | `acceptance_runner.py:24-50` runs acceptance framework; verdict factory in `event_use_cases.py` computes verdict from L0/L1/L2 status | Limited but isolated |
| 7 | Domain events | ⚠ | `qa.acceptance-completed` event published; not raised by aggregate (no aggregate) | Events flow but not via aggregate-raised pattern |
| 8 | State machine | ✗ | No lifecycle module; runs are one-shot (no transitions); `acceptance_runner.py` runs checks → verdict | No FSM (defensible: run is computational, not stateful), but `qa.run-requested` → `qa.acceptance-completed` could be modeled as aggregate FSM |
| 9 | Repository pattern | ✓ | `run_store.py`, `report_store.py`, `unit_of_work_ports.py` separate persistence; transaction boundary explicit | Port-based |
| 10 | Application service purity | ✓ | `api_use_cases.py`, `event_use_cases.py`, `acceptance_execution_use_cases.py` no direct ORM / SQL; `acceptance_runner.py` calls external subprocess | Pure (subprocess call wrapped) |
| 11 | ACL for external systems | ✗ | `adapters/feishu_cards.py` delegates to shared/; no GitLab/OpenProject ACL for incoming MR/work-package context | Missing translation between source-system data and verdict inputs |
| 12 | Context-map relationship | ✓ | `README.md` events table classifies consume/publish per event | Strongest context-map evidence in the codebase |

**Summary**: 5 ✓ / 2 ⚠ / 5 ✗. Strong on documentation and value objects; weak on aggregate modeling (no `AcceptanceRun` aggregate). Decision needed: promote run to aggregate or stay verdict-VO-only.

### 4.6 Sync — OpenProject Sub-Boundary

- Runtime owner: `shared/capabilities/sync/`
- Sub-boundary code: `shared/capabilities/sync/core/openproject_sync.py`
- No `core/domain/` directory.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | `shared/capabilities/sync/README.md` describes "context synchronization"; no ubiquitous-language section | No glossary for sync-side terms (mapping, lock, projection-side) |
| 2 | Aggregate root explicit | ✗ | `SyncMapping`, `SubtaskMapping` are anemic ORM models exposed via stores | No aggregate class enforces sync invariants (e.g. parent-subtask mapping consistency) |
| 3 | Aggregate consistency boundary | ✗ | `shared/capabilities/sync/core/openproject_sync.py:68-76` updates state across multiple stores in one sync run | No single transactional root for an OP-side sync operation |
| 4 | Value objects | ✗ | `shared/capabilities/sync/core/mapper.py` uses plain dicts for `WorkPackageData` | No value-object types; equality-by-value missing |
| 5 | Entities (identity-based) | ⚠ | `SyncMapping` keyed on primary id; ORM model leaks through port typed as `object | None` | No typed entity; identity is a plain int/str |
| 6 | Domain services | ⚠ | `mapper.py` and `shared/capabilities/sync/core/locking.py` `acquire_sync_lock` exist | Utilities, not invariant-enforcing domain services |
| 7 | Domain events | ✓ | `openproject_sync.py:61,104` stage events; `event_use_cases.py` collects and forwards | Pattern present; events flow through outbox with `trace_id` |
| 8 | State machine | ✗ | `shared/capabilities/sync/core/engine.py:74-87` compares `op_status == "failed" or feishu_status == "failed"`; no enum, no transition table | String-driven behavior (already documented as H4 / P1-2) |
| 9 | Repository pattern | ⚠ | `sync_ports.py` defines protocols; `db/sync_stores.py` implements; protocol return type is `object` (untyped) | ORM leaks via `object` return; ports do not declare typed return |
| 10 | Application service purity | ✓ | `openproject_sync.py` uses injected `BitableTablePort`, `OpenProjectWorkPackagePort`; no direct SDK calls | Pure; infrastructure delegated via ports |
| 11 | ACL for external systems | ✓ | `mapper.py` translates OP `work_package` → Feishu fields; `feishu_bitable_sync.py` orchestrates data flow | Bidirectional translation isolated to mapper |
| 12 | Context-map relationship | ✗ | `engine.py:12-18` comments on existence of two sub-boundaries | No formal context map; relationship to OpenProject upstream not classified |

**Summary**: 2 ✓ / 4 ⚠ / 6 ✗. High-priority remediation: introduce `SyncOperation` aggregate per sub-boundary with typed FSM (DDD-003).

### 4.7 Sync — Feishu Bitable Sub-Boundary

- Runtime owner: `shared/capabilities/sync/`
- Sub-boundary code: `shared/capabilities/sync/core/feishu_bitable_sync.py`
- No `core/domain/` directory.
- Known gap: `shared/capabilities/sync/core/engine.py:74-87` drives behavior
  off string-status comparisons (already documented as H4 / P1-2).

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | Implicit in `feishu_bitable_sync.py`; no glossary | No Feishu-specific context doc; vocabulary (record, subtask, parent) not formalized |
| 2 | Aggregate root explicit | ✗ | `SubtaskMapping` is anemic | No aggregate enforces parent-subtask invariants |
| 3 | Aggregate consistency boundary | ✗ | `shared/capabilities/sync/core/feishu_bitable_sync.py:60-65` writes directly; `progress.py` is stateless | Cross-record consistency not guarded |
| 4 | Value objects | ✗ | `record_data.subtask_status: str \| None` | No status value object |
| 5 | Entities (identity-based) | ⚠ | `feishu_record_id` is identity but stored on anemic model | Identity not promoted to a typed value object |
| 6 | Domain services | ✓ | `shared/capabilities/sync/core/progress.py` `calculate_progress_from_subtasks` encodes percentage-done logic | Pure domain logic isolated |
| 7 | Domain events | ✗ | `FeishuBitableSyncEngine` does not stage domain events; only logs sync completion | Missing event emission on progress update |
| 8 | State machine | ✗ | `record_data.subtask_status` untyped string; no validation | Implicit string comparison only |
| 9 | Repository pattern | ⚠ | `FeishuBitableSyncStore.upsert_subtask(status: str \| None)` leaks string type | Status parameter should be a domain enum |
| 10 | Application service purity | ✓ | `feishu_bitable_sync.py` uses `BitableTablePort`, `OpenProjectWorkPackagePort` only | Pure use case |
| 11 | ACL for external systems | ⚠ | `mapper.feishu_to_record_data` extracts fields; no dedicated antiseptic layer | ACL embedded in mapper; no published translation contract |
| 12 | Context-map relationship | ✗ | No spec of how Feishu status maps to OP percentageDone | Implicit translation; no published mapping |

**Summary**: 2 ✓ / 4 ⚠ / 6 ✗. Both Sync sub-boundaries share one outbox and one store (`sync_store.transaction()`) — needs split per DDD-014.

### 4.8 Interaction Gateway

- Runtime owner: `services/gateways/user_interaction/`
- Application facade landed: `core/application_facade.py` (recent commit
  `95de4b30b refactor(user-interaction): extract application facade`).
- No `core/domain/` directory. Gateways own gateway concerns, not
  product-domain records; dimensions 2, 3, 6, 7 graded as `n/a` unless
  the audit finds a domain record leaked into the gateway.

**Important boundary alert**: User Interaction owns `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress` tables (`services/gateways/user_interaction/models/*`). The naming prefix (`chat_agent_*`) signals these are product-domain tables of the `chat-agent` runtime, not gateway concerns. This is a `module-boundaries.md` §2.7 violation: gateways must not own product-domain records. Tracked as DDD-016.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `services/gateways/README.md` describes "Direct user interaction and Feishu webhook gateway" | Gateway concerns clear; ownership of product tables blurs boundary (see alert above) |
| 2 | Aggregate root explicit | ⚠ | `services/gateways/user_interaction/models/conversation.py:8` `ConversationHistory`, `models/card_operation.py:8` `CardOperation`, `models/daily_progress.py:8` `DailyProgress` are ORM-first records | Entities have IDs but no aggregate root pattern; in any case these belong to chat-agent, not gateway |
| 3 | Aggregate consistency boundary | ✗ | `ConversationHistory`, `CardOperation`, `DailyProgress` mutated independently | No transactional saga |
| 4 | Value objects | ✗ | No VOs; `webhook_intake.py:34` `FeishuWebhookMessage` is internal transfer dataclass, not reused as VO | Message metadata not modeled as immutable VO |
| 5 | Entities (identity-based) | ⚠ | All three records have id keys but no DDD entity pattern | Identity via primary key only |
| 6 | Domain services | ⚠ | `core/chat_service.py` coordinates conversation, tool execution, context compression; `core/daily_tasks.py` has morning/evening routines | Domain services exist but leak infrastructure (see dim 10) |
| 7 | Domain events | ✓ | `core/event_use_cases.py` handles events; `outbox_delivery_use_cases.py` publishes; `application_facade.py:79-86` `sync_trigger` event | Events flow through outbox |
| 8 | State machine | ⚠ | `models/card_operation.py:19` result `Literal["pending"|...]`; `models/daily_progress.py:17` status `Literal["pending"|...]`; no transition guards | States exist but no enforced transitions |
| 9 | Repository pattern | ✓ | `db/repository.py` `ConversationRepository`, `CardOperationRepository`, `DailyProgressRepository`; port in `core/chat_ports.py:18` | Port + adapter clean |
| 10 | Application service purity | ✗ | `core/chat_service.py:1` imports `ConversationEngine`, `ToolExecutionEvent` from `shared.infra.conversation_engine:9`; `core/tools.py` uses Anthropic SDK indirectly via shared | Infrastructure leaks into core; violates `architecture-principles.md` §4.1 |
| 11 | ACL for external systems | ⚠ | `core/webhook_intake.py:26` `FeishuUserDirectoryPort` Protocol; `core/feishu_cards.py` deprecated shim; `core/bitable_operations.py` uses `shared.integrations.feishu.bitable` | Partial port use; no explicit ACL translation |
| 12 | Context-map relationship | ✗ | No relationship classification to coordinator, requirement-manager, chat-agent | Implicit |

**Summary**: 3 ✓ / 4 ⚠ / 5 ✗. Two critical issues: (1) owns product tables that belong to `chat-agent` (DDD-016); (2) infrastructure leaks into `core/chat_service.py` (DDD-017).

### 4.9 Channel Gateway

- Runtime owner: `services/gateways/channel/`
- Application facade landed: `core/application_facade.py` (recent commit
  `50cde3f52 refactor(channel-gateway): extract application facade`).
- No `core/domain/` directory. Same gateway grading as 4.8.

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
| 8 | State machine | ⚠ | `models/event_outbox.py:22` status `Literal["pending"|...]` with `retry_count`, `last_error`; no transition enforcement | Outbox status without guarded transitions |
| 9 | Repository pattern | ✓ | `db/outbox_store.py` adapter; `outbox_ports.py:14` port; `db/repository.py` adapter | Clean separation |
| 10 | Application service purity | ✓ | `core/event_use_cases.py` depends only on adapter registry port; no SDK in use case | Pure |
| 11 | ACL for external systems | ⚠ | `service/agent.py` registers adapters from `shared.messaging.outbound.adapters`; no explicit translation in `core/` | Pass-through routing; ACL implicit in adapter shells |
| 12 | Context-map relationship | ✗ | No relationship classification to coordinator or upstream services | Implicit |

**Summary**: 4 ✓ / 2 ⚠ / 1 ✗ / 5 n/a. Cleanest gateway. Only remediation: state-machine guard for outbox (covered by cross-cutting DDD-006) and context-map classification (DDD-008).

### 4.10 Coordination / Orchestration

- Runtime owner: `services/orchestration/coordinator/`
- Application facade landed: `core/application_facade.py` (recent commit
  `a109d4320 refactor(coordinator): extract application facade`).
- No `core/domain/` directory. Coordinator owns dispatch decisions and a
  port-backed scratchpad / state store. Durable backing of scratchpad is
  the open question carried from `backend-architecture-analysis.md` §11.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `services/orchestration/README.md` "Orchestration agents coordinate work across runtime modules" | Coordinator concerns documented; no formal context charter |
| 2 | Aggregate root explicit | ⚠ | `core/models.py:7` `Decision` value-like; `db/models.py` `WorkflowState` (line 8), `DecisionRecord` (line 29) have identity but no root pattern | `Decision` lacks identity; `WorkflowState` has `workflow_id` but not marked root; no invariant enforcement |
| 3 | Aggregate consistency boundary | ✗ | `db/state_store.py:43-59` manually manages in-memory lists; no transactional scope; `state_ports.py` exposes `update_agent_state()` / `persist()` without atomic boundary | In-memory mutation; no aggregate invariants |
| 4 | Value objects | ⚠ | `core/models.py:7` `Decision` Pydantic BaseModel, mutable (no `frozen=True`) | No immutable VOs |
| 5 | Entities (identity-based) | ⚠ | `db/models.py` `AgentStateRecord` (`agent_id`), `WorkflowState` (`workflow_id`), `DecisionRecord` (`decision_id`) have identity but no lifecycle semantics | Identity via Pydantic field; no `NewType` |
| 6 | Domain services | ⚠ | `core/event_use_cases.py:35` `CoordinatorEventUseCase` crosses scratchpad + state_store + thinker via ports; `core/dispatcher.py:8` `decision_to_event()` pure function | EventUseCase crosses aggregate bounds without explicit domain service |
| 7 | Domain events | ✓ | `core/event_use_cases.py` handles classified events; `outbox_delivery_use_cases.py` publishes via EventBus | Typed events with outbox durability |
| 8 | State machine | ⚠ | `db/models.py` `DecisionRecord.status`, `WorkflowState.status` use `Literal[...]` but no transition guard | States exist; transitions implicit |
| 9 | Repository pattern | ✓ | `db/outbox_store.py:10` `SqlAlchemyCoordinatorEventOutboxStore`; `db/state_store.py:13` `CoordinatorStateStore` (in-memory adapter); ports `outbox_ports.py:8`, `state_ports.py:6` | Port + adapter; ORM isolated |
| 10 | Application service purity | ⚠ | `core/event_use_cases.py:35-56` depends on `CoordinatorThinker` callable (LLM); `application_facade.py:29` injects `thinker_provider` without SDK isolation | LLM coupling not wrapped in ACL |
| 11 | ACL for external systems | ✗ | No explicit ACL for LLM thinker invocation; thinker is a raw callable | Missing translation between LLM response and domain decision |
| 12 | Context-map relationship | ✗ | `core/dispatcher.py:8-65` hardcodes targets `"dev-agent"`, `"qa-agent"`, `"chat-agent"`; README silent on downstream contract | Dispatcher is hardcoded route, not published contract |

**Summary**: 3 ✓ / 6 ⚠ / 3 ✗. Critical durability question: `CoordinatorStateStore` is in-memory by default (`db/state_store.py:13` adapter); the port-backed design allows a durable adapter but none ships. Tracked as DDD-018.

### 4.11 Analytics / Reporting

- Runtime owner: `shared/capabilities/analysis/`
- No `core/domain/` directory.
- Known gap: direct reads from source-domain tables (P2-2). No projection
  layer.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | README describes risk detection and operating analytics | No glossary for risk, quality, report concepts |
| 2 | Aggregate root explicit | ✗ | `AnalysisReportLog` is anemic ORM; `MilestoneChecker` / `QualityEvaluator` are stateless utilities | No aggregate enforces report-generation invariants |
| 3 | Aggregate consistency boundary | ✗ | `shared/capabilities/analysis/core/daily_report.py:38` and `weekly_report.py` orchestrate independently; no transaction coordinator | Multi-step report flow lacks consistency boundary |
| 4 | Value objects | ✗ | Report content is plain dict; risk is dict with `"risk_level"` string | No value objects for Risk, Report, QualityAssessment |
| 5 | Entities (identity-based) | ⚠ | `AnalysisReportLog` has `id`; ORM model not wrapped | ORM leak; identity not promoted |
| 6 | Domain services | ✓ | `MilestoneChecker.check()`, `QualityEvaluator.evaluate_all()` encapsulate domain logic | Risk and quality assessment logic isolated |
| 7 | Domain events | ✓ | `event_use_cases.py:86-155` collects `SYNC_COMPLETED`, stages `REPORT_DAILY_GENERATED`, `ANALYSIS_RISK_DETECTED`, `ANALYSIS_QUALITY_EVALUATED` | Event-collection pattern present |
| 8 | State machine | ⚠ | `ReportLog.status` is plain string (`"pending"`, `"pushed"`); no enum | String status without typed transitions |
| 9 | Repository pattern | ⚠ | `ReportLogRepository` returns `ReportLog` ORM object | Repository returns ORM entity directly; no DTO mapping |
| 10 | Application service purity | ✗ | `daily_report.py:61-72` calls `self._bitable.list_all_records()` and `self._op.get_work_packages()` directly via ports | Use case orchestrates source-system reads; no projection between |
| 11 | ACL for external systems | ✗ | `daily_report.py:31,81` reads directly from `OpenProjectWorkPackagePort` (source domain) | No projection or anti-corruption layer (closes P2-2 when DDD-004 lands) |
| 12 | Context-map relationship | ✗ | No context map showing analysis depends on sync-produced tables or OP source | Dependencies implicit |

**Summary**: 2 ✓ / 4 ⚠ / 6 ✗. Cross-context pollution confirmed: Analysis reads OP and Feishu Bitable directly via integration ports, bypassing any projection.

### 4.12 Evolution

- Runtime owner: `shared/capabilities/evolution/` (+ historical
  `shared/evolution/` split per `module-boundaries.md` §2.10).
- No `core/domain/` directory.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ⚠ | README defines capability, not domain model | No glossary for proposal, tier, rollout, approval concepts |
| 2 | Aggregate root explicit | ✓ | `shared/control_plane/models.py` `EvolutionProposal` (owned by Control Plane but operated on here) carries approval/tier/rollout state; `shared/capabilities/evolution/core/proposal_approval_use_cases.py:67-100` validates approval requirement | Aggregate is in Control Plane; capability operates as application service on it (acceptable composition) |
| 3 | Aggregate consistency boundary | ✓ | `proposal_approval_use_cases.py:67-100` validates and writes audit transactionally | Approval gate guards rollout; audit trail maintained |
| 4 | Value objects | ⚠ | `EvolutionTier`, `ApprovalStatus` are enums; `EvolutionProposal` itself is mutable | Enums present; proposal fields not immutable value objects |
| 5 | Entities (identity-based) | ✓ | `EvolutionProposal` has `proposal_id`; `ApprovalGate` tracks `approval_id` | Identity-based entities with lifecycle |
| 6 | Domain services | ✓ | `ApprovalGate` (Control Plane), `skill_seed_store` (capability) encode workflow | Domain-specific logic isolated |
| 7 | Domain events | ✓ | `event_use_cases.py` collects and stages `AuditEvent`; outbox dispatches | Audit trail captured via events |
| 8 | State machine | ✓ | `EvolutionRolloutState`, `ApprovalStatus` enums define valid states; use cases check transitions | Typed state with explicit enum |
| 9 | Repository pattern | ✓ | `evolution_proposal_ports.py` defines `ControlPlaneEvolutionProposalStore`; implementations in `db/` hide ORM | Port-based; no ORM leak |
| 10 | Application service purity | ✓ | `proposal_approval_use_cases.py` accepts injected stores; no direct DB / SDK | Pure |
| 11 | ACL for external systems | ✓ | `analysis_ports.py`, `control_plane_ports.py` define external context contracts | Explicit ports for cross-context integration |
| 12 | Context-map relationship | ⚠ | `analysis_ports.py` exists; no formal context map | Ports present but relationship type (customer/supplier, conformist) not classified |

**Summary**: 8 ✓ / 4 ⚠ / 0 ✗. Most-mature capability. Remaining work is the package split between `shared/capabilities/evolution/` and `shared/evolution/` (DDD-005) and the context-map classification (DDD-008).

### 4.13 Identity / User

- Runtime owner: `shared/messaging/inbound/user_service.py`,
  `shared/db/user_store.py`.
- Foundation doc landed: [`identity-boundary.md`](./identity-boundary.md).
- Architecture-boundary test enforces port-based access:
  `tests/unit/test_architecture_boundaries.py::test_inbound_user_service_uses_identity_store_port`.

| # | Dimension | Status | Evidence (file:line) | Gap |
|---|-----------|--------|----------------------|-----|
| 1 | Bounded context defined | ✓ | `shared/core/identity_ports.py:10-30` defines `UserIdentityStore` Protocol; `identity-boundary.md` is the contract doc | Boundary defined |
| 2 | Aggregate root explicit | ⚠ | `shared/models/user.py:16` `User` is the aggregate root but has no invariant methods | Pydantic record without invariant enforcement |
| 3 | Aggregate consistency boundary | ⚠ | Platform-linking logic lives in `shared/messaging/inbound/user_service.py:216-228` `_set_platform_id`, not on `User` itself | Invariants belong on the aggregate, not in app service |
| 4 | Value objects | ✗ | Platform IDs (`feishu_open_id`, `wecom_user_id`, `web_user_id`) stored as raw strings; `Email`, `Phone` are primitives | No `PlatformId`, `Email`, `Phone` value objects with validation |
| 5 | Entities (identity-based) | ✓ | `User` has primary key id; mutable state (`last_active_at`); tracked by identity not value | Clear entity |
| 6 | Domain services | ⚠ | `UserService` lives in `shared/messaging/inbound/`, not in a domain location | Application + caching logic mixed with identity resolution |
| 7 | Domain events | ✗ | No `UserCreated`, `UserLinked`, `PlatformLinked` events published | Missing event emission on link/create |
| 8 | State machine | ✗ | No explicit transitions; user is passive data holder | No `unlinked → linked_{platform} → active` modeling |
| 9 | Repository pattern | ✓ | `UserRepository` implements port `UserIdentityStore`; per `identity-boundary.md` §2 single write path | Clean ACL boundary |
| 10 | Application service purity | ⚠ | `UserService.resolve_user()` mixes cache, DB queries, platform API calls, session management | Command/query separation missing |
| 11 | ACL for external systems | ⚠ | `UserService._create_or_link_user()` calls `adapter.get_user_email()` and `.get_user_name()` (lines 163-164); `User` model stores platform IDs directly | Should have `PlatformUserRef` value object so adapters translate to it |
| 12 | Context-map relationship | ⚠ | `identity-boundary.md` is the contract; no Brandolini relationship classification | Relationship to Integrations (upstream) and consuming runtimes (downstream) not labeled |

**Summary**: 3 ✓ / 7 ⚠ / 2 ✗. Strong on Identity boundary doc and repository pattern; weak on aggregate methods, value objects, and domain events.

### 4.14 Integration Plane (Adapter Library)

Integrations are not a bounded context. They are graded against the ACL
sub-rubric (§1.2 dimension 11 + the five ACL questions in the evidence
brief):

| Integration | Port file | Adapter file | ACL clean? | Leaks (file:line) |
|-------------|-----------|--------------|------------|-------------------|
| Feishu | `shared/core/integration_ports.py:102-134` (`FeishuMessengerPort`, `FeishuContactLookupPort`) | `shared/integrations/feishu/adapter.py:25` `FeishuChannelAdapter` | ✓ | Card builders imported into agents (`agents/qa_agent/adapters/feishu_cards.py`, `agents/pjm_agent/adapters/feishu_cards.py`) but wrapped in local renderer classes; `lark_oapi` SDK stays isolated in `client.py` |
| WeCom | `shared/core/integration_ports.py:45` (implicit via `ChannelMessage`) | `shared/integrations/wecom/adapter.py:21` `WecomChannelAdapter` | ⚠ | Agents import `WecomCardBuilder.from_channel_card()` directly; no protocol-based gateway for card composition |
| OpenProject | `shared/core/integration_ports.py:13-43` `OpenProjectWorkPackagePort` | (client only; no adapter shell) | ⚠ | `agents/pjm_agent/service/agent.py` imports `get_op_client` directly; port returns `dict[str, Any]` (leaks OpenProject schema shape) |
| GitLab | `shared/core/integration_ports.py:150-177` `GitLabMergeRequestPort`, `GitLabMergeRequestNotePort` | (client only) | ✓ | httpx client used through port; external schema isolated |
| OpenClaw | none | `shared/integrations/openclaw/adapter.py:23` `OpenClawChannelAdapter` | ⚠ | `client.send_request()` accepts raw `dict` params (lines 40-47); no schema translation |
| AgentForge | n/a | n/a | n/a | No `shared/integrations/agentforge/` module; AgentForge integration lives inside `dev_agent` adapters (audit follow-up) |

**Cross-cutting integration gaps** (key questions A–E from §1.2 dimension 11):

- A. **Port-typed access**: Feishu/WeCom expose ports but card builders bypass them via agent-local imports.
- B. **External-type leaks**: `OpenProjectWorkPackagePort` returns `dict[str, Any]`; OpenClaw client takes raw dicts.
- C. **Auth/token caches**: handled in `client.py` constructors (e.g. `feishu/client.py`); not exposed to shared code (✓).
- D. **Port contract coverage**: `integration_ports.py` covers 4 of 5 declared integrations; WeCom lacks a dedicated port; OpenClaw lacks any port.
- E. **Card builders**: Feishu/WeCom card builders are transitively imported by agents via local adapter wrappers; not a direct leak but circumvents layering.

**Summary**: Feishu and GitLab cleanest; OpenProject and OpenClaw need typed return values and proper port contracts; WeCom needs a dedicated port. Remediation packaged in DDD-013.

---

## 5. Cross-Cutting Findings

Patterns that appear across multiple contexts. These are the highest-
leverage opportunities because a single binding rule closes the pattern
everywhere at once.

### 5.1 Inconsistent `core/domain/` Adoption

Four of twelve contexts have a `core/domain/` subdirectory
(`requirement_manager`, `pjm_agent`, `qa_agent`, `dev_agent`). Control
Plane has both `domain/` and a top-level `agent_run_lifecycle.py`. The
remaining seven contexts have no `core/domain/` at all.

`architecture-principles.md` §1 lists Domain as a layer but does not
require every context to materialize the package. The audit recommends
making the package mandatory for every runtime that owns product
records (so: contexts 1–5, 6a, 6b, 8, 9, 10, 11) and explicitly excluded
for gateways (7a, 7b).

### 5.2 Lifecycle Module Location Drift

Three legitimate locations exist today:
- `core/<aggregate>_lifecycle.py` (Dev agent: `task_lifecycle.py`).
- `core/domain/lifecycle/` (Requirement, PJM, Dev — co-located with
  aggregate module).
- `shared/control_plane/agent_run_lifecycle.py` (top-level, not under
  `domain/`).

The intent in `migration-plan.md` §Stage 1 item 2 is `core/domain/lifecycle/`
for every aggregate. The audit recommends finishing the move in one PR
per runtime and adding an architecture-boundary test that forbids
`*_lifecycle.py` outside the canonical path.

### 5.3 QA Domain File Pluralization

`agents/qa_agent/core/domain/acceptance_verdict.py` and
`acceptance_verdicts.py` coexist. A pluralized duplicate is either an
incomplete rename or a leftover from a multi-aggregate split. The audit
flags this for inline triage in the next QA-touching PR — either
consolidate or rename one to a distinct concern (e.g. `acceptance_verdicts`
as a query model on top of `acceptance_verdict`).

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
`agents/dev_agent/core/`, and `shared/control_plane/`. PJM has an
explicit decomposition transaction port (`decomposition_ports.py`) but
not a generalized UoW. Requirement Manager, Sync, Analysis, Evolution,
Coordinator, and the gateways still rely on implicit session context
boundaries (P2-6 partial).

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
Analysis carries the same anti-pattern in `AnalysisReportLog.status`
(plain `"pending"` / `"pushed"` strings — see §4.11). Evolution is the
positive counter-example: `EvolutionRolloutState` and `ApprovalStatus`
are typed enums with transition checks (§4.12).

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

Integrations under `shared/integrations/` expose port interfaces, but
several leaks remain: OpenProject port returns `dict[str, Any]`,
OpenClaw takes raw dicts, WeCom lacks a dedicated port. Per-integration
leaks are tabulated in §4.14. Remediation packaged in DDD-013 and
DDD-022.

### 5.11 Ubiquitous Language Documentation Gap

Only the Control Plane has its vocabulary captured in
[`docs/overview/glossary.md`](../overview/glossary.md) and
[`docs/overview/product-model.md`](../overview/product-model.md).
Business agents and capabilities do not have per-context glossary
sections; the audit recommends one glossary subsection per context,
linked from each runtime's README — satisfying
`backend-evolution-plan.md` §5 item 3.

### 5.12 Gateway-Owned Product Tables (Boundary Violation)

User Interaction Gateway owns three product-domain tables prefixed
`chat_agent_*`. The table prefix itself signals the intended owner: a
`chat-agent` runtime, not a gateway. `module-boundaries.md` §2.7 states
"Gateway must not own product-domain records." The fix (DDD-016) is to
move the persistence and the related use cases into a `chat-agent`
capability, keeping only transport, webhook intake, and outbound card
delivery in the gateway. Channel Gateway is the reference for how a
clean gateway looks (§4.9).

### 5.13 Infrastructure Leaks Into Gateway and Coordinator Cores

Two contexts violate application-layer purity:

- User Interaction: `services/gateways/user_interaction/core/chat_service.py`
  imports `ConversationEngine` from `shared.infra.conversation_engine`.
- Coordinator: `services/orchestration/coordinator/core/event_use_cases.py`
  depends on `CoordinatorThinker` callable that wraps an LLM SDK call;
  no ACL between the LLM response and the typed `Decision`.

Both are fixable by introducing a port at the core/infra seam (DDD-017,
DDD-019). The pattern is already proven for LLM in
`shared.infra.llm_gateway`.

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
| DDD-001 | Control Plane | 2 / 8 | high | Move `agent_run_lifecycle.py` into `shared/control_plane/domain/lifecycle/`; promote AgentRun to an explicit aggregate class with FSM | 2 | DDD-006 |
| DDD-002 | All contexts | 1 | medium | Make `core/domain/` mandatory for every business + capability runtime; add architecture-boundary test that forbids `core/<x>_lifecycle.py` outside `core/domain/lifecycle/` | 1 | DDD-003 |
| DDD-003 | Sync (both sub-boundaries) | 2 / 3 / 8 | high | ✅ Seed landed `<DDD-003 PR>`. `shared/capabilities/sync/core/domain/sync_operation.py` exposes `SyncOperation` aggregate + `SyncOperationStatus` enum + `VALID_TRANSITIONS` FSM (PENDING → RUNNING → SUCCEEDED/PARTIAL_FAILURE/FAILED/SKIPPED) + `SyncSide` discriminator for the two sub-boundaries. `combine_side_statuses()` is the typed replacement for the H4 string-comparison in `engine.py:74-87`. 8 unit tests verify the FSM and the side-status combiner. Engine migration follows in dedicated PRs per sub-boundary (one OP, one Feishu Bitable) per `architecture-principles.md` §3. | 2 | DDD-014 (extraction) |
| DDD-004 | Analysis | 9 / 11 | high | Introduce explicit projection tables consumed by Analysis use cases; remove source-domain reads (closes P2-2) | 3 | C |
| DDD-005 | Evolution | 2 / 9 | medium | Promote `EvolutionProposal`, `EvolutionTrace`, `Reflection`, `Experiment` to explicit aggregates with FSMs; consolidate `shared/capabilities/evolution/` and `shared/evolution/` packages | 2 | — |
| DDD-006 | All business runtimes | 7 | medium | Standardize aggregate-raised domain events per `architecture-principles.md` §4.8; one PR per runtime (Control Plane, PJM, QA, Dev each emit aggregate events; Requirement already does) | 2 | — |
| DDD-007 | All contexts | 4 / 5 | medium | Introduce identifier value-object wrappers (`NewType`) for `work_item_id`, `run_id`, `approval_id`, `goal_id`, etc.; adopt one identifier per PR | 2 | — |
| DDD-008 | All product-owning runtimes | 12 | low | Extend `module-boundaries.md` §2.* with Brandolini-style context-map relationship row per context | 1 | — |
| DDD-009 | All product-owning runtimes | 1 | low | Add per-context ubiquitous-language glossary under `<runtime>/README.md`; link to `docs/overview/glossary.md` | 1 | — |
| DDD-010 | Coordinator, Requirement, Evolution | 3 / Application | medium | Extend explicit `UnitOfWork` adoption to remaining multi-aggregate write paths | 2 | — |
| DDD-011 | Cross-cutting | application | low | Add architecture-boundary test that `application_facade.py` depends on ports + use cases only (rule already documented in `architecture-principles.md` §4.7) | 1 | — |
| DDD-012 | QA | 4 | low | Resolve `acceptance_verdict.py` vs `acceptance_verdicts.py` pluralization in QA `core/domain/`; consolidate or rename to distinct concerns | 1 | — |
| DDD-013 | All adapters | 11 | medium | Audit each agent-local `adapters/` for direct external SDK type leaks; introduce port-typed return values where missing | 2 | — |
| DDD-014 | Sync runtime | service-boundary | high | Split Sync into two sub-capability runtimes (`sync-openproject`, `sync-feishu-bitable`); each with own outbox, store, runtime plugin; orchestrator endpoint joins via APIs | 4 | D |
| DDD-015 | Cross-cutting | testing | medium | Add domain-unit tests per new aggregate (one per aggregate + one per state machine) per `testing-strategy.md` §1 | 2 | — |
| DDD-016 | User Interaction Gateway | boundary | **high** | Move `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress` and their use cases into a `chat-agent` runtime (or chat-agent capability). Gateway retains transport + webhook intake only. Update `module-boundaries.md` §2.7. | 3 | — |
| DDD-017 | User Interaction Gateway | application purity | **high** | Wrap `shared.infra.conversation_engine` behind a port consumed by `core/chat_service.py`; remove infrastructure import from core | 2 | DDD-016 |
| DDD-018 | Coordinator | durability | **high** | Decide and document `CoordinatorStateStore` durable adapter (Postgres-backed or Redis-backed); add operator replay tooling; closes Phase 1 audit §11 open question 2 | 2 | — |
| DDD-019 | Coordinator | ACL | medium | Wrap LLM thinker callable behind a typed port that translates LLM responses into typed domain decisions (`ThinkerDecision` value object) | 2 | — |
| DDD-020 | Requirement Manager, Dev Agent | layering | medium | ✅ Landed `27a5a5d24`. Six callers migrated to `core/domain/lifecycle/`; both shims deleted; architecture-boundary tests updated to require the canonical path | 1 | done |
| DDD-021 | QA Agent | aggregate | medium | Decide whether `AcceptanceRun` is an aggregate (with FSM `REQUESTED → RUNNING → VERDICT_RENDERED → CLOSED`) or stays as a one-shot computation. If aggregate, model run-state transitions; if not, document the decision in QA README | 2 | — |
| DDD-022 | Integration Plane | port coverage | medium | Add a dedicated `WecomMessengerPort`; add `OpenClawIntegrationPort` (currently raw dict params); make `OpenProjectWorkPackagePort` return typed records instead of `dict[str, Any]` | 2 | DDD-013 |

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
| `AGENTS.md` | Part 3 Architecture Boundary Rules | Added rule 14: "Every product-owning runtime materializes an explicit `core/domain/` package per `architecture-principles.md` §1." (CLAUDE.md auto-syncs from AGENTS.md.) |

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
- `AGENTS.md` Part 3 (constitution).

When a remediation row in §6 lands, mark it complete in this document or
remove it from the table; do not let completed rows accumulate.
