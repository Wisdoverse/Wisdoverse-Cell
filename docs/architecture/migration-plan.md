# Backend Migration Plan

Last updated: 2026-05-18

Status: Foundation document. Standalone form of
[Backend Target Architecture](./backend-target-architecture.md) §5.

Six stages. Each stage states the goal, scope, verification, risk, and done
criteria. Stages 0 and 1 are non-behavior-changing and can ship first; later
stages depend on the seams established earlier.

The current PR set context:

- [Backend Architecture Analysis](./backend-architecture-analysis.md) —
  Phase 1 read-only audit.
- [Backend Evolution Plan](./backend-evolution-plan.md) — initial follow-up
  plan (kept as historical context).
- [Backend Target Architecture](./backend-target-architecture.md) — Phase 2
  target architecture and the first version of this roadmap.

When this document changes, the design doc above must be reconciled in the
same PR.

---

## Stage 0 — Architecture Docs and Standards

- **Goal**: lock the contract that every later stage runs against.
- **Scope**: ship the 10 foundation documents under `docs/architecture/`
  (this file plus its siblings) and add additive references in
  `docs/INDEX.md` and `AGENTS.md`.
- **Will not change**: any code, schema, route, event, configuration, or
  runtime artifact.
- **Risk**: low. Documentation only.
- **Verification**:
  - `git diff --check` clean.
  - Every internal doc link resolves on disk.
  - No file under `agents/`, `services/`, `shared/`, `migrations/`,
    `rust/`, `frontend/`, `docker/`, `infra/`, `scripts/`, `tests/`, or
    `plugins/` is modified.
- **Done criteria**: 10 docs merged on `main`; `docs/INDEX.md` updated;
  `AGENTS.md` references the architecture constitution doc set.

---

## Stage 1 — Code Structure Cleanup

- **Goal**: tighten module boundaries without touching business behavior.
- **Scope**:
  1. Add an explicit `core/domain/` directory per agent (empty initially;
     no class moves yet — just the package).
  2. Move `*_lifecycle.py` files into `core/domain/lifecycle/` and add a
     deprecation shim that re-exports from the old location until callers
     update.
  3. Hide `AsyncSession` from route handlers in
     `shared/control_plane/api.py` behind a `UnitOfWork` or
     session-provider port; route handlers receive stores, not sessions.
  4. Split `shared/control_plane/api.py` (1783 LOC) into per-aggregate
     routers under `shared/control_plane/api/` (file moves only; no
     logic change).
  5. Add minimum tests around the use cases touched in (3) and (4).
  6. Add `trace_id`, `agent_id`, and `run_id` logging on every use-case
     entry/exit (per `observability-guidelines.md` §2 item 3) using a
     small helper.
- **Will not change**: HTTP routes, request/response shapes, event names,
  payload schemas, database schema, business behavior.
- **Risk**: medium. File moves can break test discovery and CI cache;
  the session-provider port introduces a new internal contract.
- **Verification**:
  - Full `make test` regression matches the baseline (1860 passed / 15
    skipped / 183 deselected).
  - Architecture-boundary tests grow to cover the new rules (no
    `AsyncSession` in route handler signatures; no use case importing an
    adapter).
  - Manual HTTP smoke against `/api/v1/control-plane/*` confirms
    response shapes are unchanged.
- **Done criteria**: regression green; architecture-boundary tests cover
  the new rules; PR descriptions cite the rules added.

---

## Stage 2 — Core Domain Modeling

- **Goal**: turn the implicit domain into explicit code.
- **Scope** per business runtime (one PR per aggregate to keep diffs
  small):
  1. Identify the aggregate root (e.g., `Requirement`, `DevTask`,
     `AcceptanceRun`, `DecompositionRecord`, `AgentRun`).
  2. Define entities, value objects, and aggregate boundaries.
  3. Define an explicit state machine; illegal transitions raise a typed
     domain error.
  4. Move state-transition decisions out of use cases and stores into the
     aggregate.
  5. Introduce in-memory domain events; use cases collect them for
     outbox publication.
  6. Keep public HTTP and event payloads unchanged.
- **Will not change**: APIs, event payloads, DB schema, business
  behavior.
- **Risk**: medium. Behavior must remain identical; FSM refactors risk
  subtle differences.
- **Verification**:
  - Domain unit tests per aggregate.
  - Use-case tests asserting the same observable outcomes as before
    (snapshot/regression tests on responses + emitted events).
  - Per-aggregate FSM coverage matrix in the PR description.
- **Done criteria**: every business runtime has a non-empty `core/domain/`
  with an aggregate, an FSM, and matching unit tests.

---

## Stage 3 — Data Ownership and Boundaries

- **Goal**: enforce the data-ownership rules in
  [`data-ownership.md`](./data-ownership.md).
- **Scope**:
  1. Confirm one write owner per table; update
     `docs/guides/backend-boundaries.md` §3 if any row is wrong.
  2. Introduce an explicit projection table for Analysis. One projection
     per source domain it currently reads.
  3. Introduce an Identity / User write-owner path.
  4. Move ORM types out of business-logic returns: stores return domain
     models, not `*Table` rows.
  5. Add a CI rule to `tests/unit/test_architecture_boundaries.py` that
     forbids cross-runtime ORM imports in the application layer.
- **Will not change**: HTTP routes (additive only); event payloads
  (additive only); running migrations are additive (new projection
  tables); no in-place column changes.
- **Risk**: medium-high. Touches more code; projection roll-forward
  needs one operator step.
- **Verification**:
  - Migration test on the new projection tables.
  - Provider/consumer event tests for the events that drive projection
    inserts.
  - Backfill script idempotency test.
- **Done criteria**: Analysis depends only on projection ports; Identity
  has a single public API; architecture-boundary test forbids the
  remaining cross-runtime ORM access.

---

## Stage 4 — Service Boundary Evolution

- **Goal**: split the first one or two runtimes once the seams are ready.
- **Scope** (per service to extract; see
  [`service-boundaries.md`](./service-boundaries.md) §4):
  1. Move that runtime to its own Alembic directory (or per-runtime
     migration tool).
  2. Switch from in-process subscribe to remote EventBus consumer group;
     verify replay + DLQ.
  3. Publish per-agent OpenAPI snapshot; lock contract.
  4. Deploy as a separate container in staging; run the canary monitor.
  5. Document rollback: revert the container to the bundled `cell`
     topology and replay events from outbox.
- **Will not change**: public HTTP routes, public event payloads, control
  plane ledger contract.
- **Risk**: high. First extraction is the riskiest. Pick Dev or QA first
  (per the service-boundaries matrix).
- **Verification**:
  - Stage-3 done criteria all hold.
  - Smoke tests on the new container in staging for at least two weeks
    with outbox-lag, DLQ-rate, and LLM cost dashboards green.
  - Documented rollback exercised once in staging.
- **Done criteria**: one runtime runs independently in staging with
  bounded outbox lag, no DLQ growth, and observable SLIs meeting their
  SLOs.

---

## Stage 5 — Engineering Quality

- **Goal**: lock the engineering bar so later stages cannot regress.
- **Scope** (10 items from the brief):
  1. CI: keep the existing GitHub Actions pipeline; add per-runtime
     tests.
  2. Lint: `ruff` already in use; promote warnings to errors in two
     reviewed PRs.
  3. Type check: add `mypy` (or `pyright`) on `shared/control_plane/`,
     `shared/core/`, and one agent first; expand gradually.
  4. Test: keep `make test` as the canonical regression gate; expand
     contract + projection tests.
  5. Migration check: CI runs Alembic up + down on every PR that touches
     `migrations/`.
  6. Dependency check: Dependabot already wired; ensure security alerts
     route to Issues.
  7. Security baseline: continue secret-detection and PII tests; add
     scheduled `cso` mode runs.
  8. Release checklist: documented in `docs/guides/operations.md`; gated
     by the architecture-review checklist.
  9. Rollback checklist: per-runtime; documented as part of Stage 4
     extraction.
  10. Incident runbook: extend `docs/guides/incident-response.md` to
      cover outbox lag, DLQ overflow, LLM budget breach.
- **Will not change**: any business behavior. This stage is gate
  hardening.
- **Risk**: low to medium; type-check rollout can be noisy.
- **Verification**: every gate is enforced in CI and has a documented
  override path.
- **Done criteria**: every architecture-affecting PR passes the gate set
  defined here without manual exceptions.

---

## Cross-Stage Rules

1. Stages land in order. A later stage cannot begin until the earlier
   stage's done criteria are met.
2. Within a stage, sub-items may parallelize when they touch disjoint
   files and contexts.
3. Every PR cites the stage, scope item, and done criteria it addresses.
4. Reverts of any earlier-stage PR move the project back a stage; the
   later stage's done criteria are re-evaluated.

---

## Maintenance

When this document changes:

- Update `docs/architecture/backend-target-architecture.md` §5.
- Update `docs/architecture/backend-evolution-plan.md` if a phase
  ordering changes.
- Update `docs/architecture/architecture-review-checklist.md` if a new
  gate is introduced.
