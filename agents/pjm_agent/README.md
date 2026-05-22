# PJM Agent

Real business runtime agent for project management. Decomposes confirmed
requirements into delivery-ready work items, prepares approvals, surfaces
project reports and alerts.

Canonical agent ID: `pjm-agent`.
See [`docs/architecture/module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.3 for the bounded context catalog entry.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `agents/pjm_agent/` |
| Owned tables | `pjm_agent_*` (decomposition records, alert log, config cache, event outbox) |
| Aggregate root | `Decomposition` (`core/domain/decomposition.py:58-108`) |
| State machine | `core/domain/lifecycle/decomposition_lifecycle.py:45-52` `VALID_TRANSITIONS` table; `Decomposition.transition_to()` enforces and raises `InvalidDecompositionTransitionError` on illegal moves |
| Domain events | `DecompositionStatusChanged` raised by aggregate; drained by use case and persisted to outbox |
| Unit of work | `core/decomposition_ports.py` `PJMDecompositionTransaction` Protocol (explicit transaction boundary) |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Decomposition** | Breaking one confirmed Requirement (work item) into one or more delivery-ready sub-items. Modeled as an aggregate keyed on `wp_id` (OpenProject work-package ID). |
| **Work Package** (`wp_id`) | The OpenProject identifier for the unit of delivery. PJM maintains a `Decomposition` per `wp_id`. |
| **Decomposition state** | `pending → writing → approved` (or `write_failed`, `failed`, `rejected`). Each transition is FSM-enforced and emits a `DecompositionStatusChanged` event. |
| **Approval preparation** | The step where a Decomposition is queued for human-in-the-loop approval (per `architecture-principles.md` §4 human gates) before it reaches Dev / QA. |
| **Alert** | A reportable condition (overdue task, decomposition failure, sync conflict). Logged to `pjm_agent_alert_log` and published via `pm.alert-triggered`. |
| **Config cache** | Per-project decomposition prompt / threshold configuration; refreshed lazily and stored in `pjm_agent_config_cache`. |

Cross-link to the company-wide vocabulary:
[`docs/overview/glossary.md`](../../docs/overview/glossary.md).

## Context-Map Relationships

Per [`module-boundaries.md`](../../docs/architecture/module-boundaries.md) §2.3:

- **Upstream**: Customer/Supplier to Requirement Manager (consumes `requirement.*`) and Coordinator (consumes `decomposition.request`).
- **Downstream**: Customer/Supplier to Dev Agent, QA Agent, and Sync capability (emits `decomposition.*` events).
- **ACL** to OpenProject via the Sync capability.
- **Conformist** to Control Plane on AgentRun / AuditEvent Published Language.

## Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `sync.completed` | Subscribe | Sync run finished (consumes for progress / re-trigger) |
| `analysis.risk-detected` | Subscribe | Risk signal from Analysis capability |
| `chat.pm-query` | Subscribe | Operator query routed via Channel Gateway |
| `sync.task-needs-decompose` | Subscribe | Sync flagged a work package needing decomposition |
| `coordinator.dispatch` | Subscribe | Cross-boundary dispatch envelope from Coordinator |
| `pm.alert-triggered` | Publish | Project alert (overdue, failed, drift) |
| `chat.pm-response` | Publish | Reply to operator query |
| `pm.decomposition-failed` | Publish | Decomposition could not be produced |
| `decomposition.*` | Publish | Decomposition lifecycle integration events |

Event payloads live in `shared/schemas/event_payloads.py`; the Event Catalog at
[`docs/guides/event-catalog.md`](../../docs/guides/event-catalog.md) is the
authoritative list.

## API

See [`docs/guides/api-reference.md`](../../docs/guides/api-reference.md) for the operator-facing PJM REST surface (decomposition, reports, alerts).

## Development

```bash
pytest agents/pjm_agent/tests/ -v
```

## Architecture

Layered per `architecture-principles.md`:

```
api/        FastAPI routers — thin handlers
app/        create_agent_app() wiring + outbox dispatcher plugin
core/
  application_facade.py — composes use cases for the service shell
  domain/   Decomposition aggregate + state machine
  *_use_cases.py — orchestration only; depends on ports
  decomposition_orchestrator.py — multi-step workflow composition
  *_ports.py — outbound port interfaces
db/         SQLAlchemy stores; returns domain models
adapters/   External SDK / HTTP clients (e.g. Feishu cards)
service/    BaseAgent subclass
models/     Pydantic DTOs
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../docs/architecture/ddd-compliance-audit.md) §4.3.
