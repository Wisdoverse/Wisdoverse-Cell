# Module Boundaries

Last updated: 2026-10-01

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
- **Context-map relationships**: classification of upstream and downstream
  contexts using Brandolini terminology (customer/supplier, conformist,
  ACL, partnership, shared kernel, separate ways). The DDD compliance
  audit ([`ddd-compliance-audit.md`](./ddd-compliance-audit.md) §4)
  tracks per-context coverage.

When you add a new context, you must add a row to this document **and** to
`docs/guides/backend-boundaries.md` §3 in the same PR.

---

## 2. Catalog

### 2.1 Control Plane / Governance

- Runtime owner: `shared/control_plane/`
- Core responsibility: durable operating ledger of the company. The local
  glossary lives in [`shared/control_plane/README.md`](../../shared/control_plane/README.md).
- Business objects: `Company`, `Goal`, `AgentRole`, `WorkItem`, `AgentRun`,
  `Decision`, `ApprovalRequest`, `BudgetPolicy`, `BudgetUsage`, `Artifact`,
  `AuditEvent`, `EvolutionProposal`, `AgentPromptConfig`, company-template
  names, artifact-backed knowledge references and tombstones, execution
  leases/reservations, outcome acceptances, evolution evaluation reports and
  Control Plane release snapshots, and stateless
  `ControlPlaneDomainService` policies for cross-aggregate rules.
- Owned data: `control_plane_*` tables, including
  `control_plane_event_outbox` for aggregate-raised domain events. The eight
  product-governance tables added in the current migration remain Control
  Plane-owned; Evolution runtime release state is stored separately in its
  two `evolution_skill_*` tables.
- Exposed capabilities: `/api/v1/control-plane/*`, `/agent/request` wakeups,
  run-evidence APIs, budget enforcement, approval gates, and durable
  domain-event outbox staging.
- Outbound dependencies: runtime agents (writes runs, artifacts, audit);
  LLM Gateway (budget usage); gateways (approvals consumption); Evolution
  runtime through its signed HTTP release receiver.
- Boundary clarity: high (single owner); internal SQL ownership is now behind
  per-aggregate stores. The retired `repository.py` facade no longer exists;
  callers use store ports/factory adapters.
- Split fitness: must remain central. Do not extract.
- Context-map relationships: Open-Host Service to every runtime agent via `/api/v1/control-plane/*` and `/agent/request`. Published Language on `AgentRun`, `ApprovalRequest`, `BudgetPolicy`, `Artifact`, `AuditEvent` Pydantic records, `control_plane_event_outbox` integration-event rows, `ControlPlaneMetadata` JSON payload vocabulary, the `ControlPlaneStateMachine` lifecycle contract, and `ControlPlaneDomainService` policy naming for cross-aggregate rules. No upstream context (root authority).

The new `services/orchestration/control_plane_worker` profile is an HTTP-only
scheduler client. It calls the Control Plane heartbeat endpoint with operator
credentials; it has no ORM, migration, or table ownership. Its Compose profile
is opt-in and remains off by default.

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
- Context-map relationships: Anti-Corruption Layer to Interaction Gateway (meetings, chat), Feishu via `shared/integrations/feishu/`, and LLM Gateway extraction responses via `core/llm_extraction_response.py`. Customer/Supplier to PJM Agent (emits `requirement.*` integration events; PJM is the primary consumer). Conformist to Control Plane on `AgentRun`, `AuditEvent` Published Language.

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
- Context-map relationships: Customer/Supplier to Requirement Manager (consumes `requirement.*`) and Coordinator (consumes `decomposition.request`). Customer/Supplier to Dev Agent, QA Agent, and Sync (emits `decomposition.*` events). Anti-Corruption Layer to OpenProject (via Sync capability). Conformist to Control Plane.

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
- Context-map relationships: Customer/Supplier to PJM (consumes `decomposition.*`) and QA (consumes `qa.gate-failed` for retry). Customer/Supplier to Channel Gateway (emits `mr.*` events). Anti-Corruption Layer to GitLab and AgentForge via `agents/dev_agent/adapters/gitlab_client.py` and `agents/dev_agent/adapters/agentforge_client.py`. Conformist to Control Plane.

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
- Context-map relationships: Customer/Supplier to Dev Agent (consumes `code.committed`; emits `qa.acceptance-completed` and `qa.gate-failed`). Conformist to Control Plane. Anti-Corruption Layer pending for GitLab / OpenProject context resolution (DDD-013).

### 2.6 Sync / Projection (OpenProject ↔ Feishu Bitable)

- Runtime owner: `shared/capabilities/sync/`
- Core responsibility: project OpenProject ↔ Feishu Bitable; manage sync
  locks; propagate progress backflow.
- Business objects: `SyncMappingRecord`, `SubtaskMappingRecord`, `SyncLock`,
  `SyncLog`.
- Owned data: `sync_agent_*` tables.
- Exposed capabilities: sync trigger commands, sync status, sync events.
- Outbound dependencies: OpenProject, Feishu Bitable, PJM.
- Boundary clarity: medium. Two sub-boundaries live inside one runtime.
- Split fitness: split into two sub-capability runtimes (OpenProject side
  and Feishu Bitable side) before any full extraction.
- Context-map relationships: Customer/Supplier to PJM (receives decomposition handoff). Two sub-boundaries in Partnership today (shared `SyncStore`, shared outbox); target is Separate Ways per sub-runtime split (DDD-014). Anti-Corruption Layer to OpenProject and Feishu Bitable via integration ports. Conformist to Control Plane.

### 2.7 Interaction / Channel Gateway

- Runtime owner: `services/gateways/user_interaction/`,
  `services/gateways/channel/`; chat product runtime:
  `agents/chat_agent/`
- Core responsibility: receive inbound chat and webhook traffic; deliver
  outbound messages across channels.
- Business objects: gateway owns none; `ConversationHistory`,
  `CardOperation`, `DailyProgress` now belong to `agents/chat_agent/`.
- Owned data: user-interaction gateway owns transport/webhook state only;
  `chat_agent_*` belongs to `agents/chat_agent/`;
  `channel_gateway_event_outbox` belongs to Channel Gateway as gateway
  infrastructure and its retry/publish state is guarded by
  `ChannelGatewayOutboxLifecycle`.
- Exposed capabilities: chat REST and webhooks; outbound card operations;
  channel messages.
- Outbound dependencies: Feishu, WeCom, runtime agents (downstream of
  intent), Control Plane.
- Boundary clarity: high. ADR-0010 Steps 1-7 moved chat product runtime
  composition, persistence, scheduler, outbox dispatching, and HTTP API
  ownership to `agents/chat_agent/`; the gateway calls it through HTTP
  adapters and keeps only transport/webhook/card concerns.
- Split fitness: gateway boundary, not a business context. Keep as-is.
- Context-map relationships: Interaction Gateway is Anti-Corruption Layer
  to external users via Feishu / WeCom adapters (translates inbound
  platform messages into typed inbound events). Conformist to downstream
  Coordinator and chat-agent target on event payloads. Channel Gateway is
  Open-Host Service for `channel.message.outbound` emitted by any runtime,
  and Anti-Corruption Layer to external channels via `ChannelProviderACL` plus
  concrete adapters. DDD-016 is
  closed for the gateway code boundary; tactical chat aggregate modeling
  remains a separate chat-agent concern. Channel Gateway is Open-Host Service
  for outbound delivery events and must keep that relationship documented in
  its runtime README.

### 2.8 Coordination / Orchestration

- Runtime owner: `services/orchestration/coordinator/`
- Core responsibility: classify and dispatch cross-boundary events; keep
  scratchpad and short-term state for coordination decisions.
- Business objects: `CoordinatorEventOutbox`, scratchpad, agent-state store
  (port-backed), `CoordinatorWorkflowState`, `CoordinatorDispatchRoute`,
  `CoordinatorDispatchEnvelope`, `CoordinatorAgentStateRecord`,
  `CoordinatorDecisionRecord`, `CoordinatorScratchpadProjectionPlan`.
- Owned data: `coordinator_event_outbox`; durable `coordinator_agent_state`,
  `coordinator_workflow_state`, and `coordinator_pending_decision` are explicit
  when `COORDINATOR_DURABLE_STATE=true`. Scratchpad files are a derived
  reasoning projection after decision persistence, not the consistency source.
- Exposed capabilities: cross-boundary dispatch events.
- Outbound dependencies: all runtime agents, LLM (thinker), Control Plane.
- Boundary clarity: medium. Durable-state backing is explicit when
  `COORDINATOR_DURABLE_STATE=true`; workflow-state writes are validated by
  `core/domain/workflow_state.py`, dispatch target contracts are owned by
  `core/domain/dispatch.py`, scratchpad projection ordering is owned by
  `core/domain/scratchpad.py`, and persisted agent/decision identities are
  normalized by `core/domain/state_records.py`.
- Split fitness: not a candidate until durable-state and replay contracts
  are explicit.
- Context-map relationships: Open-Host Service to all runtime agents (consumes
  their events from the EventBus). Customer/Supplier to all runtime agents
  (emits dispatch decisions targeted to specific agents through
  `CoordinatorDispatchPolicy`). Anti-Corruption Layer to LLM via
  `CoordinatorThinkerPort` and `shared.infra.llm_gateway`; raw LLM responses
  are translated into typed `Decision` records before dispatch. Conformist to
  Control Plane.

### 2.9 Analytics / Reporting

- Runtime owner: `shared/capabilities/analysis/`
- Core responsibility: generate risk and operating reports from
  operational evidence and Analysis-owned projections.
- Business objects: `GeneratedAnalysisReport`, `AnalysisReportStats`,
  `WorkPackageProjection`, `SubtaskProgressProjection`,
  `AnalysisReportLogRecord`, `AnalysisFeishuTaskSnapshot`.
- Owned data: `analysis_agent_*`.
- Exposed capabilities: analysis REST API, analysis events.
- Outbound dependencies: Sync / PJM projections, Feishu Bitable task port for
  projection refresh and quality write-back, downstream report/risk/quality
  event consumers.
- Boundary clarity: high. OpenProject work-package and Feishu task reads for
  reports/risks now go through the Analysis-owned projection; Feishu Bitable
  task records are translated by `AnalysisFeishuTaskACL` into Analysis-owned
  snapshots at the projection boundary before report stats or formatting
  consume them.
- Split fitness: projection / read-model service candidate. Pre-condition is
  now met for report/risk reads; quality write-back remains an explicit
  platform port interaction.
- Context-map relationships: Customer/Supplier to Sync / PJM through the
  Analysis-owned work-package/subtask projection; Customer/Supplier to all
  reporting consumers (emits `analysis.report-*` and `analysis.risk-*`
  events); Anti-Corruption Layer to Feishu Bitable task records through the
  projection updater and `AnalysisFeishuTaskACL`; Conformist to Control Plane.

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
  `shared/capabilities/evolution/` is intentional — runtime primitives
  (trace collector, evaluator, skill optimizer, evolution guard, canary
  router, kill switch) live in `shared/evolution/`; the L2 capability
  service (analysis cycles + `EvolutionProposal` flow + approval gate)
  lives in `shared/capabilities/evolution/`. The split is documented in
  both READMEs and the DDD audit row DDD-005.
- Split fitness: keep guarded. Only split after approval/rollback contracts
  are hardened.
- Context-map relationships: Open-Host Service to all runtime agents on trace and reflection ingestion. Customer/Supplier to Control Plane on `EvolutionProposal` records (proposals surface via the approval gate). Anti-Corruption Layer to LLM via `shared.infra.llm_gateway`. Conformist to Control Plane on approval enforcement semantics.

### 2.11 Identity / User

- Runtime owner: `shared/db/user_store.py`,
  `shared/messaging/inbound/user_service.py`
- Core responsibility: platform user identity, contact value normalization,
  lookup, runtime context, and PII-safe identity event staging.
- Business objects: `User`, `PlatformUserRef`, `EmailAddress`, `PhoneNumber`,
  `IdentityState`, `Platform`, `IdentityEventOutbox`.
- Owned data: `users`, `identity_event_outbox`.
- Exposed capabilities: identity lookup through messaging inbound and
  shared user store; `identity.*` events through `identity_event_outbox`.
  No dedicated public API today.
- Outbound dependencies: every runtime that needs user context.
- Boundary clarity: high. Writes route through the `UserService` shell,
  core `IdentityResolutionUseCase`, `UserIdentityStore`, and aggregate
  methods; aggregate-raised events are mapped through
  `identity_event_from_domain_event()` and staged in the identity outbox.
  No public API yet.
- Split fitness: define the public boundary first. Splitting can wait
  until the API contract is durable.
- Context-map relationships: Anti-Corruption Layer to inbound platform identifiers (Feishu OpenID, WeCom UserID, Web User ID, OpenClaw user ID) via the inbound message path. Published Language for the `User` model, `UserIdentityStore`, and PII-safe `identity.*` events; downstream runtimes resolve through `UserIdentityStore.get_by_id` and never join the `users` table. See [`identity-boundary.md`](./identity-boundary.md) for the full contract.

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
- Context-map relationships: Anti-Corruption Layer for every external system (Feishu, WeCom, OpenProject, GitLab, AgentForge, OpenClaw). Translates external SDK types into domain-friendly types per integration ports in `shared/core/integration_ports.py`: `OpenProjectWorkPackagePort` returns `OpenProjectWorkPackage` TypedDict records, `WecomMessengerPort` is the named WeCom messaging port, and `OpenClawIntegrationPort` is the named OpenClaw messaging port (DDD-013, DDD-022).

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
7. Every product-owning context materializes an explicit `core/domain/`
   package per `architecture-principles.md` §1. Gateways are excluded
   (they own no product-domain records).
8. Gateways must not own product-domain records. If a table belongs to a
   product context, it lives in that runtime even if the gateway is the
   external touchpoint. See
   [`ddd-compliance-audit.md`](./ddd-compliance-audit.md) DDD-016 for the
   current open violation.

---

## 4. Maintenance

When the catalog changes:

- Update `docs/guides/backend-boundaries.md` §3 in the same PR.
- Update `docs/architecture/backend-target-architecture.md` §3 if a
  context's split fitness changes.
- Update `tests/unit/test_architecture_boundaries.py` to encode any new
  import rule.
