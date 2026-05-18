# Backend Boundaries and Data Ownership

Last updated: 2026-05-17

This guide is the backend boundary contract for the current modular-monolith
stage. Wisdoverse Cell is not a traditional DDD monolith and is not yet a fully
split microservice system. Runtime packages already run behind service
boundaries, but data ownership, API contracts, and event contracts must be
stable before any additional service extraction.

## 1. Boundary Rules

1. Business runtime agents under `agents/` own their own use cases, domain
   rules, and persistence model.
2. Capability modules under `shared/capabilities/` own support capabilities and
   must not become hidden business owners.
3. Gateway services under `services/gateways/` own inbound/outbound transport
   concerns and must not own durable product state except gateway-local
   interaction records.
4. `shared/control_plane/` owns durable operating-company records: companies,
   goals, work items, agent roles, agent runs, approvals, budgets, artifacts,
   decisions, audit events, and evolution proposals.
5. Cross-boundary writes go through HTTP/RPC/application methods or EventBus
   events. Do not mutate another boundary's table directly.
6. Cross-boundary reads should use API/RPC, events, or explicit read-only
   projections. Analysis code may consume projections; it must not become the
   write owner of source-domain tables.
7. Repository implementations are infrastructure adapters. Lifecycle rules,
   state transitions, history entries, and side effects belong in domain or
   application code.
8. External indexes and adapters such as Milvus, Feishu, OpenProject, GitLab,
   and AgentForge are infrastructure dependencies. Application services own
   best-effort cleanup, retries, and failure handling.
9. Domain events are internal facts. Integration events published through the
   EventBus are cross-boundary contracts and must be documented in the Event
   Catalog.
10. Future service extraction requires stable APIs/events, owned tables,
    idempotent commands, projection strategy, and deployment evidence.

## 2. Bounded Contexts

| Boundary | Runtime owner | Core responsibility | Service extraction posture |
|----------|---------------|---------------------|----------------------------|
| Control Plane / Governance | `shared/control_plane` | Goals, work items, roles, runs, approvals, budgets, artifacts, audit, evolution proposals | Keep central until APIs and budget/approval contracts are stable |
| Requirement | `agents/requirement_manager` | Meeting ingestion, requirement lifecycle, PRD support, feedback learning, requirement search index | Good future service; first keep tightening application/domain/infrastructure separation |
| Planning / PJM | `agents/pjm_agent` | Decomposition, approval preparation, reports, project alerts | Candidate after decomposition lifecycle and OpenProject contracts are explicit |
| Delivery / Dev | `agents/dev_agent` | Delivery tasks, workflow execution, MR handoff, QA request | Strong candidate for independent scaling because it owns long-running workflows |
| Quality / QA | `agents/qa_agent` | Acceptance runs and quality results | Strong candidate for independent execution once trigger contracts are stable |
| Sync / Integration Projection | `shared/capabilities/sync` | OpenProject to Feishu Bitable projection, Feishu progress backflow, sync locks | Keep as one capability for now; keep OpenProject and Feishu Bitable sub-boundaries separate inside core |
| Interaction / Channel | `services/gateways/user_interaction`, `services/gateways/channel` | Chat, webhooks, card operations, outbound delivery | Gateway boundary; do not let it own product-domain records |
| Coordination / Orchestration | `services/orchestration/coordinator` | Cross-boundary routing decisions, dispatch commands, workflow coordination state | Keep modular until durable state and operator replay contracts are explicit |
| Analytics / Reporting | `shared/capabilities/analysis` | Risk and report generation from read models or explicit source data | Projection/read-model service candidate; should not own source-domain writes |
| Evolution | `shared/capabilities/evolution`, `shared/evolution` | Skill, prompt, architecture, and collaboration optimization records | Keep guarded; split only after approval/rollback contracts are hardened |
| Identity / User | `shared/models/user.py`, `shared/db/repository.py`, `shared/messaging/inbound/user_service.py` | Platform user identity and user lookup | Keep as a shared boundary for now; route writes through the identity/user service path |

## 3. Table Ownership

| Tables | Owner boundary | Write contract | Read contract |
|--------|----------------|----------------|---------------|
| `control_plane_companies`, `control_plane_goals`, `control_plane_agent_roles`, `control_plane_agent_prompt_configs`, `control_plane_work_items`, `control_plane_agent_runs`, `control_plane_decisions`, `control_plane_approval_requests`, `control_plane_artifacts`, `control_plane_budget_policies`, `control_plane_budget_usage`, `control_plane_audit_events`, `control_plane_evolution_proposals` | Control Plane / Governance | `shared/control_plane` repository/API only | Control-plane API or explicit read-only reporting path |
| `meetings`, `requirements`, `open_questions`, `feedback_records`, `llm_usage`, `chat_messages`, `requirement_event_outbox` | Requirement | Requirement Manager application services and repositories | Requirement API, gRPC requirement service, EventBus events, or requirement read models |
| `pjm_agent_alert_logs`, `pjm_agent_config_cache`, `pjm_agent_decomposition_records`, `pjm_agent_event_outbox` | Planning / PJM | PJM agent application services and repositories | PJM API/events or reporting projections |
| `dev_agent_tasks`, `dev_agent_workflow_logs`, `dev_agent_event_outbox` | Delivery / Dev | Dev agent application services and repositories | Dev API/events or reporting projections |
| `qa_acceptance_runs`, `qa_acceptance_results`, `qa_agent_event_outbox` | Quality / QA | QA agent application services and repositories | QA API/events or reporting projections |
| `sync_agent_mappings`, `sync_agent_subtask_mappings`, `sync_agent_logs`, `sync_agent_locks`, `sync_agent_event_outbox` | Sync / Integration Projection | Sync capability only | Sync API/status endpoints or explicit projection reads |
| `chat_agent_conversation_histories`, `chat_agent_card_operations`, `chat_agent_daily_progress`, `chat_agent_event_outbox`, `channel_gateway_event_outbox` | Interaction / Channel | User interaction and channel gateways only | Gateway API/events or analytics projection |
| `coordinator_event_outbox` | Coordination / Orchestration | Coordinator runtime only | Coordinator events and operator replay tooling |
| `analysis_agent_report_logs`, `analysis_agent_event_outbox` | Analytics / Reporting | Analysis capability only | Analysis API/report endpoints and analysis events |
| `evolution_event_outbox`, `evolution_traces`, `evolution_skill_configs`, `evolution_reflections`, `evolution_experiments`, `evolution_memory`, `evolution_collaboration_patterns` | Evolution | Evolution capability and evolution stores only | Evolution API/control-plane proposal views and evolution events |
| `users` | Identity / User | Identity/user service path only; do not add new writes from unrelated modules | User lookup APIs or inbound messaging user service only |

## 4. API and Event Contracts

- Public HTTP routes stay versioned under `/api/v1` unless they are platform
  webhooks or internal runtime endpoints.
- HTTP route handlers should stay thin: request validation, auth/dependency
  injection, DTO conversion, error mapping, and response shaping only.
- Compatibility error codes use the `X-Error-Code` response header while
  preserving existing FastAPI `detail` strings until clients migrate to a
  structured error body.
- Application services own use-case orchestration, transaction boundaries,
  idempotency, feedback learning, external side effects, and EventBus
  publication.
- Event names, producers, consumers, and payload expectations live in
  `docs/guides/event-catalog.md`.
- New EventBus events require a payload model in `shared/schemas/event_payloads.py`
  and a row in the Event Catalog.
- Cross-boundary commands must include an idempotency strategy before they are
  used for retries or async delivery.
- `AgentRuntime` must route events returned by `handle_event()` through an
  agent-level `publish_event_via_outbox(event)` hook when the runtime boundary
  owns a durable outbox; direct EventBus publish is a legacy fallback only.

## 5. Data Evolution Rules

- A new table must be added to this guide in the same change that introduces the
  SQLAlchemy model or Alembic migration.
- A table owner change requires a migration plan, compatibility window, and
  read/write cutover evidence.
- Cross-service direct database access is not an acceptable service extraction
  strategy. Use API/RPC, EventBus events, or read-only projections.
- Distributed transactions are out of scope for the current architecture.
  Prefer one local transaction plus an outbox/projection workflow when a use
  case needs database writes and cross-boundary notification.
- Auxiliary stores such as Milvus are not sources of truth. Their cleanup is
  best-effort unless a use case explicitly requires a blocking consistency
  guarantee.

## 6. Current Known Gaps

| Gap | Risk | Next step |
|-----|------|-----------|
| `users` still lacks a dedicated public user/profile API boundary | Identity data can become shared mutable state if unrelated modules write directly | Keep writes behind the identity/user service path and make an explicit API ownership decision before expanding auth or profile writes |
| Requirement events, PJM decomposition API events, QA acceptance events, Sync lifecycle/decomposition handoff events, user-interaction sync trigger commands, PJM service notifications, Dev result-collection callback events, channel gateway events, analysis report/risk/quality events, coordinator dispatch/handoff events, and evolution proposal events now use durable outboxes and runtime dispatchers | Event delivery is retryable, but the outbox tables still share one database in the modular-monolith stage | Keep service extraction blocked until each runtime has deployment evidence and read-model/projection strategy |
| Some compatibility layers remain under `shared/services` and root `skills/` | New imports can reintroduce old coupling | Keep architecture tests blocking new runtime imports and retire shims when callers are gone |
| Analysis can drift into source-table reads | Reporting code can become implicit owner of other domains | Define read-only projections before expanding analytics |
| Error response shape is not yet uniform across all agent APIs | Operators and clients must parse inconsistent errors | Expand the compatibility `X-Error-Code` contract beyond Requirement APIs, then introduce versioned structured error bodies |
