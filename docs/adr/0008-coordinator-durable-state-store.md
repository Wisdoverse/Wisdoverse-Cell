# ADR-0008: Coordinator Durable State Store

- **Date**: 2026-05-22
- **Status**: Accepted
- **Closes**: Phase 1 audit §11 open question 2; DDD compliance audit row DDD-018.

## Context

The Coordinator service (`services/orchestration/coordinator/`) classifies
inbound EventBus events and emits dispatch decisions for downstream
runtime agents. To decide well, it consults three pieces of state:

- the per-agent state cache (`status`, `current_task`),
- a scratchpad (incremental reasoning context for the LLM thinker),
- the set of pending decisions awaiting resolution.

All three live behind ports in `services/orchestration/coordinator/core/`:

- `core/state_ports.py` `CoordinatorStateStorePort` Protocol
- `core/event_use_cases.py` `CoordinatorScratchpadPort` Protocol

The ports are clean. The **default adapter** that ships today
(`services/orchestration/coordinator/db/state_store.py:13`
`CoordinatorStateStore`) is **in-memory**. It serves the unit-test path
and the default Compose topology but does not survive process restart.
No operator replay tooling exists for in-flight coordination state.

The DDD compliance audit flagged this as DDD-018 (high severity) and as
the unresolved Phase 1 §11 open question 2. The implicit durability is
acceptable for development; it is not acceptable for any deployment
that loses coordination decisions on a coordinator restart.

## Decision

Adopt a **Postgres-backed durable adapter** for
`CoordinatorStateStorePort` and `CoordinatorScratchpadPort`. The
adapter writes to the coordinator's owned schema using SQLAlchemy
async sessions; the schema lives in the same Alembic migration root as
the existing `coordinator_event_outbox` table (per
[`data-ownership.md`](../architecture/data-ownership.md) rule 3, "outbox
per runtime; same DB today; one DB per runtime after Migration Plan
Stage 4").

Concrete plan:

1. Add `coordinator_agent_state`, `coordinator_workflow_state`,
   `coordinator_pending_decision`, and `coordinator_scratchpad` tables
   under `services/orchestration/coordinator/models/`. Each row is
   keyed by the existing logical identifier (`agent_id`, `workflow_id`,
   `decision_id`).
2. Add `services/orchestration/coordinator/db/postgres_state_store.py`
   implementing `CoordinatorStateStorePort`. The Pydantic in-memory
   `CoordinatorStateStore` adapter is kept for unit tests but is no
   longer the default in any deployment topology.
3. Add a `coordinator-replay` operator command that re-emits dispatch
   events for `coordinator_pending_decision` rows whose `status` is
   `pending` and whose `created_at` is older than a configurable
   threshold.
4. Wire the durable adapter in `services/orchestration/coordinator/app/`
   when `COORDINATOR_DURABLE_STATE=true` (the default in production
   topology) and fall back to the in-memory adapter for the
   `unit-test` configuration profile.
5. Extend
   [`docs/architecture/observability-guidelines.md`](../architecture/observability-guidelines.md)
   with the four metrics that bracket coordinator-state durability:
   - `coordinator_state_writes_total{table}`
   - `coordinator_pending_decisions_oldest_age_seconds`
   - `coordinator_scratchpad_size_bytes`
   - `coordinator_replay_runs_total{outcome}`
6. Add the `coordinator-replay` runbook step to
   [`docs/guides/incident-response.md`](../guides/incident-response.md).

## Rationale

- **Same boundary as the outbox**. The coordinator already owns
  `coordinator_event_outbox` in the shared database. Adding the
  state tables next to it keeps one runtime owner per schema and one
  Alembic chain per runtime (Stage 4 still applies).
- **Postgres-backed, not Redis-backed**. Coordinator state is small
  but correctness-sensitive (a missed decision = a stalled workflow).
  Postgres gives ACID and Alembic-tracked schema; Redis is the
  EventBus delivery medium, not a durable state store. ADR-0002 keeps
  the persistence boundary at Postgres.
- **In-memory adapter kept for tests**. Pure unit tests should not
  pay the cost of a Postgres fixture. The Protocol stays the
  development seam.
- **Replay tooling at the same layer as the data**. Operator replay
  must read the same rows the coordinator wrote; an external
  read-through replay service would break the data-ownership rule.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| Redis-only durable adapter | Redis already serves EventBus delivery. Mixing the durable state of decisions with the delivery channel makes it harder to recover when Redis evicts. Postgres is the canonical persistence boundary (ADR-0002). |
| Per-event reconstruction (no durable state) | Coordinator state spans multiple events; rebuilding from the event log requires scanning the EventBus and is not bounded. Stateful reads need a real store. |
| Move state to Control Plane ledger | Control Plane owns durable product objects; coordinator state is operational not product. Co-mingling them couples two unrelated change rates. |
| New separate `coordinator` database | A separate DB is the Stage 4 target for every runtime, not a special case for the coordinator. Per ADR-0002 / Migration Plan §4, all runtimes adopt per-DB isolation together. |

## Consequences

- New Alembic migration adds 4 tables. Net schema change is additive;
  no existing columns move.
- `CoordinatorEventUseCase` semantics do not change. Use cases
  continue to depend on ports; the adapter swap is invisible to the
  application layer per
  [`architecture-principles.md`](../architecture/architecture-principles.md) §1.
- Operator playbook gains one new command (`coordinator-replay`); the
  runbook must reference it.
- Tests: a new `tests/integration/coordinator/test_postgres_state_store.py`
  proves the adapter end-to-end against a real Postgres fixture; the
  existing in-memory test path is preserved.

## Rollout

1. Land the schema migration and the durable adapter implementation
   behind the `COORDINATOR_DURABLE_STATE` flag (default off).
2. Stage smoke: enable in non-production for two weeks; watch the
   four metrics + DLQ trends.
3. Default to on in production topology; keep the in-memory adapter
   reachable for unit tests only.
4. Run the `coordinator-replay` playbook once in staging to validate
   the operator path before any production restart that could lose
   in-flight decisions.

## Status Tracking

- Schema migration: pending follow-up PR.
- Postgres adapter implementation: pending follow-up PR.
- Replay tooling: pending follow-up PR.
- Operator runbook + metrics: pending follow-up PR.

This ADR records the **decision**; the implementation lands in the
follow-up PR sequence per
[`architecture-principles.md`](../architecture/architecture-principles.md)
§3 ("no one-shot rewrites").
