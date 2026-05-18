# Module Boundaries

Last updated: 2026-05-18

Status: Foundation document.

This document is the operator-and-engineer-readable catalog of bounded
contexts in the Wisdoverse Cell Python backend. It consolidates the
analysis in [Backend Architecture Analysis](./backend-architecture-analysis.md)
§3 and the design in [Backend Target Architecture](./backend-target-architecture.md)
§3.

Each context entry follows the same schema. Table ownership is the binding
contract — when in doubt, the row owner in
[`docs/guides/backend-boundaries.md`](../guides/backend-boundaries.md) §3 wins.

---

## 1. How to Read This Catalog

For each bounded context, the catalog lists:

- **Runtime owner**: the deployable runtime that owns the writes.
- **Core responsibility**: what the context exists to do.
- **Business objects**: aggregates and value objects this context owns.
- **Owned data**: tables (and other persistent state) the context writes.
- **Exposed capabilities**: APIs, events, and side effects other contexts
  may consume.
- **Outbound dependencies**: contexts and external systems this context
  depends on.
- **Boundary clarity**: how well the boundary is enforced today.
- **Split fitness**: whether the context is a candidate for runtime
  extraction; if so, the gating pre-conditions.

When you add a new context, you must add a row to this document **and** to
`docs/guides/backend-boundaries.md` §3 in the same PR.

---

## 2. Catalog

### 2.1 Control Plane / Governance

- Runtime owner: `shared/control_plane/`
- Core responsibility: durable operating ledger of the company.
- Business objects: `Company`, `Goal`, `AgentRole`, `WorkItem`, `AgentRun`,
  `Decision`, `ApprovalRequest`, `BudgetPolicy`, `BudgetUsage`, `Artifact`,
  `AuditEvent`, `EvolutionProposal`, `AgentPromptConfig`.
- Owned data: `control_plane_*` tables.
- Exposed capabilities: `/api/v1/control-plane/*`, `/agent/request` wakeups,
  run-evidence APIs, budget enforcement, approval gates.
- Outbound dependencies: runtime agents (writes runs, artifacts, audit);
  LLM Gateway (budget usage); gateways (approvals consumption).
- Boundary clarity: high (single owner); internal seam not yet structurally
  complete (`repository.py` is 902 LOC; needs P0-1 work).
- Split fitness: must remain central. Do not extract.

### 2.2 Requirement Management

- Runtime owner: `agents/requirement_manager/`
- Core responsibility: turn meetings and user intent into structured
  requirements; manage PRD flow and feedback learning.
- Business objects: `Meeting`, `Requirement`, `OpenQuestion`,
  `FeedbackRecord`, `ChatMessage`, `LlmUsage`.
- Owned data: `meetings`, `requirements`, `open_questions`,
  `feedback_records`, `llm_usage`, `chat_messages`,
  `requirement_event_outbox`.
- Exposed capabilities: requirement REST API, gRPC (`HealthCheck` and
  related), `requirement.*` events, Feishu card flow.
- Outbound dependencies: LLM Gateway, Feishu integration, Control Plane.
- Boundary clarity: high.
- Split fitness: future service candidate. Gating: per-runtime migrations,
  analytics projection, contract tests, OpenAPI snapshot.

### 2.3 Planning / PJM

- Runtime owner: `agents/pjm_agent/`
- Core responsibility: decompose work; prepare approvals; surface reports
  and alerts.
- Business objects: `DecompositionRecord`, `AlertLog`, `ConfigCache`.
- Owned data: `pjm_agent_*` tables.
- Exposed capabilities: decomposition REST API, PJM events, OpenProject
  handoff.
- Outbound dependencies: Requirement events, OpenProject via Sync,
  Control Plane (approvals, budgets).
- Boundary clarity: medium-high. Some capability coupling with Sync.
- Split fitness: candidate after decomposition is fully state-machine
  modeled and OpenProject contracts are explicit.

### 2.4 Delivery / Dev

- Runtime owner: `agents/dev_agent/`
- Core responsibility: run delivery tasks; execute workflows; hand off to
  MR and QA.
- Business objects: `DevTask`, `WorkflowLog`.
- Owned data: `dev_agent_*` tables.
- Exposed capabilities: delivery REST API, Dev events, MR handoff, QA
  request.
- Outbound dependencies: GitLab, AgentForge, Control Plane, QA.
- Boundary clarity: high.
- Split fitness: strong service candidate (long-running workflows). Gating:
  per-runtime migrations, projection for reporting, replay strategy.

### 2.5 Quality / QA

- Runtime owner: `agents/qa_agent/`
- Core responsibility: run acceptance; produce quality verdicts.
- Business objects: `AcceptanceRun`, `AcceptanceResult`.
- Owned data: `qa_acceptance_*`, `qa_agent_event_outbox`.
- Exposed capabilities: QA REST API, QA events, acceptance results.
- Outbound dependencies: Dev events, Control Plane.
- Boundary clarity: high. Idempotency contract already explicit.
- Split fitness: strong service candidate once trigger contracts and
  idempotency keys are documented as public.

### 2.6 Sync / Projection (OpenProject ↔ Feishu Bitable)

- Runtime owner: `shared/capabilities/sync/`
- Core responsibility: project OpenProject ↔ Feishu Bitable; manage sync
  locks; propagate progress backflow.
- Business objects: `SyncMapping`, `SubtaskMapping`, `SyncLock`, `SyncLog`.
- Owned data: `sync_agent_*` tables.
- Exposed capabilities: sync trigger commands, sync status, sync events.
- Outbound dependencies: OpenProject, Feishu Bitable, PJM.
- Boundary clarity: medium. Two sub-boundaries live inside one runtime.
- Split fitness: split into two sub-capability runtimes (OpenProject side
  and Feishu Bitable side) before any full extraction.

### 2.7 Interaction / Channel Gateway

- Runtime owner: `services/gateways/user_interaction/`,
  `services/gateways/channel/`
- Core responsibility: receive inbound chat and webhook traffic; deliver
  outbound messages across channels.
- Business objects: `ConversationHistory`, `CardOperation`, `DailyProgress`.
- Owned data: `chat_agent_*`, `channel_gateway_event_outbox`.
- Exposed capabilities: chat REST and webhooks; outbound card operations;
  channel messages.
- Outbound dependencies: Feishu, WeCom, runtime agents (downstream of
  intent), Control Plane.
- Boundary clarity: medium. Gateway must not own product-domain records.
- Split fitness: gateway boundary, not a business context. Keep as-is.

### 2.8 Coordination / Orchestration

- Runtime owner: `services/orchestration/coordinator/`
- Core responsibility: classify and dispatch cross-boundary events; keep
  scratchpad and short-term state for coordination decisions.
- Business objects: `CoordinatorEventOutbox`, scratchpad, agent-state store
  (port-backed).
- Owned data: `coordinator_event_outbox`; durable backing of scratchpad and
  state store needs confirmation (open question in Phase 1 analysis §11).
- Exposed capabilities: cross-boundary dispatch events.
- Outbound dependencies: all runtime agents, LLM (thinker), Control Plane.
- Boundary clarity: medium. Durable-state backing is implicit.
- Split fitness: not a candidate until durable-state and replay contracts
  are explicit.

### 2.9 Analytics / Reporting

- Runtime owner: `shared/capabilities/analysis/`
- Core responsibility: generate risk and operating reports from
  operational evidence.
- Business objects: `AnalysisReportLog`.
- Owned data: `analysis_agent_*`.
- Exposed capabilities: analysis REST API, analysis events.
- Outbound dependencies: requirement, PJM, Dev, QA tables (currently
  direct read). Must move to projections.
- Boundary clarity: low. Reads cross domain tables; no projection layer.
- Split fitness: projection / read-model service candidate. Pre-condition:
  stop direct source-table reads.

### 2.10 Evolution

- Runtime owner: `shared/capabilities/evolution/`, `shared/evolution/`
- Core responsibility: produce L1 (skill), L2 (architecture), L3
  (collaboration) evolution proposals; capture traces, reflections,
  experiments.
- Business objects: `EvolutionTrace`, `Reflection`, `Experiment`,
  `SkillConfig`, `CollaborationPattern`, `Memory`, `EvolutionProposal`.
- Owned data: `evolution_*` tables.
- Exposed capabilities: evolution REST API, evolution events; proposals
  surface via Control Plane.
- Outbound dependencies: Control Plane (proposals, approvals); runtime
  agents (traces).
- Boundary clarity: medium. Code split between `shared/evolution/` and
  `shared/capabilities/evolution/` historically.
- Split fitness: keep guarded. Only split after approval/rollback contracts
  are hardened.

### 2.11 Identity / User

- Runtime owner: `shared/db/user_store.py`,
  `shared/messaging/inbound/user_service.py`
- Core responsibility: platform user identity, lookup, runtime context.
- Business objects: `User`, `Platform`.
- Owned data: `users`.
- Exposed capabilities: identity lookup through messaging inbound and
  shared user store. No dedicated public API today.
- Outbound dependencies: every runtime that needs user context.
- Boundary clarity: low. Multiple read paths; no public API.
- Split fitness: define the public boundary first. Splitting can wait
  until the API contract is durable.

### 2.12 Integration Plane (Feishu, WeCom, OpenProject, GitLab, AgentForge)

- Runtime owner: `shared/integrations/`
- Core responsibility: external platform adapters and reusable presentation
  builders (Feishu cards).
- Business objects: none of its own.
- Owned data: token caches treated as infrastructure; no business data.
- Exposed capabilities: client classes, ports, routers, card builders for
  agents and gateways to consume.
- Outbound dependencies: external platforms.
- Boundary clarity: high. Centralized; no duplication.
- Split fitness: never a separately deployed business service. Treat as
  adapter library.

---

## 3. Cross-Context Rules

1. A context's writes go through its runtime owner only.
2. A context's reads come from its runtime owner or from a documented
   read-only projection. Direct cross-context table access is forbidden.
3. New tables ship with a row in `docs/guides/backend-boundaries.md` §3 and
   an entry here (or a clear "extends existing context" note).
4. New cross-context contracts ship as either:
   (a) a typed HTTP endpoint with versioned route and OpenAPI snapshot, or
   (b) an EventBus integration event with payload model and Event Catalog
   row.
5. Integration events are the preferred cross-context contract.
6. ORM `*Table` types must not appear in cross-context boundaries.

---

## 4. Maintenance

When the catalog changes:

- Update `docs/guides/backend-boundaries.md` §3 in the same PR.
- Update `docs/architecture/backend-target-architecture.md` §3 if a
  context's split fitness changes.
- Update `tests/unit/test_architecture_boundaries.py` to encode any new
  import rule.
