# Rollback Checklist

Last updated: 2026-05-18

Status: Foundation document. Stage 5 deliverable per
[`migration-plan.md`](./migration-plan.md) §Stage 5 item 9.

Pair document for [`release-checklist.md`](./release-checklist.md).
Every release MUST have an answer for "if this fails, how do we get
back to a known-good state?" before it ships. This document defines
the per-area rollback playbook.

---

## 1. Decision Framework

Before reverting, classify the failure:

| Class | Symptom | First move |
|-------|---------|------------|
| 1. Build / deploy failure | New images do not start | Stay on previous image; no rollback needed |
| 2. Smoke-test failure | `/ready` fails; one runtime cannot start | Revert the offending PR; redeploy |
| 3. Runtime regression | Error rate or latency breach; functionality broken | Revert the release tag; redeploy previous |
| 4. Data corruption | Migration applied; rows are wrong | Stop writes; assess scope before rollback (see §4) |
| 5. Security incident | Unauthorized access, leaked secret | Treat as incident first; rollback after containment |

Class 1–3 follow §2. Class 4 follows §4. Class 5 follows
[`docs/guides/incident-response.md`](../guides/incident-response.md).

---

## 2. Code Rollback (Class 1–3)

For a release composed of merged PRs on `main`:

```bash
# Step 1: Identify the last known-good release commit.
git log --oneline main | head -20

# Step 2: Choose one of the rollback strategies.
```

### 2.1 Revert the release commits

Preferred when the regression came from a small subset of PRs.

```bash
# Revert the squash-merge commits in reverse order (newest first).
git revert -m 1 <merge_sha_N> <merge_sha_N-1> ... <merge_sha_1>
git push origin HEAD
```

- [ ] Each revert is its own commit with a clear message referencing
      the original PR.
- [ ] CI green on the revert branch before push.
- [ ] On-call notified; release issue updated with the revert PR
      number.

### 2.2 Reset deployment to the previous tag

Preferred when the entire release is bad.

```bash
# Re-tag previous-good commit; redeploy.
git tag -a v<previous> -m "rollback target"
git push origin v<previous>

# Re-pull and restart Compose with the previous image tag.
docker compose pull
docker compose up -d
```

- [ ] Verify image digest matches the previous-good release.
- [ ] Confirm `/ready` healthy on every runtime.
- [ ] Confirm outbox lag returns to baseline after one dispatcher
      cycle.

### 2.3 Per-runtime rollback (Stage 4 split deployments only)

Once a single runtime is extracted from the bundled `cell` topology:

- [ ] Revert only the offending runtime's container to the previous
      image.
- [ ] Other runtimes stay on the current release.
- [ ] EventBus consumers must handle mixed versions; verify
      `schema_version` compatibility before splitting versions.

---

## 3. Configuration Rollback

For configuration-only releases or environment-variable changes:

```bash
# Restore the previous env file from the backup.
cp .env.backup .env
docker compose restart <affected_service>
```

- [ ] `.env.backup` was captured before the release (this is part of
      the release checklist).
- [ ] Production secrets are not committed; the restore reads from
      the previous deployment's secret store.
- [ ] Confirm `/ready` healthy after restart.

---

## 4. Data Rollback (Class 4)

Migrations are the riskiest part of any release. The default policy
is **additive migrations** — new columns nullable, new tables empty,
no in-place data mutation. Stage 4 introduces per-runtime migrations;
until then, all migrations share one directory.

### 4.1 Reversible Alembic Migration

```bash
# Step 1: Stop write traffic to the affected runtime.
docker compose stop <runtime>

# Step 2: Downgrade.
docker compose exec cell alembic downgrade -1

# Step 3: Verify schema state.
docker compose exec postgres psql -U wisdoverse_cell -d wisdoverse_cell -c "\d <affected_table>"

# Step 4: Restore the previous image (per §2.2 or §2.3).
```

- [ ] The migration's `downgrade()` was tested on staging.
- [ ] No data was destroyed; if rows were transformed, the original
      values are recoverable from `pg_dump` taken before the
      release.

### 4.2 Destructive Migration (DROP TABLE / DROP COLUMN)

If the migration destroyed data:

- [ ] STOP. Notify on-call.
- [ ] Restore from the pre-release `pg_dump`.
- [ ] Replay events from `<runtime>_event_outbox` if necessary to
      re-derive state in downstream tables.
- [ ] Do not redeploy the offending migration without a fresh
      cutover plan.

This case is rare by design. Migration Plan §Stage 4 and
[`data-ownership.md`](./data-ownership.md) §4 require an explicit
cutover plan for destructive migrations.

### 4.3 Backfill Rollback

If a backfill script wrote bad values:

- [ ] Pause the backfill (it should be re-runnable and idempotent).
- [ ] Restore the affected rows from `pg_dump` or from a
      timestamped audit-event replay.
- [ ] Fix the backfill, re-run; idempotency means the second run
      converges on the correct state.

---

## 5. Event Rollback

If a release published events that downstream consumers cannot
process:

```bash
# Step 1: Stop the offending producer.
docker compose stop <runtime>

# Step 2: List the bad events on the dlq.failed stream or in the
# runtime's outbox.
docker compose exec redis redis-cli XLEN dlq.failed

# Step 3: Mark the bad outbox rows as failed so they do not retry.
docker compose exec postgres psql -U wisdoverse_cell -d wisdoverse_cell -c \
  "UPDATE <runtime>_event_outbox SET status='failed', last_error='rolled_back'
   WHERE event_id IN ('<bad_id_1>', '<bad_id_2>');"

# Step 4: Publish a corrective event manually if business correctness
# requires it.
```

- [ ] No bad event is replayed silently.
- [ ] Every consumer of the affected event_type has been notified.
- [ ] If `schema_version` was bumped, both producer and consumer
      versions are reconciled before lifting the pause.

---

## 6. Frontend Rollback

For Next.js frontend releases:

- [ ] Re-deploy the previous frontend container tag.
- [ ] Confirm that the API contracts the previous frontend expects
      are still served by the current backend release.
- [ ] No client-side caching pinned to the new release shape.

---

## 7. Post-Rollback

- [ ] Release issue updated with rollback timestamp + cause.
- [ ] Incident post-mortem scheduled per
      `docs/guides/incident-response.md` §4.2.
- [ ] CHANGELOG updated to reflect the actual deployed state.
- [ ] Tests added to prevent regression of the specific failure mode.
- [ ] Follow-up release planned only after the regression test
      gates the affected code path.

---

## 8. Anti-Patterns

- Rolling back code without rolling back the matching configuration
  (or vice versa).
- Re-running a destructive migration in "the other direction" without
  validating the downgrade path on staging.
- Replaying events from `dlq.failed` without fixing the consumer
  first — that just refills the DLQ.
- Force-pushing a "fixed" branch over `main` instead of creating
  revert commits.
- Skipping the post-rollback regression test because "the rollback
  worked".

---

## 9. Maintenance

When this document changes:

- Update [`release-checklist.md`](./release-checklist.md) §9 if the
  rollback path that the release issue references changes shape.
- Update `docs/guides/operations.md` if the operator commands
  change.
- Update `docs/guides/incident-response.md` if a new failure class
  warrants its own playbook.
