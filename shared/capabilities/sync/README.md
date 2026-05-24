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
| Sub-boundaries | Two: **OpenProject side** (`core/openproject/engine.py`) and **Feishu Bitable side** (`core/feishu_bitable/engine.py`). Today share one runtime and one outbox; targeted to split per DDD-014. |
| Aggregate root | `SyncOperation` (`core/domain/sync_operation.py`) owns one sub-boundary run, status transitions, processed-count tally, and status-change domain events. |
| Value objects | `core/domain/sync_values.py` owns immutable `WorkPackageData`, `FeishuRecordData`, `SyncMappingRecord`, `SubtaskMappingRecord`, `SyncMappingId`, `SyncSubtaskMappingId`, `FeishuRecordId`, and `FeishuSubtaskStatus`; `shared/core/identifiers.py` supplies `WorkPackageId` and `OpenProjectProjectId`. |
| State machine | `SyncOperationStatus` and `VALID_TRANSITIONS` model `pending → running → succeeded / partial_failure / failed / skipped`; `engine.py` combines sub-boundary statuses through `combine_side_statuses()`. |
| Domain events | `SyncOperationStatusChanged` is raised by `SyncOperation.transition_to()`; integration lifecycle, Feishu progress-update, and decomposition handoff events are staged through `core/scope_execution_use_cases.py`, `core/feishu_bitable/engine.py`, and `core/openproject/engine.py` before outbox publish. |
| Unit of work | Split persistence ports in `core/sync_ports.py`: `OpenProjectSyncStore`, `FeishuBitableSyncStore`, `SyncEventOutboxStore`, and `SyncLockStore`. |

## Ubiquitous Language

| Term | Meaning |
|------|---------|
| **Sync operation** | One run of a sync sub-boundary. The aggregate has an `operation_id`, `side`, typed status, processed count, and status-change events. |
| **Mapping** | Persistent link between an OpenProject work-package id and a Feishu Bitable record id. `SyncMappingRecord` and `SubtaskMappingRecord` normalize persisted `sync_agent_mappings` / `sync_agent_subtask_mappings` rows before core code consumes them. |
| **Sync lock** | Advisory lock preventing concurrent sync runs over the same scope. Stored in `sync_locks`. |
| **OpenProject side** | The OP-leg of the operation: read/write work packages through `OpenProjectWorkPackagePort`. |
| **Feishu Bitable side** | The Bitable-leg of the operation: read/write records through `BitableTablePort`. |
| **Progress back-flow** | Updates pushed from Bitable subtask completion back to OpenProject `percentageDone`. Computed by `core/progress.py`. |
| **Scope** | A grouping (project, table, or work-package set) over which one sync operation runs. |
| **Work-package data** | Immutable Sync projection of an OpenProject work package used before writing Feishu fields. |
| **Feishu record data** | Immutable Sync projection of a Bitable record used before updating OpenProject progress. |
| **Feishu subtask status** | Typed status value used to classify completion for progress back-flow. |

## Context-Map Relationships

Per [`module-boundaries.md`](../../../docs/architecture/module-boundaries.md) §2.6:

- **Upstream**: Customer/Supplier to PJM (receives decomposition handoff).
- **Internal**: two sub-boundaries in Partnership today; target Separate Ways per DDD-014.
- **External**: ACL to OpenProject and Feishu Bitable through `core/mapper.py`, `core/domain/sync_values.py`, `OpenProjectWorkPackagePort`, and `BitableTablePort`.
- **Conformist** to Control Plane on AgentRun / AuditEvent.

## Architecture

```
core/
  application_facade.py     composes use cases for the service shell
  domain/
    sync_operation.py       SyncOperation aggregate + typed FSM
    sync_values.py          immutable Sync value objects + mapping records
  engine.py                 compatibility orchestrator over split engines
  openproject/engine.py     OP-side use cases
  feishu_bitable/engine.py  Bitable-side use cases
  scope_execution_use_cases.py
  request_use_cases.py
  event_use_cases.py
  outbox_delivery_use_cases.py
  mapper.py                 OP ↔ Bitable translation (ACL/domain service)
  progress.py               percentage-done calculator (domain service)
  locking.py                advisory-lock guard
  sync_ports.py             outbound ports
db/                         SQLAlchemy stores
adapters/                   none — uses shared/integrations OP + Bitable
```

DDD compliance: see
[`docs/architecture/ddd-compliance-audit.md`](../../../docs/architecture/ddd-compliance-audit.md) §4.6 (OpenProject side) and §4.7 (Feishu Bitable side).
