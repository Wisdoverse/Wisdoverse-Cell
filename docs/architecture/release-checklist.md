# Release Checklist

Last updated: 2026-05-18

Status: Foundation document. Stage 5 deliverable per
[`migration-plan.md`](./migration-plan.md) §Stage 5 item 8.

This checklist runs before any production-like deployment. It is a
superset of the per-PR
[`architecture-review-checklist.md`](./architecture-review-checklist.md)
— individual PR reviews check structural correctness; this checklist
gates the cumulative diff that is about to ship.

Copy the checklist into the release issue / RFC. Answer every item. If
an item does not apply, write "n/a" with a one-line reason.

---

## 1. Scope

- [ ] Release tag and version match the change in `VERSION` /
      `CHANGELOG.md`.
- [ ] CHANGELOG entries cover every user-visible behavior change.
- [ ] PR list is enumerated in the release issue; each PR has a
      one-line summary.
- [ ] No PR in the release set has unaddressed reviewer comments.

## 2. CI Gates

- [ ] CI green on the release commit on `main` (all 10 workflows:
      Public hygiene, Python lint + tests, Rust gateway tests,
      Agents image smoke build, Frontend lint/tests/audit, CodeQL ×
      4).
- [ ] `tests/unit/test_architecture_boundaries.py` green.
- [ ] `tests/control_plane` green.
- [ ] No CI step skipped without an explicit override note.

## 3. Public Contract

- [ ] No breaking change to `/api/v1/*` shapes (or, if there is one,
      it ships under `/api/v2/*` and `/api/v1/*` continues to serve).
- [ ] No breaking change to integration event payload schemas (or,
      if there is one, `schema_version` was bumped on the producer
      and consumer-side contract tests pass for both versions).
- [ ] Per-agent OpenAPI snapshots under `docs/api/openapi/` match the
      route shapes that will be live.
- [ ] `X-Error-Code` enum in `shared/api/errors.py` matches the
      values documented in `docs/guides/api-reference.md`.

## 4. Configuration and Secrets

- [ ] No production secret committed in the diff (re-scan with the
      existing secret-detection step).
- [ ] `.env.example` reflects every new required environment
      variable.
- [ ] No removal of an existing environment variable without a
      deprecation window and operator notice.
- [ ] Production deployment will set every required secret to a
      non-empty value (failing-closed defaults still hold).

## 5. Data and Migrations

- [ ] Every new Alembic migration in this release runs cleanly
      (`alembic upgrade head`) and cleanly reverts
      (`alembic downgrade -1`) on a fresh database.
- [ ] No destructive migration without an explicit cutover plan
      attached to the release issue.
- [ ] Every new or renamed table has a row in
      `docs/guides/backend-boundaries.md` §3.
- [ ] Backfill scripts (if any) are idempotent and have been dry-run
      against a copy of production data.

## 6. Boundary and Architecture

- [ ] The Architecture Review section of the PR template was
      completed for every PR that checked the "Architecture boundary
      touched" risk box.
- [ ] No new `AsyncSession` leaks into route handlers.
- [ ] No new cross-runtime ORM imports (architecture-boundary tests
      `test_only_control_plane_imports_control_plane_orm` and
      `test_capabilities_do_not_cross_import_each_other` still pass).
- [ ] No new direct `anthropic`/`openai`/etc. SDK imports outside
      `shared.infra.llm_gateway`.
- [ ] No new module under `shared/services/*` or root `skills/*` —
      compatibility surfaces only retire, not grow.

## 7. Observability

- [ ] New metrics in this release follow the naming + cardinality
      rules in [`observability-guidelines.md`](./observability-guidelines.md)
      §5 (no high-cardinality labels).
- [ ] Outbox dispatcher metrics still cover all 10 runtimes
      (regression check: `wisdoverse-cell_outbox_dispatch_events_total`
      reports a value for each canonical runtime label).
- [ ] Alertmanager rules for outbox lag, DLQ rate, LLM budget breach,
      `/ready` failure are still wired (per
      [`observability-guidelines.md`](./observability-guidelines.md) §6).
- [ ] Every new alert in this release has a matching playbook in
      [`docs/guides/incident-response.md`](../guides/incident-response.md).

## 8. Security

- [ ] Webhook signature verification still active on every
      `/webhook/*` route.
- [ ] No log line includes secrets, tokens, signatures, or raw PII.
- [ ] DSAR export and delete paths still require internal
      authentication.
- [ ] CodeQL findings for this release are at 0 unresolved
      high/critical.

## 9. Operations

- [ ] Docker image builds reproducibly (Compose `make build` succeeds
      on a clean checkout).
- [ ] Rollback path is documented (see
      [`rollback-checklist.md`](./rollback-checklist.md)) and is
      reachable from the release issue.
- [ ] On-call is informed of the release window and has the
      `operations.md` runbook handy.
- [ ] `make load-smoke` runs green against the staging deployment.

## 10. Sign-Off

- [ ] Release engineer signed off.
- [ ] Architecture-review owner signed off (any "Architecture
      boundary touched" PR included).
- [ ] Security owner signed off (any security-affecting PR included).
- [ ] On-call signed off and confirmed availability for the release
      window.

---

## Exceptions

When a box above cannot be checked, the release issue records:

- Which item is unchecked.
- Why this release is shipping anyway (operator decision + risk
  assessment).
- Compensating control (extra monitoring, accelerated rollback,
  external comm).
- A follow-up task to close the gap before the next release.

A release with unchecked items proceeds only with explicit operator
sign-off.

## Maintenance

When this document changes:

- Update the linked
  [`rollback-checklist.md`](./rollback-checklist.md) for any
  reversibility implication.
- Update `docs/guides/operations.md` if the operator surface changes.
- Update `docs/architecture/architecture-review-checklist.md` if a
  per-PR rule changes.
