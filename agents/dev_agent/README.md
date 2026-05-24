# Dev Agent

Real business runtime agent for delivery execution. Picks up decomposed
tasks, runs the AgentForge workflow, hands the result off as a GitLab
merge request, and triggers QA acceptance.

Canonical agent ID: `dev-agent`.
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.4 for the bounded context catalog entry.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/dev_agent/` |
| Owned tables | `dev_agent_*` (tasks, workflow logs, event outbox) |
| Aggregate root | `Task` (`core/domain/task.py:64-120`) |
| State machine | `core/domain/lifecycle/task_lifecycle.py:26-38` `VALID_TRANSITIONS` table over 12 statuses (`pending → planning → awaiting_approval → executing → security_scanning → mr_creating → mr_created → qa_triggered → reviewing → completed / failed / expired`); `Task.transition_to()` enforces and raises `InvalidTaskTransitionError` on illegal moves |
| Value objects | `DevTaskId` and `WorkPackageId` from `shared/core/identifiers.py`; `TaskStatus` in `core/domain/lifecycle/task_lifecycle.py`; `RiskLevel` in `core/domain/task_values.py` |
| Domain policy | `core/domain/delivery_policy.py` owns automatic-delivery rejection, HITL workflow approval, capacity, and QA retry decisions |
| Domain events | `TaskStatusChanged` raised by aggregate; drained by use case and persisted to outbox |
| Unit of work | `core/unit_of_work_ports.py` `DevUnitOfWorkFactory` (explicit transaction boundary) |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Task** | A single unit of delivery work, derived from a PJM `Decomposition`. Has identity (`task_id`) and a foreign key to its OpenProject work package (`wp_id`). |
| **Workflow** | The end-to-end automation that takes a Task from `planning` to `mr_created`. Executed via AgentForge with each step persisted to `dev_agent_workflow_logs`. |
| **Risk level** | Pre-execution risk classification (`LOW / MEDIUM / HIGH / CRITICAL`) produced by the in-process risk assessor. Drives the gating decision for `awaiting_approval`. |
| **Security scan** | Static analysis step (`security_scanning` state) that must pass before code is committed to a branch. |
| **MR (Merge Request)** | The GitLab merge request created by the workflow. Recorded by `mr_iid` on the Task; published as `mr.created` for downstream consumers. |
| **QA trigger** | The handoff to QA Agent. Task moves to `qa_triggered` and Dev consumes `qa.acceptance-completed` / `qa.gate-failed` through the shared QA acceptance Published Language in `shared/core/qa_acceptance.py` to advance or fail. |
| **Approval gate** | Human-in-the-loop approval required for `HIGH` risk tasks before they execute. `CRITICAL` tasks are rejected from automatic delivery. Backed by `shared/control_plane/approval_gate.py`. |

Cross-link to the company-wide vocabulary:
[`docs/overview/glossary.md`](../../docs/overview/glossary.md).

## Consistency Rules

- One meaningful Dev `Task` exists for one OpenProject `WorkPackageId`; `DevTaskRepository.create_task()` persists with a unique `wp_id` constraint and `on_conflict_do_nothing`.
- `Task` is the aggregate root. `DevAgentWorkflowLog` rows are task-owned workflow/audit history written through the same unit-of-work, not a separate aggregate with its own lifecycle.
- Task lifecycle transitions must go through `TaskStatus` constants and `can_transition()` from `core/domain/lifecycle/task_lifecycle.py`.
- `DevDeliveryWorkflowPolicy` owns decisions that are meaningful to the domain: CRITICAL tasks are rejected from automatic delivery, HIGH tasks wait for HITL workflow approval, capacity limits queue work, and QA failures get one retry.

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.4:

- **Upstream**: Customer/Supplier to PJM (consumes `decomposition.*`) and QA (consumes `qa.gate-failed` for retry).
- **Downstream**: Customer/Supplier to Channel Gateway (emits `mr.*` events).
- **ACL** to GitLab and AgentForge via `adapters/gitlab_client.py` and `adapters/agentforge_client.py`.
- **Conformist** to Control Plane on AgentRun / Approval / AuditEvent Published Language.

## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `pm.tasks-ready-for-dev` | Subscribe | Decomposition output handed to Dev |
| `qa.acceptance-completed` | Subscribe | QA verdict for a Dev-produced MR |
| `dev.task-failed` | Publish | Task transitioned to `failed` |
| `mr.created` | Publish | GitLab MR created for a Task |

Event payloads live in `shared/schemas/event_payloads.py`; the Event Catalog at
[`docs/guides/event-catalog.md`](../../docs/guides/event-catalog.md) is the
authoritative list.

## API

See [`docs/guides/api-reference.md`](../../docs/guides/api-reference.md) for the operator-facing Dev REST surface (task listing, workflow status).

## Development

```bash
pytest agents/dev_agent/tests/ -v
```

## Architecture

Layered per `architecture-principles.md`:

```
api/        FastAPI routers — thin handlers
app/        create_agent_app() wiring + outbox dispatcher plugin
core/
  application_facade.py — composes use cases for the service shell
  domain/   Task aggregate, value objects, 12-state FSM, delivery policy
  workflow_execution_use_cases.py — multi-step workflow orchestration
  workflow_validator.py, security_scanner.py, risk_assessor.py — operational tools behind domain use cases
  *_use_cases.py — orchestration only; depends on ports
  repositories.py — outbound port interfaces (DevTaskRepositoryPort, DevWorkflowLogRepositoryPort)
db/         SQLAlchemy stores; returns domain models
adapters/   gitlab_client.py + agentforge_client.py — agent-local ACL
service/    BaseAgent subclass
models/     Pydantic DTOs
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md) §4.4.
