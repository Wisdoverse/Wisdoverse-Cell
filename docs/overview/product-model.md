# Wisdoverse Cell Product Model

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
| Goal | Measurable business objective | `ControlPlaneRepository` goal ledger and `/api/v1/control-plane/goals` |
| Agent Role | Organization role, interaction mode, context sources, scope, policy, adapter, and budget | `AgentRole` records with `agent_kind`, `interaction_mode`, `context_sources`, frontend-created agents, adapter registry |
| Work Item | Durable unit of work | Control-plane work-item ledger, OpenProject work package, Feishu task/card, PRD item |
| Agent Run | One execution attempt with state, tools, logs, and cost | `ControlPlanePlugin`, `AgentRun`, wakeup runner, EventBus traces, QA checks |
| Approval | Human decision gate | Control-plane approval API, approval gates in high-risk flows, Feishu callbacks |
| Budget Policy | Spend and model/tool routing constraint | `BudgetGuard`, LLM gateway usage records, tool registry cost estimates |
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
| Workbench | `/[locale]/workflows` uses Feature-Sliced Design slices for goals, agents, approvals, budgets, runs, and timeline evidence | [API Reference](../guides/api-reference.md#control-plane-api), [Operations](../guides/operations.md#9-control-plane-operations) |
| Agent creation | Operators can create `AgentRole` records with kind, interaction mode, context sources, reporting line, adapter type/config, capabilities, responsibilities, subscribed/published events, permissions, and status | [API Reference](../guides/api-reference.md#post-apiv1control-planeagents) |
| Agent execution | Manual wakeup and heartbeat ticks create normal `AgentRun` records through the adapter registry | [Operations](../guides/operations.md#9-control-plane-operations) |
| Governance | Approval and budget gates append durable evidence before or during sensitive execution | [Event Catalog](../guides/event-catalog.md#30-control-plane-domain) |
| Evolution proposals | L1/L2/L3 self-evolution proposals are durable records with approval and rollout state; approval gates synchronize linked proposal state | [API Reference](../guides/api-reference.md#control-plane-api) |
| Audit | Timeline combines run, budget, approval, artifact, and audit events by trace or run | [API Reference](../guides/api-reference.md#control-plane-api) |

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

## Remaining Product Hardening

1. **Deployment-grade scheduler ownership.**
   Move heartbeat ticks from an operator endpoint to a production-owned scheduler
   with retry, timeout, and idempotency policy.

2. **Fine-grained permissions.**
   Extend role records into enforceable policy checks for agent creation,
   wakeups, budget changes, and approval resolution.

3. **Operational SLOs.**
   Add dashboards and alerts for run success rate, queue latency, approval age,
   budget burn, adapter failures, and event lag.

4. **Richer board controls.**
   Expand approve/reject into pause, resume, terminate, retry, rollback, and
   policy override flows.

5. **Company templates.**
   Export and import org structure, goals, agent roles, routines, and skills
   while scrubbing secrets.

6. **Long-term audit retention.**
   Define retention, redaction, and export policy for run logs, artifacts,
   approvals, and budget records.
