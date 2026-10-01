# Wisdoverse Cell Product Model

Last updated: 2026-10-01

Delivery baseline: main at commit c387877 (2026-10-01). Implemented surfaces
are repository evidence. The [Product Roadmap](./roadmap.md) owns delivery
order and outcome acceptance; the
[Backend Migration Plan](../architecture/migration-plan.md) owns architecture
stages and deployment cutover gates. The roadmap records current CI evidence
separately from operator-flow and deployment acceptance.

Wisdoverse Cell should be understood as an AI-native company control plane. The codebase already contains agent services, a gateway, shared runtime infrastructure, event contracts, and operational integrations; the public product model connects those pieces into a clear operating system for company work.

The core product thesis is category clarity: agent companies need goals, org
charts, work queues, budgets, governance, heartbeats, and audit logs. Wisdoverse
Cell applies that model to its own stack and company-operating thesis.

---

## Design Principles

1. **Manage business intent, not only agent prompts.**
   Every piece of work should trace back to a company goal, a success metric, and the human or agent role that owns it.

2. **Agents have jobs, not just chat sessions.**
   Agents need roles, responsibilities, permissions, budgets, escalation rules, and observable output.

3. **Work is durable.**
   Tasks, comments, approvals, run logs, artifacts, and decisions should survive restarts and be queryable later.

4. **Humans are the board.**
   The system can execute repeatable work autonomously, but humans approve sensitive changes and can pause, override, or terminate agent work.

5. **Budgets are runtime policy.**
   Cost limits should be enforced before and during execution, not only reviewed after a bill arrives.

6. **The runtime is adapter-friendly.**
   Wisdoverse Cell should coordinate internal agents, coding agents, chat tools, SaaS integrations, and webhook bots through explicit boundaries.

7. **Improvement is built in.**
   L1 skill optimization, L2 architecture optimization, and L3 collaboration optimization are product capabilities, not only research ideas.

---

## Core Objects

| Object | Meaning | Existing Mapping |
|--------|---------|------------------|
| Company | Top-level operating context | Wisdoverse Cell deployment and tenant boundary |
| Mission | Long-term operating direction | README vision and PRD goals |
| Goal | Measurable business objective | Control-plane goal store and `/api/v1/control-plane/goals` |
| Agent Role | Organization role, interaction mode, context sources, scope, policy, adapter, and budget | `AgentRole` records with `agent_kind`, `interaction_mode`, `context_sources`, frontend-created agents, adapter registry |
| Work Item | Durable unit of work | Control-plane work-item ledger, OpenProject work package, Feishu task/card, PRD item |
| Agent Run | One execution attempt with state, tools, logs, and cost | `ControlPlanePlugin`, `AgentRun`, wakeup runner, EventBus traces, QA checks |
| Approval | Human decision gate | Control-plane approval API, approval gates in high-risk flows, Feishu callbacks |
| Budget Policy | Spend and model/tool routing constraint | `BudgetGuard`, `/api/v1/control-plane/budgets/policies`, LLM gateway usage records, tool registry cost estimates |
| Activity Event | Immutable operational record | Control-plane audit events, `Event`, Redis Streams, trace IDs |
| Artifact | Output produced by an agent | Control-plane artifacts, PRD, report, QA result, issue, code change |
| Company Template | Portable operating model | Planned export/import with secret scrubbing |

---

## Control Plane View

```text
Human Board
  -> Mission and policy
  -> Goals and budgets
  -> Agent org chart
  -> Work queue
  -> Agent runs
  -> Approvals and audit log
```

Wisdoverse Cell should make this flow visible in the product surface. The user should see why work exists, who owns it, what it costs, what state it is in, what decision is blocked, and what artifact was produced.

---

## Capability Map

| Capability | Implemented Foundation | Public Product Direction |
|------------|------------------------|--------------------------|
| Goal alignment | Requirement extraction, PRD generation, PJM decomposition, durable goals | Goal tree with richer metrics and progress rollups |
| Org chart | Persisted `AgentRole` definitions separate CEO/CTO-style organization roles, root business runtime agents, and support capability modules | Scoped permissions and reusable policy templates |
| Task system | OpenProject and Feishu sync plus native work-item ledger | Deeper dependency, blocker, label, comment, and artifact workflow |
| Heartbeats | Runtime hooks, manual control-plane wakeup, authenticated `/agent/request`, scheduler tick endpoint | Production scheduler ownership and run retry policies |
| Governance | Human approval callbacks, internal service auth, control-plane approval ledger | First-class pause, resume, terminate, and rollback controls |
| Cost control | Tiered LLM routing, daily budgets, `BudgetGuard`, LLM/tool usage records | Per-goal forecasts and team-level budget planning |
| Audit log | Immutable events, logs, traces, metrics, control-plane timeline | SLO dashboards and long-term audit retention policy |
| Portability | Compose stack and environment templates | Export/import company templates with secret scrubbing |
| Self-evolution | `shared/evolution/` and the evolution capability module | Governed improvement proposals with shadow mode and rollout history |

---

## Current Operator Surfaces

| Surface | Current State | Primary Docs |
|---------|---------------|--------------|
| Company context | `/api/v1/control-plane/companies` exposes durable company name, mission, metadata, and audit evidence | [API Reference](../guides/api-reference.md#control-plane-api) |
| Operator home | The command center highlights task focus, approvals, fleet state, and recent activity | [Home widget](../../frontend/src/widgets/home/ui/home-page-widget.tsx) |
| Workbench | `/[locale]/workflows` uses Feature-Sliced Design slices for goals, agents, approvals, budgets, runs, and timeline evidence | [API Reference](../guides/api-reference.md#control-plane-api), [Operations](../guides/operations.md#10-control-plane-operations) |
| Agent creation | Operators can create `AgentRole` records with kind, interaction mode, context sources, reporting line, adapter type/config, capabilities, responsibilities, subscribed/published events, permissions, and status | [API Reference](../guides/api-reference.md#control-plane-api) |
| Work item operations | `/api/v1/control-plane/work-items/{work_item_id}/activity`, `/run`, `/retry`, `/reassign`, `/block`, and `/close` make the work item the default operator command center | [API Reference](../guides/api-reference.md#control-plane-api), [Operations](../guides/operations.md#10-control-plane-operations) |
| Agent execution | Manual wakeup and heartbeat ticks create `AgentRun` records. HTTP and gated local-process paths execute work; `builtin` records a wakeup, and Codex/Claude entries share the local-process path. Real executor conformance remains pending. | [Operations](../guides/operations.md#10-control-plane-operations), [runner](../../shared/control_plane/agent_runner.py) |
| Governance | Approval and budget gates append durable evidence before or during sensitive execution | [Event Catalog](../guides/event-catalog.md#30-control-plane-domain) |
| Cost controls | Operators can manage scoped budget policies and inspect usage evidence | [API Reference](../guides/api-reference.md#control-plane-api), [Event Catalog](../guides/event-catalog.md#30-control-plane-domain) |
| Evolution proposals | L1/L2/L3 self-evolution proposals are durable records with approval and rollout state; approval gates synchronize linked proposal state | [API Reference](../guides/api-reference.md#control-plane-api) |
| Audit | Timeline combines run, budget, approval, artifact, and audit events by trace or run | [API Reference](../guides/api-reference.md#control-plane-api) |

## Operator Experience Gap and Direction

The home command center and work-item-scoped run, retry, reassign, block,
close and activity contracts are implemented. The next delivery should prove
that operators can complete a task and recover from failure across those
surfaces.

| Existing foundation | Next product outcome |
|---------------------|----------------------|
| Home task focus, pending approvals and activity | Make the next actionable task or decision clear and validate navigation to its working surface |
| Work-item commands and activity evidence | Validate create, assign, run, approve when required, inspect artifact and close as one flow |
| Durable runs, artifacts, decisions and audit records | Connect output, cost, status and the next action to the same work item |
| Retry, reassign and block commands | Demonstrate failed-run recovery, clear policy denial and safe handling of duplicate commands |
| Agent roles, budget policies and execution defaults | Introduce a synthetic first-success template once the core flow is accepted |

Acceptance covers the backend contract and the operator surface together,
including empty, loading, permission-denied, approval-required, timed-out and
failed-run states.

---

## What Wisdoverse Cell Is Not

| Not | Reason |
|-----|--------|
| A chatbot shell | Chat is one interface; company work needs goals, roles, budgets, tasks, and approvals. |
| A prompt folder | Prompts matter, but the product value is in operational control and durable state. |
| A single-agent demo | The architecture assumes independent agents with explicit runtime boundaries. |
| A generic workflow builder | The domain model is company operations, not drag-and-drop automation. |
| A replacement for human judgment | Humans remain responsible for values, tradeoffs, approvals, and strategic direction. |

---

## Delivery Priorities and Acceptance

The [Product Roadmap](./roadmap.md#delivery-order) is the active product backlog,
informed by the [Public Project Landscape](./public-project-landscape.md).
This table summarizes its order; detailed exit criteria live in that roadmap.
Responsible roles describe ownership; individual assignment and release dates
remain open. Public progress excludes personal contacts, internal deployment
links, credentials, customer data and raw production logs.

| Priority | Milestone | Responsible role | Dependency | Acceptance |
|----------|-----------|------------------|------------|------------|
| P0 / M0 | First repeatable business outcome | Product maintainer + runtime maintainer + QA | Existing commands, surfaces and execution gates | Real execution, QA/required approval, accepted artifact and goal-linked cost/audit evidence; failure and restart cases |
| P1 / M1 | Reliable recurring work and governance | Control Plane maintainer + operator | M0 and explicit scope/lifecycle policy | Atomic task ownership, scheduler recovery, enforced permissions, approval binding, concurrent budget policy, observability and audit retention |
| P1 / M2 | Executor and integration conformance | Runtime/integration maintainer + QA | M0; M1 before broader execution access | Certify existing HTTP/local execution and a scoped integration handoff before adding an executor/protocol |
| P1 / M3 | Measured self-evolution | Evolution maintainer + QA + approving role | M0 evaluation baseline and M1 controls | Connect proposal, comparative evidence, approved L1 experiment, promotion/rejection and verified rollback |
| P2 / M4 | Company reuse and knowledge | Product maintainer + Control Plane maintainer | Stable contracts, M1 permissions and retention | Synthetic template round trip with secret scrubbing; permission/provenance/retention tests for reusable knowledge |
| Release gate / R0 | Deployment acceptance | Runtime maintainer + release operator | Applicable product milestones and runtime-specific migration readiness | [S4.1–S4.3](../architecture/migration-plan.md#next-delivery-priorities) where extracting: migration rehearsal, two-week staging observation, replay and rollback; keep the bundled topology until split gates pass |

Dev S4.1 synthetic PostgreSQL engineering acceptance is complete
([evidence](../architecture/evidence/dev-migration-s41.md)); physical cutover
and deployment acceptance remain pending.

R0 preparation and the M0 task-flow work may proceed in parallel. Production
promotion remains gated; service extraction is not a prerequisite for a
trusted-development operator flow. Scheduled ownership, integrated evolution,
executor conformance and template export/import remain pending acceptance,
even though component records, endpoints and tests exist.

## Remaining Product Hardening

Use the linked Product Roadmap and the summary above as the active product
backlog. Code architecture closure does not close production operations or
operator-flow acceptance.
Future proposals should build on the existing work-item commands and state
which remaining milestone they complete, how it is verified, and what remains
pending.
