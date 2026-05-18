# Per-Runtime Migration Cutover Plan

Last updated: 2026-05-18

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

## 3. Pre-conditions

The following MUST hold before this work begins:

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
