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
| Goal | Measurable business objective | Requirement Manager and PJM planning inputs |
| Agent Role | Job description, scope, policy, and budget | `BaseAgent`, agent configs, 26-agent model |
| Work Item | Durable unit of work | OpenProject work package, Feishu task/card, PRD item |
| Agent Run | One execution attempt with state, tools, logs, and cost | `AgentRuntime`, EventBus traces, QA checks |
| Approval | Human decision gate | Feishu card callbacks and human-in-the-loop policy |
| Budget Policy | Spend and model routing constraint | LLM budget settings and tiered model strategy |
| Activity Event | Immutable operational record | `Event`, Redis Streams, trace IDs |
| Artifact | Output produced by an agent | PRD, report, QA result, issue, code change |
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
| Goal alignment | Requirement extraction, PRD generation, PJM decomposition | Goal tree with task ancestry and metrics |
| Org chart | Named agent services and 26-agent company model | Role editor, reporting lines, scoped permissions |
| Task system | OpenProject and Feishu sync | Native work ledger with dependencies, blockers, labels, comments, and artifacts |
| Heartbeats | Schedulers and runtime hooks exist in agent services | Unified heartbeat queue with resumable agent runs |
| Governance | Human approval callbacks and internal service auth | Board console for approve, reject, pause, resume, terminate, and rollback |
| Cost control | Tiered LLM model routing and daily budget settings | Per-company, per-goal, and per-agent budgets with hard stops |
| Audit log | Immutable events, logs, traces, metrics | Operator-facing timeline with actor, reason, cost, and artifact links |
| Portability | Compose stack and environment templates | Export/import company templates with secret scrubbing |
| Self-evolution | `shared/evolution/` and `evolution_agent` | Governed improvement proposals with shadow mode and rollout history |

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

## Near-Term Roadmap

1. **Make goal lineage visible.**
   Each PRD, work package, QA result, and report should point back to a goal and owner.

2. **Promote agent roles into product data.**
   Move from documented agent responsibilities toward editable role, permission, policy, and budget records.

3. **Unify run history.**
   Capture agent execution state, tool calls, cost, logs, artifacts, and approval decisions in one operator-facing timeline.

4. **Add board controls.**
   Provide first-class approve, reject, pause, resume, terminate, and rollback actions.

5. **Add budget gates.**
   Enforce per-agent and per-goal limits before running expensive LLM work.

6. **Package company templates.**
   Export/import org structure, goals, agent roles, routines, and skills while scrubbing secrets.
