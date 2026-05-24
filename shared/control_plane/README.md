# Control Plane / Governance

The Control Plane is the durable operating ledger for Wisdoverse Cell. It owns
company-level goals, work queues, agent-role templates, runtime runs, human
approvals, budgets, artifacts, audit events, and evolution proposals. It is a
central governance context, not an agent runtime and not a support capability.

The public language for this context is exported through the Control Plane API,
store ports, Pydantic records in `models.py`, and domain aggregates under
`domain/`.

## Ubiquitous Language

| Term | Meaning | Local owner |
|------|---------|-------------|
| Company context | Tenant and operating-company boundary for all ledger records | `CompanyContext` aggregate in `domain/company_context.py` |
| Goal | Outcome to pursue, with owner, status, success metric, and optional parent goal | `Goal` aggregate in `domain/goal.py` |
| Work item | Operational unit of work tied to a goal, owner, priority, source, and lifecycle | `WorkItem` aggregate in `domain/work_item.py` |
| Agent role | Durable catalog record for organization-role agents, runtime agents, capabilities, gateways, and workers | `AgentRole` aggregate in `domain/agent_role.py` |
| Agent role status | Published lifecycle vocabulary for agent runnability and retirement | `AgentRoleStatus` in `domain/agent_role.py` |
| Agent prompt config | Mutable prompt/runtime instruction record for one agent inside one company | `AgentPromptConfig` aggregate in `domain/agent_prompt_config.py` |
| Agent run | Execution ledger entry for one runtime invocation, including trace, cost, result, and error evidence | `AgentRun` aggregate in `domain/agent_run.py` |
| Decision | Operator or agent decision with options, rationale, selected option, and lifecycle status | `Decision` aggregate in `domain/decision.py` |
| Approval request | Human-in-the-loop gate for finance, legal, customer, and technical actions | `ApprovalRequest` aggregate in `domain/approval_request.py` |
| Budget policy | Spending limit for a company, goal, agent, or work item over a budget period | `BudgetPolicy` aggregate in `domain/budget_policy.py` |
| Budget usage | Recorded model/tool spend tied to a budget policy, run, and trace | `BudgetUsage` aggregate in `domain/budget_usage.py` |
| Artifact | Durable evidence URI such as PRD, report, QA result, issue, merge request, patch, or run walkthrough | `Artifact` aggregate in `domain/artifact.py` |
| Audit event | Append-only operator evidence for mutations and domain-event collection | `AuditEvent` aggregate in `domain/audit_event.py` |
| Control Plane event outbox | Durable integration-event staging table for aggregate-raised Control Plane domain events | `control_plane_event_outbox` table through `event_outbox_store.py` |
| Evolution proposal | Governed proposal for L1 skill, L2 architecture, or L3 collaboration change | `EvolutionProposal` aggregate in `domain/evolution_proposal.py` |
| Adapter definition | Runtime adapter metadata exposed to operator surfaces and service composition | `AdapterDefinition` / `AdapterRegistry` |
| Agent wakeup adapter config | Domain interpretation of persisted `AgentRole.adapter_type` / `adapter_config` before HTTP, local-process, or built-in wakeup execution | `AgentWakeupAdapterConfig` value object in `domain/agent_wakeup_adapter.py` |
| Control Plane metadata | JSON-friendly metadata/config payload carried by ledger records without leaking raw dict rules into aggregates | `ControlPlaneMetadata` value object in `domain/metadata.py` |
| Control Plane state machine | Immutable lifecycle transition table used by Control Plane aggregates | `ControlPlaneStateMachine` value object in `domain/state_machine.py` |
| Control Plane domain service | Stateless policy for rules that span multiple Control Plane aggregate records without owning persistence | `ControlPlaneDomainService` in `domain/services.py`; `ApprovalResolutionPolicy`, `ExecutionLinkConsistencyPolicy`, and `BudgetPolicyConflictPolicy` |
| Control Plane aggregate catalog | Domain-owned source of truth for aggregate-root modules and required unit-test ownership | `CONTROL_PLANE_AGGREGATES` in `domain/aggregate_catalog.py` |

## Boundary Rules

- The Control Plane is the root authority for ledger records. Runtime agents
  create or update ledger state through Control Plane ports, APIs, or
  application use cases, not by writing `control_plane_*` tables directly.
- `shared/control_plane/models.py` defines the published record language at the
  API and persistence boundary. Aggregate behavior lives in `domain/` and use
  cases must call those aggregate methods before persistence when an invariant
  exists.
- `domain/aggregate_catalog.py` is the canonical Control Plane aggregate
  catalog. New product-owned ledger aggregates must be added there with their
  aggregate module and invariant unit-test path.
- Store ports live beside the context (`*_ports.py`), SQLAlchemy adapters live
  in `*_store.py`, and route files stay thin by delegating mutations to
  `*_use_cases.py`.
- `ControlPlaneUnitOfWork` is the explicit transaction boundary for command
  routes. Cross-aggregate follow-up writes must be named as
  `ControlPlaneDomainService` policies and applied through a separate local
  transaction or event handler instead of sharing the initiating aggregate's
  transaction.
- Aggregate-raised events are collected into the audit ledger through
  `domain_event_audit.py` and staged into `control_plane_event_outbox` through
  `domain_event_outbox.py` / `event_outbox_store.py`. External delivery remains
  a separate dispatcher concern; use cases must not publish Control Plane
  domain events directly to a broker.
- Runtime adapter configuration is translated through
  `AgentWakeupAdapterConfig` before the runner or scheduler makes adapter,
  heartbeat, timeout, command, or allowlist decisions. Raw `adapter_config`
  dictionaries must not be interpreted directly in runner/scheduler code.
- Metadata and config payloads are normalized through `ControlPlaneMetadata`
  before persistence or audit emission. Aggregates must not derive
  `metadata_keys`, provider config, or JSON detail payloads from raw
  dictionaries directly.
- Lifecycle aggregates use `ControlPlaneStateMachine` for transition
  membership, terminal-state derivation, and typed illegal-transition errors.
  New Control Plane lifecycle records must not implement ad hoc transition
  checks outside a domain-owned state machine.

## Context-Map Relationships

| Neighbor | Relationship | Contract |
|----------|--------------|----------|
| Runtime agents | Open-Host Service + Anti-Corruption Layer | Agents consume `/api/v1/control-plane/*`, `/agent/request`, store ports, and published records such as `AgentRun`, `WorkItem`, `Artifact`, and `AuditEvent`; persisted wakeup adapter configuration is translated through `AgentWakeupAdapterConfig` before any HTTP or local-process boundary is invoked |
| Requirement, PJM, Dev, QA, Chat, Sync, Analysis, Evolution | Customer/Supplier | Producing runtimes request work, approvals, runs, artifacts, and audits from the Control Plane while keeping their own product state local |
| Evolution capability | Customer/Supplier + Conformist | Evolution proposes changes, while Control Plane owns `EvolutionProposal`, approval state, rollout state, and audit |
| Identity / User | Separate Ways with identity references | Control Plane stores owner IDs and actor IDs, but identity owns the `users` table and platform identity mapping |
| LLM gateway and providers | Conformist + Anti-Corruption Layer via budget records | LLM usage must be evaluated through `BudgetGuard`, `BudgetAmount`, budget policy, and budget usage vocabulary before operator evidence is persisted |
| EventBus | Published Language | Control Plane records aggregate events into the audit ledger and stages them in `control_plane_event_outbox`. EventBus-facing integrations must publish Control Plane vocabulary such as budget usage or audit events and must not expose transport envelopes as Control Plane domain objects. |

## Aggregate Ownership

The canonical aggregate inventory is `CONTROL_PLANE_AGGREGATES` in
`domain/aggregate_catalog.py`; architecture tests derive the Control Plane
aggregate/test mapping from that catalog.

Current aggregate-owned invariants:

- `CompanyContext`: required company name, mission/metadata normalization,
  tenant-boundary creation/update events, and PII-safe audit summaries.
- `AgentPromptConfig`: prompt length, actor normalization, metadata-key audit
  summary, and no-raw-prompt audit event policy.
- `AgentRole`: role lifecycle, runnability policy, and terminal retirement
  policy.
- `AgentRun`: run lifecycle and terminal-state policy.
- `ApprovalRequest`: human approval/rejection lifecycle and approved-state
  predicate.
- `Artifact`: evidence title/URI normalization, execution-link materialization,
  and PII-safe creation audit summary.
- `BudgetPolicy`: scope identity rules, limit/threshold validation, lifecycle
  transitions, active-policy conflict vocabulary, and PII-safe audit summary.
- `BudgetUsage`: non-negative spend, token-count normalization, required
  model/tool identifier, immutable spend-recording event, and PII-safe audit
  summary.
- `AuditEvent`: required append target/action identity, actor normalization,
  idempotency-key normalization, and JSON-friendly detail normalization before
  audit rows enter the durable ledger.
- `ControlPlaneEventOutbox`: durable staging of aggregate-raised Control Plane
  domain events as integration events derived from audit rows.
- `EvolutionProposal`: rollout lifecycle and approval-gated promotion.
- `Goal`: goal lifecycle, cancel terminality, and completed-progress rule.
- `WorkItem`: work-item lifecycle, close-status policy, and run-result mapping.
- `Decision`: decision lifecycle and selected-option evidence.
- `ControlPlaneMetadata`: metadata/config key normalization, enum/date/sequence
  conversion into JSON-friendly values, immutable top-level access, and
  deterministic metadata-key summaries.
- `ControlPlaneStateMachine`: immutable transition-table normalization,
  terminal-state derivation, and shared illegal-transition enforcement for
  Control Plane lifecycle aggregates.
- `ControlPlaneDomainService`: stateless cross-aggregate policies, currently
  approval-to-proposal resolution, execution-link consistency, and active
  budget-policy conflict detection. Approval-to-proposal synchronization is
  applied by the EvolutionProposal-side handler after the approval transaction
  commits.
