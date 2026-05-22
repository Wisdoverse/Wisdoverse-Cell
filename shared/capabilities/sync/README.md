# Sync Capability

Shared support capability that projects state between OpenProject and
Feishu Bitable. Maintains mapping records, sync locks, and progress
back-flow.

Canonical runtime ID: `sync-module`.
See [`docs/architecture/module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.6.

## Bounded Context

| Field | Value |
|-------|-------|
| Runtime owner | `shared/capabilities/sync/` |
| Owned tables | `sync_agent_*` (`sync_mappings`, `subtask_mappings`, `sync_locks`, `sync_logs`, `sync_event_outbox`) |
| Sub-boundaries | Two: **OpenProject side** (`core/openproject_sync.py`) and **Feishu Bitable side** (`core/feishu_bitable_sync.py`). Today share one store and one outbox; targeted to split per DDD-014. |
| Aggregate root | **None yet — DDD-003 pending**. Today the sync flow is orchestrated in `core/engine.py` with string-status comparisons. |
| State machine | Not yet typed. `engine.py:74-87` drives behavior off `op_status == "failed" or feishu_status == "failed"`. Replaced by a typed FSM under DDD-003. |
| Domain events | Staged through `core/openproject_sync.py:61,104` and forwarded to the outbox by `core/event_use_cases.py`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Sync operation** | One run of the sync engine: classifies what changed, calls each side, persists results. |
| **Mapping** | Persistent link between an OpenProject work-package id and a Feishu Bitable record id. Stored in `sync_mappings` / `subtask_mappings`. |
| **Sync lock** | Advisory lock preventing concurrent sync runs over the same scope. Stored in `sync_locks`. |
| **OpenProject side** | The OP-leg of the operation: read/write work packages through `OpenProjectWorkPackagePort`. |
| **Feishu Bitable side** | The Bitable-leg of the operation: read/write records through `BitableTablePort`. |
| **Progress back-flow** | Updates pushed from Bitable subtask completion back to OpenProject `percentageDone`. Computed by `core/progress.py`. |
| **Scope** | A grouping (project, table, or work-package set) over which one sync operation runs. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.6:

- **Upstream**: Customer/Supplier to PJM (receives decomposition handoff).
- **Internal**: two sub-boundaries in Partnership today; target Separate Ways per DDD-014.
- **External**: ACL to OpenProject and Feishu Bitable through integration ports.
- **Conformist** to Control Plane on AgentRun / AuditEvent.

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  engine.py                 orchestrator (string-status today; DDD-003 typed FSM target)
  openproject_sync.py       OP-side use cases
  feishu_bitable_sync.py    Bitable-side use cases
  scope_execution_use_cases.py
  request_use_cases.py
  event_use_cases.py
  outbox_delivery_use_cases.py
  mapper.py                 OP ↔ Bitable translation (domain service)
  progress.py               percentage-done calculator (domain service)
  locking.py                advisory-lock guard
  sync_ports.py             outbound ports
db/                         SQLAlchemy stores
adapters/                   none — uses shared/integrations OP + Bitable
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.6 (OpenProject side) and §4.7 (Feishu Bitable side).
