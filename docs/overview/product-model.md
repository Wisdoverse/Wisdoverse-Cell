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
| Company Template | Portable operating model | Company-scoped export/import with secret scrubbing; imported roles begin paused |
| Knowledge Record | Versioned reference to company knowledge | Artifact-backed URI, immutable provenance, explicit reader-role ACL, retention and tombstone |

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
| Audit log | Immutable events, logs, traces, metrics, control-plane timeline, redacted company-scoped export, and default-off physical audit/knowledge retention with minimum 90-day age and bounded batches | Operational purge, restore, and retention sign-off; cleanup does not erase WAL or backup copies. Native runtime receipt-ledger retention is separate and pending |
| Portability | Compose stack and company template export/import with secret scrubbing and paused imported roles; one isolated PostgreSQL synthetic round trip accepted | Broader company reuse and role semantics across target environments |
| Knowledge | Artifact references with provenance, owner/role ACL, optimistic versions, expiry and delete tombstones; covered by one synthetic reuse acceptance | Target-environment retention and permission lifecycle acceptance |
| Self-evolution | `shared/evolution/`, fixed-case comparative evaluations, signed release commands and approval-gated rollout states; one synthetic 50-pair L1 loop with regression rollback accepted | Measured shadow/canary/promotion/rollback against live runtime behavior |

---

## Current Operator Surfaces

| Surface | Current State | Primary Docs |
|---------|---------------|--------------|
| Company context | `/api/v1/control-plane/companies` exposes durable company name, mission, metadata, and audit evidence | [API Reference](../guides/api-reference.md#control-plane-api) |
| Operator home | The command center highlights task focus, approvals, fleet state, and recent activity | [Home widget](../../frontend/src/widgets/home/ui/home-page-widget.tsx) |
| Workbench | `/[locale]/workflows` uses Feature-Sliced Design slices for goals, agents, approvals, budgets, runs, and timeline evidence | [API Reference](../guides/api-reference.md#control-plane-api), [Operations](../guides/operations.md#10-control-plane-operations) |
| Agent creation | Operators can create `AgentRole` records with kind, interaction mode, context sources, reporting line, adapter type/config, capabilities, responsibilities, subscribed/published events, permissions, and status | [API Reference](../guides/api-reference.md#control-plane-api) |
| Work item operations | `/api/v1/control-plane/work-items/{work_item_id}/activity`, `/run`, `/retry`, `/reassign`, `/block`, and `/close` make the work item the default operator command center | [API Reference](../guides/api-reference.md#control-plane-api), [Operations](../guides/operations.md#10-control-plane-operations) |
| Agent execution | Manual wakeup and heartbeat ticks create `AgentRun` records. A default-off versioned native HTTP receiver dispatches allowlisted actions in four runtimes with owner-local durable receipts; synthetic four-runtime handler conformance and PostgreSQL replay/concurrency are verified. A separate synthetic browser acceptance uses a restricted local process and reads run/artifact/cost links through the real operator proxy. | [API Reference](../guides/api-reference.md#native-executor-api), [Native Executor Runbook](../runbooks/native-executor.md), [engineering evidence](../evidence/native-executor-engineering-2026-10-01.md), [browser acceptance](../../frontend/e2e/control-plane-real-api.spec.ts) |
| Governance | Approval and budget gates append durable evidence before or during sensitive execution | [Event Catalog](../guides/event-catalog.md#30-control-plane-domain) |
| Cost controls | Operators can manage scoped budget policies and inspect usage evidence | [API Reference](../guides/api-reference.md#control-plane-api), [Event Catalog](../guides/event-catalog.md#30-control-plane-domain) |
| Evolution proposals | L1/L2/L3 self-evolution proposals are durable records with approval and rollout state; approval gates synchronize linked proposal state | [API Reference](../guides/api-reference.md#control-plane-api) |
| Audit | Timeline combines run, budget, approval, artifact, and audit events by trace or run | [API Reference](../guides/api-reference.md#control-plane-api) |
| Company portability | Company-scoped template export/import; imported runtime roles remain paused pending review; one PostgreSQL synthetic round trip and knowledge lifecycle acceptance | [Company template use cases](../../shared/control_plane/company_template_use_cases.py), [acceptance case](../../tests/integration/test_company_reuse_acceptance.py) |
| Reusable knowledge | Artifact-backed references; same-company readers need owner or explicit role grant; delete leaves a tombstone | [Knowledge routes](../../shared/control_plane/api_routes/knowledge.py) |
| Audit export and retention | Redacted, exact-company and date-bounded paginated export; default-off 90-day physical retention is bounded to 1,000-row batches and preserves pending/pinned evidence with compact tombstones | [Audit export route](../../shared/control_plane/api_routes/audit_export.py), [retention route](../../shared/control_plane/api_routes/retention.py), [seven PostgreSQL cases](../../tests/integration/test_physical_retention.py) |

## Operator Experience Gap and Direction

The home command center and work-item-scoped run, retry, reassign, block,
close and activity contracts are implemented. One real-browser case now
completes create, assignment, real backend execution, artifact inspection,
acceptance and closure through the authenticated operator proxy, with persisted
goal/work/run/artifact/cost/audit links. Its company and local-process output
are synthetic; it does not prove the native QA or four-runtime business path,
failure/restart recovery, or a live provider/platform flow.

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
| P0 / M0 | First repeatable business outcome | Product maintainer + runtime maintainer + QA | Existing commands, surfaces and execution gates | One synthetic real-browser create-to-close case is verified; still require the native business path, QA/required approval, failure and restart cases, and target runtime evidence |
| P1 / M1 | Reliable recurring work and governance | Control Plane maintainer + operator | M0 and explicit scope/lifecycle policy | Two synthetic PostgreSQL cases cover recurring claims/restart and governance denial; observed pilot, selected-runtime recovery and operational evidence remain open |
| P1 / M2 | Executor and integration conformance | Runtime/integration maintainer + QA | M0; M1 before broader execution access | Native receiver conformance is synthetic; one default-off Requirement Manager handoff test verifies existing OpenProject IDs and Control Plane links through read-only HTTP, with atomic mapping/outbox. Live platform write/sync and PJM/Dev/QA delivery remain open |
| P1 / M3 | Measured self-evolution | Evolution maintainer + QA + approving role | M0 evaluation baseline and M1 controls | One PostgreSQL loop exercises 50 fixed paired synthetic cases and L1 rollback; live model/provider measurement remains open |
| P2 / M4 | Company reuse and knowledge | Product maintainer + Control Plane maintainer | Stable contracts, M1 permissions and retention | One synthetic PostgreSQL template and knowledge lifecycle round trip passed; broader target-environment reuse and retention acceptance remain open |
| Release gate / R0 | Deployment acceptance | Runtime maintainer + release operator | Applicable product milestones and runtime-specific migration readiness | [S4.1–S4.3](../architecture/migration-plan.md#next-delivery-priorities) where extracting: migration rehearsal, at least 14 days and 1,000 matching staging requests, replay and rollback; keep the bundled topology until split gates pass |

Seven PostgreSQL tests now cover the default-off audit/knowledge retention path;
native runtime receipt-ledger retention still needs its own policy and
acceptance. Dev S4.1 synthetic PostgreSQL engineering acceptance is complete
([evidence](../architecture/evidence/dev-migration-s41.md)); physical cutover
and deployment acceptance remain pending. S4.1 remains rehearsal-only; no
production per-runtime split has been accepted.

R0 preparation and the M0 task-flow work may proceed in parallel. Production
promotion remains gated; service extraction is not a prerequisite for a
trusted-development operator flow. Recurring-work pilot, live model/provider
measurement, live provider/platform integration, QA-agent delivery, operational
retention/purge sign-off, and R0 remain pending. The handoff test verifies a
default-off mapping and outbox only; the real-browser test verifies one
synthetic restricted-process outcome. Native executor handler conformance
remains at the synthetic engineering boundary; a receipt does not mean a
four-runtime delivery outcome was accepted. S4.1's historical three-table
cutover proof does not cover the additional native executor ledger.

## Remaining Product Hardening

Use the linked Product Roadmap and the summary above as the active product
backlog. Code architecture closure does not close production operations or
operator-flow acceptance.
Future proposals should build on the existing work-item commands and state
which remaining milestone they complete, how it is verified, and what remains
pending.

For the current implementation evidence and operational boundaries, see the
[engineering receipt](../evidence/product-roadmap-engineering-2026-10-01.md)
and [product governance runbook](../runbooks/product-governance.md). Both keep
completed local validation and explicitly open milestone acceptance.
