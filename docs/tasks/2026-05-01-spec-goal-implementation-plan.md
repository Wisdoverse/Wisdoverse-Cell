# SPEC Goal Implementation Plan (2026-05-01)

Source contract: [SPEC.md](../../SPEC.md)

## Current Distance To Goal

This repository has a strong agent-runtime foundation, but it is not yet a
complete implementation of the `SPEC.md` control-plane contract.

Approximate status:

- Foundation readiness: 82% to 85%
- End-to-end SPEC behavior: 62% to 66%

The remaining work is not mainly about adding more agents. The gap is the
durable company control-plane ledger: goals, work items, agent runs, decisions,
artifacts, budgets, approvals, and audit events must become shared product data
with enforced runtime gates and operator-visible evidence.

## Evidence Snapshot

Implemented foundations:

- Shared control-plane models, tables, repository, migration, runtime plugin,
  approval gate, and budget guard:
  `shared/control_plane/`, `shared/app/plugins/control_plane.py`,
  `migrations/versions/20260501_control_plane_ledger.py`
- Agent interface and stable runtime contract:
  `shared/schemas/agent.py`, `shared/app/factory.py`, `shared/app/runtime.py`
- Event contract and typed event constants:
  `shared/schemas/event.py`, `shared/schemas/event_payloads.py`
- Async EventBus and DLQ/error handling:
  `shared/infra/event_bus.py`, `shared/infra/nats_event_bus.py`
- Synchronous HTTP client with internal key propagation:
  `shared/infra/agent_client.py`, `shared/middleware/internal_auth.py`
- LLM gateway with error taxonomy, retry, fallback, circuit breaker, and cost
  primitives:
  `shared/infra/llm_gateway.py`, `shared/infra/llm_errors.py`,
  `shared/infra/circuit_breaker.py`
- Evolution system with trace collection, kill switch, canary, and L3 approval:
  `shared/evolution/`, `agents/evolution_agent/`
- Frontend shell for agents, monitor, dashboard, and approvals:
  `frontend/src/app/[locale]/(app)/`, `frontend/src/lib/api/`
- Frontend agent management is now a Feature-Sliced Design vertical slice:
  `frontend/src/entities/agent/`, `frontend/src/features/agent-create/`,
  `frontend/src/widgets/agent-fleet/`, `frontend/src/widgets/agent-detail/`
- Frontend-created agent definitions now have a shared wakeup path through
  `POST /api/v1/control-plane/agents/{agent_id}/wake`, adapter execution in
  `shared/control_plane/agent_runner.py`, and a deployed-service request
  boundary at `POST /agent/request`.
- Product model documentation already names the target control-plane objects:
  `docs/overview/product-model.md`

Main gaps:

- First control-plane APIs are exposed for runs, approvals, budget usage, audit
  events, combined timeline, goals, and work items.
- Approval behavior is now wired through shared control-plane records for
  high-risk dev workflows, PJM decomposition writes, and evolution proposals.
  The remaining gap is exposing approval queues/actions through a unified API.
- LLM cost controls now have a durable budget guard path, and LLM usage is
  merged back into `AgentRun` when calls execute inside a control-plane event
  context.
- Runtime traces and audit logs now have a first queryable timeline API; the
  remaining gap is artifact coverage and frontend integration.
- Frontend approval and monitor views exist, but they are not yet wired to the
  new control-plane API contract.
- Agent identity/configuration is now partially decoupled from code: operators
  can create control-plane agent definitions from the frontend and store role,
  reporting line, adapter type/config, capabilities, responsibilities, and
  status. Operators can manually wake those definitions through explicit
  adapters. The remaining gap is production heartbeat scheduling, adapter
  registry hardening and broader failure evidence.

## Goal Gap Matrix

| SPEC Goal | Current Status | Gap | Priority |
|-----------|----------------|-----|----------|
| Durable goals, work items, runs, decisions, artifacts, budgets, audit events | Shared ledger, first APIs, and FSD workbench present | Need export/import hardening | P0 |
| Independently deployable agents with explicit runtime boundaries | Mostly present | Need conformance tests and no direct service import checks | P1 |
| Async EventBus plus authenticated HTTP clients | Mostly present | Need trace/work IDs standardized across control-plane events | P1 |
| Traceability from intent to execution, approval, artifacts, cost, outcome | Goal/work/run/evidence workbench present | Need broader failure evidence and trace consistency | P0 |
| HITL approval for sensitive actions | Core agent wiring, API, evidence visibility, and durable action UI present | Need deeper approval-history filters | P0 |
| Cost controls, fallback, circuit breakers around LLM calls | Stronger foundation | Need run-ledger linkage and high-cost tool gates | P0 |
| Operator-visible logs, metrics, traces, health, failure evidence | Backend evidence API and first UI timeline present | Need richer failure detail and log links | P1 |
| Controlled L1/L2/L3 self-evolution | Medium foundation | Need approval/audit linkage to control-plane proposals | P1 |
| Frontend-created agent definitions and org relationships | Manual wakeup path present | Need production heartbeat scheduler and adapter hardening | P0 |

## Implementation Strategy

### Phase 1: Control-Plane Ledger

Create the shared durable data contract first.

Owned scope:

- `shared/control_plane/models.py`
- `shared/control_plane/tables.py`
- `shared/control_plane/repository.py`
- `shared/control_plane/database.py`
- `shared/control_plane/__init__.py`
- `migrations/versions/<next>_control_plane_ledger.py`
- `tests/control_plane/`

Objects:

- `CompanyContext`
- `Goal`
- `AgentRole`
- `WorkItem`
- `AgentRun`
- `Decision`
- `ApprovalRequest`
- `Artifact`
- `BudgetPolicy`
- `BudgetUsage`
- `AuditEvent`
- `EvolutionProposal`

Acceptance:

- All IDs use stable prefixes aligned with `shared/utils/id_generator.py`.
- Tables include `trace_id`, `company_id`, timestamps, status, actor, and JSON
  evidence fields where needed.
- Repository tests cover create, read, status transition, audit append, and
  idempotency on repeated event ingestion.
- Alembic can create the ledger tables from a clean database.

### Phase 2: Runtime Trace Integration

Wire the ledger into execution.

Owned scope:

- Add a `ControlPlanePlugin` or equivalent runtime integration.
- Record `AgentRun` lifecycle around `handle_event()` and `handle_request()`.
- Persist `AuditEvent` for event handling, failures, LLM calls, and tool calls.
- Propagate `trace_id`, `goal_id`, `work_item_id`, and `agent_run_id`.

Acceptance:

- [x] One inbound event produces a queryable run record.
- [x] Failure path stores error category, error message, and last successful step.
- [x] Event publication links output events back to the source run.
- [x] `create_agent_app()` exposes control-plane recording as explicit opt-in.
- [x] `ControlPlanePlugin` can be enabled in production agent entry points after
      migrations are applied.
- [x] LLM cost details are merged into the run ledger for control-plane event
      execution.
- [x] Tool cost details are merged into the run ledger.

### Phase 3: Approval And Budget Enforcement

Make governance a runtime policy, not only UI behavior.

Owned scope:

- Shared approval service and repository methods.
- Approval request API for pending, approve, reject, timeout, and evidence view.
- Budget policy checks before expensive LLM/tool work.
- Integration points for `dev_agent`, `pjm_agent`, `evolution_agent`, and LLM
  gateway.

Acceptance:

- [x] Finance, legal, customer, and technical categories are first-class enums.
- [x] Approval requests include action, reason, risk, affected resources, rollback
  note, artifact links, requester, and trace IDs.
- [x] Sensitive actions cannot proceed without an approved record in the shared
      `ApprovalGate`.
- [x] Per-request and daily/monthly budget gates can fail closed in the shared
      `BudgetGuard`.
- [x] `ApprovalGate` is wired into `dev_agent`, `pjm_agent`, and
      `evolution_agent` sensitive actions.
- [x] `BudgetGuard` is wired into LLM gateway behind an explicit enforcement
      flag.
- [x] `BudgetGuard` is wired into high-cost tool entry points.

### Phase 4: Operator Console API And UI

Turn the ledger into the product surface.

Owned scope:

- Backend API for goals, work items, runs, decisions, artifacts, approvals,
  budgets, audit events, and activity timeline.
- Frontend workbench views for:
  - goals and work queue
  - agent runs
  - approvals
  - budget usage
  - audit timeline
  - failure evidence

Acceptance:

- [x] Operator can create an agent definition from the Next.js console.
- [x] Agent definitions store role, title, domain, reports-to, adapter type,
      adapter config, capabilities, responsibilities, permissions, and status.
- [x] Agent fleet/detail routes read frontend-created definitions through the
      control-plane API.
- [x] Operator can manually wake a frontend-created agent definition through
      explicit adapter config and inspect the resulting run record.
- [x] New agent frontend code follows Feature-Sliced Design boundaries:
      entity API/model/ui, creation feature, fleet/detail widgets, thin routes.
- [x] Operator can start from a goal and inspect linked work, runs, decisions,
      approvals, artifacts, costs, and failures.
- [x] Backend timeline can merge run, decision, artifact, approval, budget, and
      audit evidence by run or trace.
- [x] Approval actions mutate durable backend state and refresh visible evidence.
- UI remains an operational console, not a marketing page.

### Phase 5: Governed Self-Evolution And Portability

Close the remaining SPEC loop.

Owned scope:

- Link L1/L2/L3 proposals into `EvolutionProposal` and `ApprovalRequest`.
- Store rollout state, canary result, shadow evidence, and rollback history.
- Add export/import of company templates with secret scrubbing.

Acceptance:

- No evolution proposal can promote without approval and audit evidence.
- Operators can inspect why a skill, architecture, or collaboration change was
  proposed, approved, rolled out, or rejected.

## Mandatory TODO Checklist

### Design

- [x] Finalize control-plane object schemas and status transitions.
- [x] Decide whether the first public API lives in a new `control_plane` agent
      service or in an existing API service.
- [x] Define API paths consumed by the Next.js console.
- [x] Define frontend slice boundaries for agent entity, create-agent feature,
      and agent fleet/detail widgets.
- [x] Define first control-plane event names for agent roles, wakeup, runs,
      budgets, artifacts, and audit records.

### Logic

- [x] Implement Pydantic models, SQLAlchemy tables, and repository methods.
- [x] Add Alembic migration for the control-plane ledger.
- [x] Wire runtime run/audit recording.
- [x] Enforce approval gates for sensitive actions.
- [x] Enforce budget gates before LLM work when
      `CONTROL_PLANE_LLM_BUDGET_ENFORCED=true`.
- [x] Add frontend-created `AgentRole` definitions with adapter config and
      reporting-line fields.
- [x] Add a shared wakeup runner for persisted `AgentRole` definitions using
      `builtin`, `http`, and explicitly enabled local process adapters.
- [x] Add authenticated `/agent/request` as the generic deployed-service
      request boundary for agents created through `create_agent_app()`.
- [x] Enforce budget gates before expensive tool work.

### Events

- [x] Add typed payloads for initial `agent.wakeup-*` and `agent_run.*`
      control-plane events.
- [x] Add typed payloads for initial `goal.*` and `work_item.*` events.
- [x] Add typed payloads for initial `decision.*` and `artifact.*` events.
- [x] Add typed payloads for `approval.*`, `budget.*`, and `audit.*`.
- [x] Update event catalog with producers, consumers, and idempotency keys.
- [x] Ensure all emitted control-plane events propagate `trace_id`.

### Test

- [x] Unit-test domain model validation.
- [x] Unit-test repository transitions and idempotency.
- [x] Test migration upgrade on a clean database.
- [x] Test runtime plugin success and failure paths.
- [x] Test approval and budget fail-closed behavior.
- [x] Test control-plane agent definition create/list/status API.
- [x] Test control-plane goal/work-item create/list/status API.
- [x] Test control-plane decision/artifact APIs and backend E2E lineage.
- [x] Test control-plane agent wakeup API, run output events, and local adapter
      fail-closed behavior.
- [x] Type-check and lint the Feature-Sliced frontend agent slices.
- [x] Test runtime plugin timeout and DLQ paths.
- [x] Add frontend API/component tests for operator surfaces.

### Docs

- [x] Keep `SPEC.md` as the root contract.
- [x] Update `docs/overview/product-model.md` when schema names become stable.
- [x] Update `docs/guides/event-catalog.md` for new event types.
- [x] Update `docs/guides/api-reference.md` for control-plane APIs.
- [x] Update `docs/guides/operations.md` for ledger, migration, and monitoring
      runbooks.

## Recommended MR Split

1. MR A: control-plane models, tables, repository, migration, and tests.
2. MR B: runtime plugin for run/audit recording and trace propagation.
3. MR C: approval and budget enforcement service.
4. MR D: backend API for operator console.
5. MR E: Feature-Sliced frontend operator console pages and timeline views.
6. MR F: evolution proposal governance and template export/import.

## First Implementation Batch

MR A is now implemented locally. It gives every later step a stable persistence
contract and keeps risk contained.

Initial branch tasks:

- [x] Create `shared/control_plane/`.
- [x] Add Pydantic enums and models for the SPEC core objects.
- [x] Add SQLAlchemy tables with indexes on `company_id`, `trace_id`, status, and
  creation time.
- [x] Add a repository with append-only audit helpers.
- [x] Add migration and focused tests.

Validation commands for MR A:

```bash
ruff check shared/ tests/
pytest tests/control_plane
git diff --check
```

## Second Implementation Batch

MR B/C foundations are partially implemented locally.

Completed tasks:

- [x] Add `ControlPlanePlugin` opt-in to `create_agent_app()`.
- [x] Pass `CONTROL_PLANE_ENABLED` and `CONTROL_PLANE_COMPANY_ID` through all
  current agent FastAPI entry points.
- [x] Add `CONTROL_PLANE_LLM_BUDGET_ENFORCED`, budget scope, and budget period
  config.
- [x] Check durable budget policies before LLM provider calls when enforcement
  is enabled.
- [x] Record actual LLM usage back to `BudgetUsage` after successful calls.
- [x] Propagate runtime `AgentRun` context into LLMGateway without changing each
  agent call site.
- [x] Add actual LLM cost/token totals onto the matching `AgentRun`.
- [x] Add focused LLM budget enforcement tests.
- [x] Add `CONTROL_PLANE_APPROVAL_ENFORCED` and shared `ApprovalGateService`.
- [x] Create/resolve control-plane approvals for high-risk dev workflows,
  PJM decomposition writes, and evolution proposals.
- [x] Add internal control-plane API routes for runs, approvals, budget usage,
  audit events, and combined timeline.
- [x] Add internal control-plane API routes for goals and work items.
- [x] Add internal control-plane API routes for decisions and artifacts.
- [x] Include run, decision, and artifact evidence in the timeline API.
- [x] Add internal control-plane API routes for frontend-created agent
  definitions.
- [x] Add Feature-Sliced frontend slices for agent entity, create-agent feature,
  fleet widget, and detail widget.
- [x] Fleet UI combines built-in agents with persisted control-plane agent
  definitions.
- [x] Add manual wakeup for frontend-created agent definitions from the detail
  view.
- [x] Add authenticated `/agent/request` to every `create_agent_app()` service.
- [x] Add the control-plane wakeup runner and local-adapter fail-closed switch.
- [x] Add Feature-Sliced control-plane workbench route for goals, work queue,
      runs, decisions, artifacts, approvals, budget usage, and timeline evidence.
- [x] Add durable approval approve/reject actions in the control-plane workbench
      and refresh the linked evidence after mutation.

Next tasks:

- [x] Add production heartbeat/scheduler execution for frontend-created agent
      definitions.
- [x] Add adapter registry and allowlist policy before enabling local adapters
      in production.

Validation commands for MR B/C foundation:

```bash
ruff check shared/config.py shared/infra/llm_gateway.py agents/*/app/main.py tests/unit/test_llm_control_plane_budget.py
pytest tests/unit/test_llm_control_plane_budget.py tests/unit/test_llm_cost_cap.py tests/unit/test_llm_audit.py
git diff --check
```
