# ADR-0009: Sync Sub-Runtime Split

- **Date**: 2026-05-22
- **Status**: Accepted (decision); implementation Stage 4 work.
- **Closes**: DDD compliance audit row DDD-014; M4 / P2-3 from the Phase 1 backend audit.

## Context

`shared/capabilities/sync/` hosts two distinct sub-boundaries inside one
runtime today:

| Sub-boundary | Code | External system |
|--------------|------|-----------------|
| OpenProject side | `core/openproject_sync.py` | OpenProject |
| Feishu Bitable side | `core/feishu_bitable_sync.py` | Feishu Bitable |

They share one `SyncStore`, one outbox (`sync_event_outbox`), and one
runtime plugin. The orchestrating engine in `core/engine.py:74-87` runs
both halves and combines their outcomes.

Constraints documented elsewhere:

- `CLAUDE.md` Part 3 / `AGENTS.md` Part 3: "The sync runtime must keep
  OpenProject synchronization and Feishu Bitable synchronization as
  separate bounded capabilities, even when a compatibility endpoint
  orchestrates both."
- `module-boundaries.md` §2.6: today's split exists inside `core/`
  only; target is two sub-capability runtimes.
- `service-boundaries.md` §4: extraction requires per-runtime
  migrations + projection + replay + observability per the §4 rule of
  thumb.
- `ddd-compliance-audit.md` row DDD-003 (seed landed): `SyncOperation`
  aggregate now carries a `SyncSide` discriminator so the same domain
  class serves both during the modular-monolith phase and is ready to
  split.

## Decision

Adopt a **two-step sub-runtime split** for Sync, scheduled in Migration
Plan Stage 4 once the Sync `SyncOperation` aggregate (DDD-003 follow-up
PRs) has migrated `core/engine.py` off string statuses.

### Step 1 — Internal split (no deployment change)

1. Move `core/openproject_sync.py` and its specific ports into
   `core/openproject/` (sub-package).
2. Move `core/feishu_bitable_sync.py` and its specific ports into
   `core/feishu_bitable/` (sub-package).
3. Split `SyncStore` into `OpenProjectSyncStore` and
   `FeishuBitableSyncStore`, each owning a subset of `sync_agent_*`
   tables (mapping table → sub-runtime via the existing `side`
   discriminator on rows).
4. Keep `core/engine.py` as a compatibility orchestrator that calls
   both sub-stores; mark deprecated.
5. Two new runtime plugins: `sync_openproject_outbox_dispatcher` and
   `sync_feishu_bitable_outbox_dispatcher`. Two new outbox tables
   (`sync_openproject_event_outbox`, `sync_feishu_bitable_event_outbox`)
   created by an additive Alembic migration; the legacy
   `sync_event_outbox` is dual-written during the cutover window,
   then frozen, then removed in a follow-up migration.

### Step 2 — Runtime split

1. Two new canonical agent IDs: `sync-openproject`, `sync-feishu-bitable`.
   The legacy `sync-module` runtime remains in the agent catalog as a
   deprecated compatibility entry for one release window.
2. Two new Compose services in the `cell` topology; the legacy single
   `sync-module` container is removed after the two new ones run
   bound-stable for two weeks in staging.
3. Each sub-runtime owns its own Alembic directory per Stage 4
   pre-condition (Migration Plan §Stage 4 item 1).
4. The orchestrator compatibility endpoint (`/sync/full`) moves to
   either `pjm-agent` (orchestration consumer) or a thin coordinator
   plugin; sync sub-runtimes accept individual triggers only.

## Rationale

- **Capability split is already declared**. CLAUDE.md / AGENTS.md /
  module-boundaries.md state the two sides are separate capabilities;
  this ADR records when and how the deployment topology follows.
- **DDD-003 aggregate is ready**. `SyncOperation` carries the
  `SyncSide` discriminator and the FSM is typed; the sub-runtime
  split is a matter of moving the right rows + use cases to each side.
- **Failure-isolation matters**. A Feishu outage today freezes the
  OpenProject side because they share the same engine + outbox.
- **Independent scaling**. The two sides have different rate profiles
  (Bitable bursts on subtask updates; OpenProject is steady-state).
- **Stage 4 work**. Per `service-boundaries.md` §4 the split requires
  per-runtime migrations + projection + replay + observability;
  Stages 0–3 supply the seams. This ADR sequences the split after
  Stages 0–3 done.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Keep one Sync runtime | Documented split intent in CLAUDE.md / AGENTS.md is binding; keeping one runtime contradicts the constitution. |
| Split sub-packages now (internal only, no runtime) | Half-measure: the split inside `core/` is already done (`openproject_sync.py` vs `feishu_bitable_sync.py`). The next valuable seam is the deployment + outbox split. |
| Extract OpenProject side first, leave Bitable | Both sides are equally split-fit (`service-boundaries.md` §4 matrix lists both at the same rank). Asymmetric extraction adds coordination cost without value. |
| Use sub-process workers inside one runtime | Doesn't isolate process crashes or scale independently. |

## Consequences

- New canonical agent IDs (`sync-openproject`, `sync-feishu-bitable`)
  must be added to `agent_catalog.py` (`AGENTS.md` Part 3 rule 13
  is amended to include them).
- Two new Alembic migration directories.
- Two new outbox tables; one frozen + removed migration for the
  legacy outbox after cutover.
- Two new Prometheus dashboards; alert rules for outbox-lag and DLQ
  cloned per side.
- `service-boundaries.md` §4 matrix updated: Sync row split into two.
- `data-ownership.md` §2 storage inventory updated.

## Rollout

This is Stage 4 work per `migration-plan.md`. Pre-conditions (all
must hold before Step 1 begins):

1. DDD-003 follow-up PRs have migrated `core/engine.py` to the typed
   `SyncOperation` FSM.
2. DDD-004 Analysis projection layer is consuming sync output (so the
   sub-split does not break Analysis reads).
3. Per-runtime migration story (`per-runtime-migrations.md`) is
   adopted.
4. Two-week staging burn of the existing single-runtime Sync to
   establish a baseline for outbox-lag and DLQ comparison.

Rollback: at any point the legacy single-runtime container can be
re-enabled and the legacy outbox table can be re-promoted as
authoritative; the dual-write window is intentional so the rollback
is one configuration flip, not a data restore.

## Status Tracking

This ADR records the **decision and sequence**. Implementation lands
in dedicated PRs once DDD-003 use-case migration and DDD-004
projection layer are in place.

When this ADR's implementation lands, append to
`docs/architecture/migration-plan.md` Stage 4 section and update
`docs/architecture/service-boundaries.md` §4 matrix.
