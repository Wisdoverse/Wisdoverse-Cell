# Per-Runtime Migration Cutover Plan

Last updated: 2026-10-01

Status: Stage 4 pre-condition design doc per
[`migration-plan.md`](./migration-plan.md) §Stage 4 item 1
("Move that runtime to its own Alembic directory"). Phase 1 audit
H1 / P0-2 named the single Alembic directory as the structural
blocker for any runtime extraction. This document captures the
cutover plan; the actual move is a follow-up PR sequence executed
only when a runtime is ready to extract.

---

## 1. Current State

Single Alembic surface, shared by all runtimes:

```text
alembic.ini                          # one config
migrations/
├── env.py                           # imports every runtime's Base
├── script.py.mako                   # one template
└── versions/                        # 19 migrations across all runtimes
    ├── 20260501_control_plane_ledger.py
    ├── 20260502_reqmgr_tables.py
    ├── 20260503_agentrole_events.py
    ├── 20260504_pjm_decomp_statuses.py
    ├── 20260504_qa_run_idempotency.py
    └── ...
```

`migrations/env.py` imports every runtime's `Base` so autogenerate
sees the full schema across:

- `agents/{dev_agent,pjm_agent,qa_agent,requirement_manager}/models/`
- `shared/control_plane/tables.py`
- `shared/evolution/db/tables.py`
- `shared/db/base.py` (User/Platform)
- `services/orchestration/coordinator/db/models.py`
- `shared/capabilities/{sync,analysis,evolution}` tables

One `alembic_version` row in PostgreSQL tracks the merged history.

---

## 2. Target State

Per-runtime Alembic surfaces:

```text
agents/<runtime>/migrations/
├── alembic.ini                      # runtime-specific
├── env.py                           # imports only this runtime's Base
├── script.py.mako
└── versions/                        # runtime's migrations only
shared/control_plane/migrations/     # control-plane is its own boundary
shared/evolution/db/migrations/      # evolution capability
```

Each runtime owns its `alembic_version_<runtime>` table (separate name
to coexist with the legacy global one during the cutover).

---

## 2.1 Dev S4.1 Engineering Acceptance

`agents/dev_agent/migrations/` contains a **rehearsal-only** candidate
baseline (`20261001_dev_baseline`). Its environment accepts only a supplied
connection; it does not read runtime database settings or enable a production
CLI. The legacy migration chain and its Dev metadata imports remain active.
The candidate freezes the Dev DDL inherited from the legacy chain, rather
than generating DDL from mutable ORM models.

| Owned table | Legacy source | Candidate owner |
|-------------|---------------|-----------------|
| `dev_agent_tasks` | `20260504_runtime_tables` | Dev Agent |
| `dev_agent_workflow_logs` | `20260504_runtime_tables` | Dev Agent |
| `dev_agent_event_outbox` | `20260512_dev_event_outbox` | Dev Agent |
| `alembic_version_dev_agent` | New candidate tracking | Dev Agent |

The synthetic engineering acceptance passed on PostgreSQL 18.6 on
2026-10-01. The dated result and source fingerprint are recorded in the
[S4.1 evidence record](./evidence/dev-migration-s41.md). To reproduce against
a disposable PostgreSQL database, set `TEST_DATABASE_URL` to a
`postgresql+asyncpg` URL and run:

```bash
TEST_DATABASE_URL='postgresql+asyncpg://user:password@127.0.0.1:5433/wisdoverse_cell_migration_test' \
  make migration-rehearse-dev

# Or use the local PostgreSQL 18 container's pg_dump/pg_restore clients.
TEST_DATABASE_URL='postgresql+asyncpg://user:password@127.0.0.1:5433/wisdoverse_cell_migration_test' \
  POSTGRES_CONTAINER=wisdoverse-cell-postgres make migration-rehearse-dev
```

The default machine-readable report is `.artifacts/s41-dev-postgresql.json`.
Override it with `DEV_MIGRATION_REHEARSAL_REPORT`; direct Python invocation
accepts `--report` or `REHEARSAL_REPORT`. Local PostgreSQL client binaries
version 18 are supported. To run clients from a local Docker container, set
`POSTGRES_CONTAINER` or pass `--postgres-container <container>`; the URL still
identifies the same disposable database. The runner bounds connect, SQL and
client operations at 10, 30 and 60 seconds respectively, with no retries.

The runner creates a UUID-named `dev_rehearsal_<32 lowercase hex>` schema,
sets a transaction-local search path with no public fallback, and removes the
schema on completion or failure. It never downgrades the shared migration
chain. Reports contain synthetic check results and source identity, not the
database URL, credentials or row contents.

The rehearsal verifies:

- Fresh upgrade → downgrade to base → upgrade with identical schema inventory.
- Baseline parity with independently applied legacy Dev DDL, including
  columns/defaults, primary keys, indexes, checks, unique constraints and FKs.
  CHECK comparison normalizes only PostgreSQL restore's equivalent array/text
  casts for the two finite Dev vocabularies; literal choices stay significant.
- Stamp → upgrade → rollback tracking → restamp with synthetic task,
  workflow log and pending outbox rows preserved.
- Separate version tracking and an unchanged legacy version sentinel.
- A real custom-format `pg_dump`, destructive removal of the isolated schema,
  and `pg_restore --single-transaction`, followed by schema/data comparison
  and stamp rollback/restamp after restore.
- Injected version mutation plus DDL failure rolls back to the savepoint;
  actual missing-index drift prevents stamping, and inherited baseline
  downgrade is rejected.
- Source input fingerprint stability during verification.
- Verified schema cleanup and preservation of the legacy version and
  outside-runtime sentinels.

**Inherited-schema rollback uses `stamp base`, never `downgrade base`.**
The latter drops Dev tables and belongs only to the empty-schema rehearsal.
This engineering acceptance covers a synthetic PostgreSQL schema only. It
does not complete production-copy validation, cutover scheduling, operational
backup sign-off, staging observation or production acceptance. Those rollout
gates remain governed by §§3–5 and the release/rollback checklists. The shared
legacy chain remains the active migration owner; there is no public API or
event-payload change in this work.

If cleanup reports failure, use the `rehearsal_schema` value in the sanitized
report. Before manual removal, verify that the identifier begins with
`dev_rehearsal_`, has exactly 32 lowercase hexadecimal suffix characters,
belongs to this disposable rehearsal database, and is not in use. Only then
may an operator remove that exact schema. Never broaden cleanup to a prefix or
the public schema.

## 3. Pre-conditions

The following MUST hold before an actual physical cutover begins. They do not
block the reversible synthetic engineering rehearsal in §2.1:

- [ ] Migration Plan Stage 3 closure — no cross-runtime ORM imports
      (already locked by
      `test_only_control_plane_imports_control_plane_orm` in #144).
- [ ] Stable backend regression on `main` (existing `make test` gate).
- [ ] A documented copy of the production `pg_dump` taken within 24h
      of the planned cutover.
- [ ] Operator availability for the cutover window (cutover is a
      stop-the-world step).
- [ ] All open feature branches that add migrations rebased onto
      `main` before the cutover starts (no in-flight migration adds).

---

## 4. Cutover Sequence

The cutover happens per runtime. The order is:

1. `dev-agent` (smallest schema, well-tested aggregate).
2. `qa-agent` (small schema, idempotent triggers).
3. `pjm-agent` (medium schema).
4. `requirement-manager` (largest schema — 7 tables; do last).
5. Capabilities and gateways follow once the agent split is proven.
6. Control plane stays central until the very last step (it is the
   ledger; splitting it loses the operator surface).

### 4.1 Per-Runtime Steps

For each `<runtime>`:

#### 4.1.1 Create the new Alembic surface

```bash
# In the target runtime's package root.
cd agents/<runtime>
alembic init -t async migrations
# Edit migrations/env.py to import ONLY this runtime's Base.
# Edit alembic.ini script_location -> agents/<runtime>/migrations
# Set version_table = "alembic_version_<runtime>" in env.py.
```

#### 4.1.2 Stamp the new version table

```bash
# On a copy of production: bring the runtime's tables up to the
# current head of the global migration chain, then mark them
# initial in the per-runtime chain.
alembic -c agents/<runtime>/alembic.ini stamp head
```

The `alembic_version_<runtime>` row now points at a synthetic
"baseline" revision that captures the state inherited from the
shared chain. Future migrations land in the per-runtime chain.

#### 4.1.3 Update CI

- Add `make migrate-<runtime>` that runs `alembic -c
  agents/<runtime>/alembic.ini upgrade head`.
- Update CI workflow to run `up && down -1 && up` per runtime
  whenever `agents/<runtime>/migrations/**` changes. (Stage 5 item 5
  closure.)

#### 4.1.4 Update env.py removals

- Remove this runtime's `Base` imports from `migrations/env.py`.
- The global chain is now smaller; future global migrations only
  touch control plane + shared tables.

#### 4.1.5 Verify

- Fresh database: `make migrate-all-runtimes` (new aggregate target)
  brings up every runtime to head.
- Existing database: shared chain stamps the historical state; each
  runtime's new chain takes over from there.
- `alembic_version_<runtime>` row exists and matches the new chain's
  head per runtime.

#### 4.1.6 Document

- Add a row to `docs/guides/backend-boundaries.md` §3 noting the
  per-runtime migration owner.
- Update `docs/guides/operations.md` operational commands.

---

## 5. Rollback

Per `rollback-checklist.md` §4. The cutover is reversible at any step:

- If the new per-runtime chain breaks: drop the new
  `alembic_version_<runtime>` row, restore the runtime's tables from
  the pre-cutover `pg_dump`, and re-stamp on the legacy global
  chain.
- If only one migration in the new chain breaks: `alembic
  downgrade -1` on the per-runtime chain. The runtime keeps the
  per-runtime surface; only the bad migration reverts.

Do not run destructive operations against the legacy
`alembic_version` table during the cutover — both tables coexist
until the very last runtime is extracted.

---

## 6. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Two runtimes' migrations touch the same table (e.g. shared FK) | Medium | High — chain divergence | Catch in Stage 3 boundary tests; refuse cross-runtime ORM imports (#144) |
| `alembic_version_<runtime>` row not stamped | Low | High — fresh DBs miss runtime tables | CI test creates a clean DB and runs every runtime's chain |
| Operator runs the legacy `alembic upgrade head` after cutover | Low | Medium — drift between chains | Disable the legacy CLI entry point after the last runtime is extracted; document the per-runtime commands |
| Different runtimes need conflicting SQLAlchemy versions | Low | Low | All runtimes share one virtualenv; pin SQLAlchemy across `requirements*.txt` (already pinned) |
| Backfill scripts assume the global chain | Medium | Medium | Audit `scripts/` before the cutover; rewrite to call per-runtime targets |

---

## 6.1 Local Split-Deployment Smoke

`make split-deploy-<runtime>` brings up infra + one runtime as an
independent container using the `split-agents` Compose profile,
polls `/health/ready`, and runs an `/agent/request` smoke. It
satisfies the "non-prod deployment proves the split" half of
[`migration-plan.md`](./migration-plan.md) §Stage 4 pre-condition #4
without booking a remote staging environment.

```bash
# After make up-infra brings up Postgres/Redis/NATS/Milvus.
make split-deploy-dev
make split-deploy-qa
make split-deploy-pjm
make split-deploy-requirement
```

The script lives at `scripts/split_deploy_smoke.sh`. Exit codes:

- `0` — `/ready` returned 200 and `/agent/request` returned 2xx/4xx
  (any structured HTTP response proves the runtime is reachable).
- `1` — `docker compose up` failed.
- `2` — `/ready` did not return 200 within `SMOKE_TIMEOUT_SECONDS`
  (default 120 s).
- `3` — `/agent/request` returned an HTTP code outside 2xx/4xx
  (connection failure, timeout, or 5xx).

Operator override knobs:

- `RUNTIME` — agent ID (e.g. `dev-agent`).
- `SMOKE_TIMEOUT_SECONDS` — how long to wait for `/ready`.
- `PM_API_KEY` — internal-key header for the health probe.

For load-side verification, pair with `make load-smoke` (k6, 10
VUs). Together they cover the smoke + load half of pre-condition #4.

## 7. Sequencing Against Service Extraction

This work is the **first** Stage 4 step per the migration plan. It is
a no-op for operators (tables stay where they are) but unlocks every
later step:

- A runtime cannot be extracted (Stage 4 pre-condition #2) without
  its own migration chain.
- A new runtime container in staging (pre-condition #4) needs a
  per-runtime migration on bootstrap.
- The `migrate-<runtime>` make targets are the API that the
  release-checklist (§5) and rollback-checklist (§4) reference.

Once all runtimes have their own chain, the legacy `migrations/`
directory shrinks to control-plane + shared tables only; eventually
the global chain disappears.

---

## 8. Maintenance

When this document changes:

- Update `docs/architecture/migration-plan.md` §Stage 4 to match.
- Update `docs/guides/operations.md` if operator commands change.
- Update `docs/architecture/release-checklist.md` §5 if the gate
  changes.
- Update `docs/architecture/rollback-checklist.md` §4 if the rollback
  path changes.
