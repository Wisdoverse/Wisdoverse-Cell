# Wisdoverse Cell Service Specification

Status: Draft v1

Purpose: define the implementation contract for Wisdoverse Cell as a
self-hosted control plane for AI-native company operations.

## Normative Language

The key words `MUST`, `MUST NOT`, `REQUIRED`, `SHOULD`, `SHOULD NOT`,
`RECOMMENDED`, `MAY`, and `OPTIONAL` in this document are to be interpreted as
described in RFC 2119.

`Implementation-defined` means the behavior is part of the implementation
contract, but this specification does not prescribe one universal policy.
Implementations MUST document the selected behavior.

## 1. Problem Statement

AI-native companies run work across chat tools, issue trackers, scripts,
documents, dashboards, and coding agents. Without a control plane, the operating
state is fragmented: goals live in documents, execution lives in transient
agent sessions, approvals live in chat, and audit evidence lives in logs.

Wisdoverse Cell provides a governed operating layer for that work. It models
company goals, agent roles, work items, agent runs, approvals, budgets, and
audit trails as first-class objects.

Important boundary:

- Wisdoverse Cell is a control plane and agent runtime, not a replacement for
  human ownership.
- External systems such as Feishu, WeCom, OpenProject, GitLab, or issue trackers
  remain their own systems of record unless an integration explicitly declares
  otherwise.
- A successful agent run MAY end in a handoff state requiring human approval,
  QA validation, or downstream execution.

## 2. Goals and Non-Goals

### 2.1 Goals

- Represent company work as durable goals, work items, agent runs, decisions,
  artifacts, budgets, and audit events.
- Run each agent as an independently deployable service with explicit runtime
  and integration boundaries.
- Support asynchronous collaboration through EventBus events and synchronous
  request/response through authenticated HTTP clients.
- Preserve traceability from user intent to agent execution, approval,
  generated artifacts, cost, and operational outcome.
- Enforce human-in-the-loop approval for sensitive finance, legal, customer, and
  technical decisions.
- Apply cost controls, fallback behavior, and circuit breakers around LLM calls.
- Expose operator-visible logs, metrics, traces, health checks, and failure
  evidence.
- Support controlled self-evolution through L1 skill optimization, L2
  architecture optimization, and L3 collaboration optimization.

### 2.2 Non-Goals

- A general-purpose no-code workflow builder.
- A fully autonomous company that bypasses human judgment.
- A single chatbot shell; chat is only one operator interface.
- A hosted multi-tenant SaaS contract in the source-available repository.
- Silent production deployment without secret management, webhook verification,
  approval gates, and observability.
- Direct in-process calls between independently deployed agents.

## 3. System Overview

### 3.1 Main Components

1. `Frontend Console`
   - Presents operator workflows, status, approvals, and product surfaces.
   - SHOULD use the shared API contracts instead of calling agent internals.

2. `Gateway`
   - Receives external HTTP and webhook traffic.
   - Verifies external platform signatures where applicable.
   - Routes internal calls to agent services through authenticated boundaries.
   - MUST use the Rust edge plane by default while preserving stable HTTP,
     gRPC, and EventBus contracts. The Go gateway is a legacy rollback
     implementation only. Rust gateway clients MUST be generated from the same
     protobuf contracts used by Python services.

3. `Agent Services`
   - Own business workflows such as requirement extraction, task decomposition,
     sync, analysis, QA, chat, development, and evolution.
   - MUST inherit the shared `BaseAgent` contract.
   - SHOULD use `create_agent_app()` for FastAPI wiring.

4. `Agent Runtime`
   - Owns lifecycle, event loop integration, plugins, health, middleware,
     tracing, and hardening hooks.
   - Extensions SHOULD be implemented as runtime plugins instead of modifying
     the core runtime.

5. `EventBus`
   - Provides asynchronous, at-least-once collaboration between agents.
   - Redis Streams is the default backend. NATS JetStream MAY be used through
     the shared EventBus protocol.

6. `LLM Gateway`
   - Centralizes model selection, retries, fallback, budget accounting, and
     circuit-breaker behavior for LLM calls.

7. `Storage`
   - PostgreSQL stores durable business state.
   - Redis stores event, cache, session, and budget data.
   - Milvus stores vector data for semantic retrieval.
   - NATS JetStream MAY provide durable event streaming.

8. `Integrations`
   - Platform adapters connect Feishu, WeCom, OpenProject, GitLab, and other
     external systems to the control plane.
   - Adapters MUST live behind shared port or client interfaces.
   - Platform-specific Feishu interactive-card builders and reusable renderers
     MUST live under `shared/integrations/feishu/cards/` and be injected into
     agent or gateway services through ports.

9. `Observability`
   - Emits structured logs, metrics, traces, and health signals for operators.
   - Runtime evidence SHOULD include trace IDs, agent IDs, work IDs, costs,
     errors, and artifact links.

### 3.2 Abstraction Levels

1. `Product Layer`
   - Goals, agent roles, work items, approvals, budgets, runs, artifacts, and
     audit history.

2. `Application Layer`
   - Agent services, API routes, command handlers, and scheduled jobs.

3. `Runtime Layer`
   - `BaseAgent`, `AgentRuntime`, `create_agent_app()`, plugins, health,
     middleware, and event-loop management.

4. `Integration Layer`
   - HTTP clients, webhook handlers, platform adapters, and messaging adapters.

5. `Infrastructure Layer`
   - PostgreSQL, Redis, NATS, Milvus, Traefik, metrics, tracing, and deployment
     assets.

### 3.3 Architecture Boundary Rules

Wisdoverse Cell uses Control Plane Architecture at repository level.

Backend architecture:

- Agent Service Boundary for runtime isolation.
- Strategic DDD for domain vocabulary and bounded contexts.
- Clean Architecture inside each agent service.
- Hexagonal Architecture for integrations and messaging.
- Rust edge plane plus Python agent plane. Rust SHOULD own gateway and future
  infrastructure workers; Python SHOULD continue to own business agents, LLM
  orchestration, and the control-plane ledger until explicit migration stages
  prove contract parity.

Frontend architecture:

- Strict Feature-Sliced Design.

Boundary rules:

1. Agents MUST NOT directly import another independently deployed agent.
2. Agents MUST communicate through HTTP clients or EventBus events.
3. External platforms MUST be accessed through ports and adapters.
4. `shared/control_plane` owns durable product objects: `Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Approval`, `Budget`, `Artifact`, and `AuditEvent`.
5. `shared/core` owns abstract ports and protocols.
6. `shared/integrations` owns platform adapters.
7. `shared/utils` MUST NOT contain business logic.
8. Frontend route files MUST stay thin.
9. Frontend domain data belongs to `entities`.
10. Frontend user actions belong to `features`.
11. Frontend composed operator surfaces belong to `widgets`.
12. All cross-boundary contracts MUST be documented in this specification, API docs, or the Event Catalog.

## 4. Core Domain Model

### 4.1 Entities

#### 4.1.1 Company Context

Top-level operating context for goals, agent roles, policies, budgets, and
integration credentials.

#### 4.1.2 Goal

A measurable business intent that work items and agent runs SHOULD trace back
to.

Fields:

- `id`
- `title`
- `owner`
- `success_metrics`
- `status`
- `parent_goal_id` (OPTIONAL)

#### 4.1.3 Agent Role

Job description, interaction contract, context contract, and execution boundary
for an agent. Implementations MUST distinguish organization-role agents,
business runtime agents, and support capability modules. CEO, CTO, CPO, COO,
and similar agents are `organization_role` records. Implemented business
runtime agents such as `requirement-manager`, `pjm-agent`, `qa-agent`, and
`dev-agent` live as root packages under `agents/`. Support services such as
sync, analysis, and evolution remain capability modules under
`shared/capabilities/` unless they explicitly become business runtime agents.
OpenProject synchronization and Feishu Bitable synchronization are separate
support capability boundaries. A deployment MAY keep the historical
`sync-agent` runtime identifier as a legacy alias, but the canonical capability
module identifier is `sync-module`. Implementations MUST NOT treat OpenProject
work-package sync and Feishu Bitable table sync as one undifferentiated domain.

Fields:

- `agent_id`
- `agent_name`
- `agent_kind` (`organization_role`, `business_runtime_agent`,
  `capability_module`, `integration_gateway`, or `system_worker`)
- `interaction_mode` (`direct`, `routed`, `internal`, or `none`)
- `context_sources`
- `responsibilities`
- `subscribed_events`
- `published_events`
- `permissions`
- `budget_policy`
- `escalation_policy`

Organization-role agents MAY be directly user-facing or routed through a
gateway. Root business runtime agents own business work outcomes behind their
service boundary. Support capability modules SHOULD be internally invoked by
role agents, root business agents, schedulers, or control-plane work items.
Integration gateways MAY be directly user-facing, but they SHOULD route intent
to a role agent or root business agent instead of owning business strategy.

#### 4.1.4 Work Item

Durable unit of company work.

Fields:

- `id`
- `source_system`
- `source_id`
- `title`
- `description`
- `owner`
- `priority`
- `status`
- `goal_id` (OPTIONAL)
- `dependencies`
- `artifact_links`

#### 4.1.5 Agent Run

One execution attempt by an agent.

Fields:

- `run_id`
- `agent_id`
- `work_item_id` (OPTIONAL)
- `trace_id`
- `status`
- `started_at`
- `finished_at` (OPTIONAL)
- `input_summary`
- `output_summary`
- `cost`
- `artifact_links`
- `error` (OPTIONAL)

#### 4.1.6 Approval

Human decision gate for sensitive work.

Fields:

- `approval_id`
- `category` (`finance`, `legal`, `customer`, `technical`, or extension value)
- `requested_by_agent`
- `subject`
- `context`
- `decision`
- `decided_by`
- `decided_at`
- `reason`

#### 4.1.7 Event

Immutable operational record used for asynchronous collaboration.

Fields:

- `event_id`
- `event_type`
- `timestamp`
- `source_agent`
- `payload`
- `schema_version`
- `metadata.trace_id`
- `metadata.retry_count`
- `metadata.correlation_id`

#### 4.1.8 Artifact

Output produced or updated by an agent, such as a PRD, report, QA result,
ticket, issue, merge request, code patch, or run walkthrough.

#### 4.1.9 Evolution Proposal

Controlled improvement proposal generated by the self-evolution system.

Fields:

- `proposal_id`
- `tier` (`L1`, `L2`, or `L3`)
- `scope`
- `evidence`
- `expected_benefit`
- `risk`
- `approval_state`
- `rollout_state`

## 5. Agent Runtime Contract

All production agent services MUST follow the shared runtime contract:

- Agents MUST inherit `BaseAgent`.
- Agents MUST expose stable `agent_id` values. Public display names MAY change,
  but runtime identifiers SHOULD remain stable unless a migration is planned.
- Agents MUST implement `handle_event()` and `handle_request()`.
- Agents SHOULD implement `startup()`, `shutdown()`, and `health_check()` when
  they own external resources.
- FastAPI entry points SHOULD use `create_agent_app()`.
- Runtime extensions SHOULD use `RuntimePlugin`.
- Scheduler jobs MUST call `runtime.agent`, not private raw-agent fields.
- Agents MUST NOT directly import another independently deployed agent service
  for business execution.

## 6. Event Contract

Events are the asynchronous language between agents.

Event requirements:

- `event_id` MUST be stable and SHOULD use the `evt_` prefix.
- `event_type` MUST use `{domain}.{action}` naming.
- `source_agent` MUST be the publishing agent ID.
- `payload` MUST be JSON-serializable.
- `schema_version` MUST be present.
- `metadata.trace_id` SHOULD be propagated across a workflow.
- Events MUST be treated as immutable after publication.

Delivery semantics:

- EventBus consumers MUST be idempotent because delivery is at least once.
- Long-running handlers SHOULD publish progress or completion events.
- Failed events SHOULD be observable through logs and dead-letter behavior.
- Event schemas SHOULD be documented before broad cross-agent use.

## 7. Synchronous Communication Contract

Synchronous inter-agent calls use HTTP REST through typed clients.

Requirements:

- Calls MUST cross service boundaries through HTTP or a documented protocol.
- Internal endpoints MUST verify `X-Internal-Key` unless explicitly public.
- Clients SHOULD set timeouts and classify network, auth, rate-limit, overload,
  and content-size failures.
- Callers SHOULD preserve `trace_id` through headers or request payloads.
- Direct Python object calls across agent services are prohibited.

## 8. Configuration and Secret Contract

Configuration is environment-driven and documented by `.env.example`.

Requirements:

- Secrets MUST NOT be committed.
- Secrets MUST NOT be logged.
- Production-like deployments MUST use explicit secrets for database, Redis,
  internal service keys, webhook verification, and LLM access.
- Empty or placeholder credentials MUST fail closed when they protect an
  externally reachable or sensitive path.
- Per-agent database and Redis isolation SHOULD be preserved for deployed
  services.
- Optional integrations MAY be disabled, but disabled integrations MUST degrade
  clearly and visibly.

## 9. Governance and Approval Contract

Human approval is REQUIRED before actions with sensitive impact.

Approval categories:

- Finance: pricing, purchasing, payment, or budget-changing actions.
- Legal: contract, compliance, privacy, or policy commitments.
- Customer: high-impact customer communication, escalation, or complaint
  handling.
- Technical: architecture changes, production deployment, destructive actions,
  or irreversible migration.
- Feishu Bitable schema mutations are technical-impacting changes and MUST
  verify a control-plane approval id before modifying table structure.

Approval requests MUST include enough context for a human to decide: proposed
action, reason, risk, affected resources, rollback or recovery note, and
artifact links where available.

## 10. LLM and Budget Contract

LLM access flows through the shared LLM Gateway.

Requirements:

- Agents SHOULD NOT call external LLM providers directly when shared gateway
  behavior is available.
- Prompt-too-large, rate-limit, overload, network, auth, and other failures
  SHOULD be classified into stable error categories.
- Retry behavior MUST be bounded.
- Model fallback MAY be used when the configured strategy allows it.
- Daily and monthly budget controls SHOULD be enforced before expensive work.
- PII and secrets MUST NOT be sent to LLM prompts unless explicitly approved by
  policy and protected by deployment controls.

## 11. Security and Privacy Contract

Security requirements:

- External webhook signatures MUST be verified when the platform supports
  verification.
- Prompt injection defenses SHOULD isolate untrusted user input from system
  instructions.
- Logs MUST avoid secrets, access tokens, webhook signatures, and raw PII.
- DSAR export and delete flows MUST require internal authentication.
- External TLS termination SHOULD happen at the reverse proxy or platform
  ingress.
- Internal traffic over untrusted networks MUST use additional transport
  protection such as mTLS or a service mesh.

## 12. Observability Contract

Operator-visible evidence is part of the product contract.

Requirements:

- Logs SHOULD be structured.
- Logs and metrics SHOULD include `trace_id`, `agent_id`, and relevant work IDs
  where available.
- Agent services SHOULD expose health and readiness signals through the shared
  app runtime.
- LLM usage SHOULD emit cost and token metrics.
- Long-running workflows SHOULD provide enough progress evidence to diagnose
  stalls, retries, and handoffs.
- Errors SHOULD include classification, retry decision, and operator action when
  possible.

## 13. Failure Model and Recovery

Failure classes:

- External platform failure.
- LLM provider failure.
- EventBus or storage failure.
- Configuration or secret failure.
- Agent handler error.
- Approval timeout or rejection.
- Budget exhaustion.

Recovery behavior:

- Transient failures SHOULD use bounded retry with backoff.
- Non-transient failures SHOULD fail visibly and preserve evidence.
- Replayed events MUST NOT create duplicate irreversible side effects.
- Circuit breakers SHOULD prevent cascading provider failures.
- Operators SHOULD be able to identify the last successful step from logs,
  events, or persisted run state.

## 14. Test and Validation Matrix

Required validation depends on the changed surface:

- Agent/runtime changes: `ruff check agents/ shared/` and focused Python tests.
- Event or schema changes: producer and consumer tests plus event catalog update.
- Gateway changes: Rust gateway tests, plus `go test ./...` in `gateway/` only
  when the legacy rollback path changes.
- Frontend changes: `make frontend-test` and lint/build checks where available.
- Documentation-only changes: `git diff --check` and link/path review.
- Security-sensitive changes: targeted tests for auth, signature verification,
  secret handling, and failure-close behavior.

## 15. Definition of Done

A change conforms to this specification when:

- It preserves explicit agent boundaries.
- It preserves or updates event and HTTP contracts.
- It keeps secrets and PII out of logs and prompts.
- It includes approval gates for sensitive actions.
- It emits enough operational evidence to debug failure.
- It updates relevant docs when behavior changes.
- It passes the validation appropriate to the changed surface.

## Appendix A. Reference Documents

- [README](./README.md)
- [Documentation index](./docs/INDEX.md)
- [Product model](./docs/overview/product-model.md)
- [Architecture overview](./docs/overview/architecture.md)
- [Agent development guide](./docs/guides/agent-development.md)
- [Operations guide](./docs/guides/operations.md)
- [Security policy](./SECURITY.md)
- [License](./LICENSE)
