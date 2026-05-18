# Data Ownership

Last updated: 2026-05-18

Status: Foundation document.

This document codifies the data ownership rules for the Wisdoverse Cell
backend. It is binding for any PR that introduces, renames, or relocates a
persistent storage object (table, projection, cache, vector index).

The authoritative table → owner mapping lives in
[`docs/guides/backend-boundaries.md`](../guides/backend-boundaries.md) §3.
This document defines the rules that mapping must respect.

---

## 1. Ownership Rules

1. **One write owner per table.** A persistent storage object has exactly
   one runtime that may write to it. Other runtimes read through APIs, RPC,
   events, or documented read-only projections.
2. **Cross-runtime joins are forbidden.** Reads that need data from another
   runtime use an API/RPC call, consume an event, or read a projection
   table that this runtime owns.
3. **Outbox per runtime.** Every runtime that publishes integration events
   owns a `*_event_outbox` table. The outbox lives in the runtime's own
   schema (today shared DB; per-runtime DB after Migration Plan Stage 4).
4. **Analysis reads only projections.** The Analysis capability must depend
   on projection ports; direct source-table reads are forbidden. This rule
   lands with Migration Plan Stage 3.
5. **Identity has a single public path.** Writes to `users` go through the
   Identity / User API; no other runtime writes to identity tables. This
   rule lands with Migration Plan Stage 3.
6. **No ORM Entity as cross-service contract.** ORM `*Table` classes are
   private to the owning runtime. Cross-boundary contracts use Pydantic
   DTOs or integration event payloads.
7. **One transaction per local boundary.** A single transaction commits
   within one runtime's schema. Distributed transactions are out of scope.
   Multi-runtime workflows compose one local transaction plus
   outbox/projection.
8. **Projections are append/replace; never write owners.** A projection is
   rebuilt from events or scheduled jobs. It must never be the source of
   truth for the source domain.
9. **No "convenience" cross-runtime imports.** A runtime may not import an
   ORM table or repository from another runtime to "save a hop". Use the
   public API or event contract.
10. **Add a row in the same PR.** New tables ship with a row added to
    `docs/guides/backend-boundaries.md` §3 and an updated context entry in
    `docs/architecture/module-boundaries.md` in the same PR.

---

## 2. Storage Inventory

The owners below match `docs/guides/backend-boundaries.md` §3. When the two
documents disagree, the guide wins; update this document to match.

| Tables (representative) | Owner runtime | Reader policy |
|--------------------------|---------------|---------------|
| `control_plane_*` | Control Plane | `/api/v1/control-plane/*`; explicit read paths |
| `meetings`, `requirements`, `open_questions`, `feedback_records`, `llm_usage`, `chat_messages`, `requirement_event_outbox` | Requirement Manager | Requirement API/RPC, events, projection |
| `pjm_agent_*` | PJM Agent | PJM API/events, projection |
| `dev_agent_*` | Dev Agent | Dev API/events, projection |
| `qa_acceptance_*`, `qa_agent_event_outbox` | QA Agent | QA API/events, projection |
| `sync_agent_*` | Sync (OpenProject + Feishu Bitable sub-boundaries) | Sync API/status, projection |
| `chat_agent_*`, `channel_gateway_event_outbox` | User Interaction + Channel Gateways | Gateway API/events, analytics projection |
| `coordinator_event_outbox` | Coordinator | Coordinator events, operator replay |
| `analysis_agent_*` | Analysis | Analysis API/events |
| `evolution_*` | Evolution | Evolution API/events; proposal views via Control Plane |
| `users` | Identity (target boundary; not finalized) | Identity / User API |

Outbox tables (one per runtime, all integration-event publishers):

`requirement_event_outbox`, `pjm_event_outbox` (or `pjm_agent_event_outbox`),
`dev_event_outbox` (or `dev_agent_event_outbox`), `qa_agent_event_outbox`,
`sync_agent_event_outbox`, `analysis_agent_event_outbox`,
`evolution_event_outbox`, `coordinator_event_outbox`,
`channel_gateway_event_outbox`, `chat_agent_event_outbox`.

---

## 3. Cross-Boundary Read Patterns

Pick exactly one per data flow. Document the choice in the PR.

1. **API/RPC**. Use when the caller needs a strongly consistent read at the
   moment of the call (e.g., approval status before publication).
2. **EventBus integration event**. Use when the caller can act on
   eventually-consistent state and needs to react to a domain change
   (e.g., decomposition triggers downstream planning).
3. **Read-only projection**. Use when the caller needs to query the data
   shape repeatedly and joins/aggregations matter (e.g., Analysis dashboards).

Do not mix these for one data flow. Mixing makes the contract harder to
reason about and the failure modes harder to recover.

---

## 4. Migration Rules

1. Every new table requires:
   (a) an Alembic migration in the same PR;
   (b) a row in `docs/guides/backend-boundaries.md` §3;
   (c) a context entry in `docs/architecture/module-boundaries.md`;
   (d) a test that exercises the migration up and down.
2. Renaming a table is a contract change. It requires a deprecation window
   with both names live, plus a migration that copies data atomically.
3. Changing a table's owner runtime requires:
   (a) a written cutover plan with operator steps;
   (b) a compatibility read path that survives both owners during cutover;
   (c) audit evidence that the original owner has no remaining writers
   before the switch.
4. Backfills happen behind idempotency keys. A rerun of the same backfill
   produces the same result.
5. The single Alembic directory becomes per-runtime in Migration Plan
   Stage 4. Until then, all migrations land in `migrations/versions/` with
   a name prefix that identifies the owning runtime.

---

## 5. Vector and Cache State

`Milvus` collections and `Redis` keys obey the same ownership rule: one
runtime is the writer; reads cross boundaries through APIs or events. Vector
indexes are best-effort and are not the source of truth.

---

## 6. Forbidden Patterns

- A runtime opening a SQLAlchemy session against another runtime's tables.
- A use case importing an ORM model from a sibling runtime.
- A projection writing into a source-domain table.
- A "shared" cache key that more than one runtime writes to without a
  documented contract.
- A migration that touches more than one runtime's tables in one step
  without an explicit cutover plan.
- A "read replica" pattern that lets non-owners write because "it is the
  same database".

---

## 7. Maintenance

When this document changes:

- Update `docs/guides/backend-boundaries.md` §3 in the same PR.
- Update `docs/architecture/module-boundaries.md` if a context's data
  inventory changes.
- Update `tests/unit/test_architecture_boundaries.py` to encode any new
  cross-runtime import rule.
