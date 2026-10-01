# Reviewed delivery and physical retention

Last updated: 2026-10-01

These contracts complete additional engineering paths. Synthetic local and CI
checks do not establish external platform delivery, observed recurring work,
live model improvement, production erasure or R0 staging acceptance.

## Reviewed requirement delivery

Keep `DELIVERY_HANDOFF_ENABLED=false` until the configured company, operator
grants, Control Plane URL and internal service key have been reviewed in the
target environment. `DELIVERY_CONTEXT_BASE_URL` points to the independently
deployed Control Plane origin. No direct Control Plane table access is used.
The HTTP verifier forwards the operator token and server-configured
`X-Internal-Key`, has a 10-second timeout per GET, disables redirects and makes
one attempt per resource. Unavailability fails closed with a redacted error.

1. Confirm the requirement through its existing lifecycle. Read
   `GET /api/v1/requirements/{id}/delivery-review` with company-scoped
   `work:execute`. Review the returned content and retain its hash.
2. Select an existing OpenProject project/work-package and a company-local
   Control Plane Goal/WorkItem. Verify external identifiers on the platform;
   the mapping API verifies the Control Plane links only. Record a review reason.
3. Submit the version 1.0 mapping using
   `Idempotency-Key: requirement-delivery:{id}` and a bounded `X-Trace-ID`.
   Save the immutable queued receipt. A changed snapshot or mapping is a conflict;
   another requirement cannot reuse that company/project/work-package tuple.
4. Observe the RM outbox dispatcher and PJM decomposition. PJM approval remains
   required. Follow the trace through Dev's workflow log, QA acceptance and final
   task events; inspect artifacts and explicitly accept the business outcome.

Rollback disables the handoff flag and stops new submissions. It does not cancel
already-committed outbox messages or downstream work. Reconcile those through
their owning runtime and normal approval/cancellation procedures; do not delete
the receipt or replay an uncertain external action. Monitor dispatcher failures,
decomposition failures and HTTP context-verification errors using the existing
runtime logs/readiness and tracing. Logs omit tokens and reviewed content.

## Physical audit and knowledge retention

`CONTROL_PLANE_RETENTION_ENABLED=false` is the default. Preview does not require
enabling apply. The dedicated operator scope is `audit:retention`; company scope
must match exactly. Set `CONTROL_PLANE_AUDIT_RETENTION_DAYS` to 90–3,650; the
server determines the UTC cutoff. A batch inspects at most 1,000 audit records
and 1,000 knowledge pointers. This endpoint is an explicit operation, not an
automatically enabled background purge.

1. Back up the target database through the deployment's existing procedure and
   verify restore access. Confirm legal holds and the retention policy.
2. Preview `POST /api/v1/control-plane/retention` with
   `{"company_id":"cmp_example","batch_size":100,"dry_run":true}`.
   Inspect eligible counts and cutoff. Pending outbox messages and artifacts
   referencing `metadata.evidence.audit_events` pin their audit evidence.
3. Enable apply only for the reviewed deployment. Submit the same company and
   batch with `dry_run=false` and a unique 1–48-character `Idempotency-Key`.
   Archive the count-only receipt; an identical retry returns that receipt,
   while changing the body under the same key conflicts.
4. Inspect the `retention.applied` audit entry and remaining eligible counts.
   Repeated batches need new keys. Monitor pinned/pending backlog through the
   existing audit/outbox inspection tools. Do not release evidence pins without
   the responsible owner's retention decision.

The transaction serializes by company, deletes eligible audit detail and its
published outbox payload, and retains compact audit receipts with hashed
idempotency keys. Those permanent receipts prevent a replay from re-emitting an
old domain event; they retain business IDs, action, timestamps and a detail hash,
not original actor identity or raw detail. Historical timeline/export queries
do not include purged detail. New events and pinned evidence remain intact.
Expired knowledge pointers or deletion records beyond the audit age threshold
are removed with permanent knowledge tombstones. The source artifact remains.
Knowledge creation takes the same company lock before checking tombstones.

Disable the apply flag to stop further cleanup. Deletion of detail cannot be
undone by a flag: recovery requires a verified backup restore and reconciliation
of events/receipts created since that backup. Do not remove replay tombstones
to regain storage. PostgreSQL MVCC, VACUUM, WAL, replicas and backups need their
own retention/erasure policy; this API makes no physical-media erasure claim.
Native executor ledgers are outside this cleanup contract.

## Schema rollout and rollback

Migration `20261001_delivery_retention` follows
`20261001_native_executor_receipts`. It adds the RM mapping, two Control Plane
receipt tables, the mapping uniqueness constraint and a PostgreSQL GIN index for
artifact evidence pins. Deploy the additive schema before enabling either flag.
Existing runtime health/readiness, graceful shutdown and external configuration
remain unchanged. The legacy global Alembic chain is retained; this change does
not promote the separate Dev migration candidate to production cutover.

Empty-schema upgrade/down/up is tested. Downgrade checks all three receipt tables
before dropping anything and refuses if any contains durable state. Use feature
rollback with the additive schema retained after real traffic. Schema removal
requires separately reviewed archival/restore procedures; never clear durable
tables just to force downgrade.
