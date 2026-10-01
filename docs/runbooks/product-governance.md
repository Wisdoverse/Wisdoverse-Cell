# Product Governance Runbook

Status: implementation reference; product acceptance and production readiness
remain open. This runbook records control behavior visible in the repository,
not a certification or deployment approval.

## Operator identity and company scope

The Control Plane resolves an operator principal from server-side configuration
and checks its action and company scopes for each request. Production operator
configuration uses token SHA-256 hashes, actor IDs, company IDs, action scopes,
and optional role IDs. Never place a raw operator token in the request body,
database, logs, or documentation. The development board principal is a local
development override. It is not evidence of production identity configuration.

For any operation, confirm that the principal is authorized for the resolved
company and action. Knowledge reads additionally require the record owner or a
matching company-local reader role; company scope alone does not grant content
access. Audit export requires `audit:export` and applies an exact company
filter. The HTTP adapter allowlist defaults to empty, so remote HTTP execution
is disabled until an operator configures an explicit allowlist.

## Execution decisions and recovery

Execution approvals are bound to the intended inputs and request payload. A
changed intent requires a new matching approval, and approvals are consumed
once. Before dispatch, the budget ledger reserves the declared maximum cost.
When an attempt fails or has an uncertain outcome and measured cost is
unavailable, the reservation is charged conservatively.

An uncertain HTTP adapter result can represent a side effect that already
happened. Do not replay it automatically. The current execution path marks
uncertain outcomes for recovery and requires operator-reviewed handoff. The
scheduler worker's bounded retry applies to heartbeat polling only; it does
not retry an uncertain adapter action.

Local process execution uses an isolated temporary working directory, a
restricted environment, bounded execution time/output, and process-group
termination on timeout or cancellation. External HTTP execution has redirect
handling disabled and bounded request/response behavior. These controls reduce
exposure but do not establish native executor conformance or certify a runtime.

## Review and accept work

The first-success CLI currently demonstrates a synthetic report through a real
local process boundary. It is not a native four-runtime delivery acceptance.
Inspect the produced run and linked artifact, then use the explicit review
reason before accepting. Acceptance records the artifact hash and run and is
valid only while that run remains the work item's latest run. A later run
invalidates prior acceptance. Empty or placeholder output is not acceptable.

## Company templates and knowledge

Company template export/import scrubs secrets. Imported runtime roles start
paused and require explicit review before activation. Preserve semantic role
keys when reviewing an import; a successful serialization round trip alone is
not proof that the resulting operating model is correct.

Knowledge records point to an existing artifact in the same company. They
store a URI reference and provenance rather than copied raw content. Provenance
is immutable, role grants are checked against roles in that company, and
updates use optimistic expected-version checks. Expired and deleted records
are inaccessible. Owner deletion creates a durable tombstone; it does not
erase the audit history. Review source artifact, owner, granted roles, expiry,
and version before publication or revision.

## Evolution and audit evidence

Evolution release transitions use signed commands bound to a frozen release
snapshot. Shadow, canary, promotion, and rollback commands pass through the
approval gate; non-shadow transitions require an approved decision matching
the release snapshot. Fixed-case evaluation requires at least 50 samples in
each arm. This is a test protocol constraint, not a live-evolution performance
claim. Keep changes in shadow until evidence and the authorized approval are
available.

Task-time skill selection is a separate opt-in path, disabled by default with
`EVOLUTION_SKILL_EXECUTION_ENABLED=false`. If enabled, the traced LLM task
resolves its exact `agent_id:task_type.replace("_", "-")` selection from the
Evolution owner before budget estimation/provider dispatch. Verify the frozen
prompt/model/parameters hash and HMAC, and preserve the actual selected
version in the task-local trace. The Evolution-owned database deduplicates
observations; an unrouted task produces no live canary score. This is execution
plumbing, not proof of live provider performance or an accepted M3 pilot.

For pending release recovery, first use reconcile to retrieve and store a
receiver acknowledgement if one exists. Only use explicit recovery after the
command has expired and the receiver lookup returns definitive `404`. A
timeout, 5xx, or other unknown outcome is not grounds to resubmit. Recovery
uses command ID/payload compare-and-swap and refreshes the approval check for
non-shadow actions. Keep unresolved releases pending until a definitive
receipt or authorized recovery is possible.

Recovery lookup includes the frozen skill and both versions. The receiver waits
on the same ordered version locks as application before reporting a missing
receipt, and application rechecks expiry after obtaining those locks. This
fences an expired request that was already waiting to apply; a plain unlocked
receipt miss would not establish that an in-flight request is unapplied.

Audit export returns sanitized, company-filtered records for an explicit range
within 90 days and supports keyset pagination. It redacts secret-bearing keys
and credential patterns while retaining identifiers and hash linkage. The
90-day export query bound is not physical storage retention: purge and physical
retention enforcement remain pending.

## R0 evidence and owner review

The Next.js operator proxy is a board surface: every request requires an
authenticated administrator. Configure both its server-only operator token and
`CONTROL_PLANE_INTERNAL_KEY` (Compose defaults this to `INTERNAL_SERVICE_KEY`).
The proxy forwards both backend credentials and exposes neither to browsers.
Deploy a company-scoped operator grant appropriate to this board; the proxy
does not infer individual tenant membership from an application session.

Run `python scripts/check_operational_readiness.py --evidence <evidence.json> --report <report.json>` only after assembling owner-provided staging evidence. The checker validates inputs; it does not deploy, cut over, or manufacture observations. Engineering input must be marked as passed synthetic and bound to a revision plus source, configuration, migration, and evidence hashes. Staging evidence must identify the runtime and owner, cover at least 14 days and at least 1,000 matching requests, include declared thresholds and sampled metrics, have complete day coverage, and include a non-synthetic restore drill plus rollback readiness for the same revision. The command requires an operator to supply those records; do not fill gaps with estimates.

A successful report means only `eligible_for_production_cutover_review` and
continues to report `production_cutover: pending` and `deployed: false`. A
release owner must review the underlying evidence, deployment-specific
migration requirements, and rollback plan before any separate cutover
decision. Current repository status does not establish those acceptance
conditions.

## Review record

[Analysis] Product controls now cover operator scope, execution, reusable
knowledge, portability, evolution, and sanitized audit export across explicit
Control Plane boundaries.

[Risk:M] Code paths and tests show implementation behavior, but operator-flow
acceptance, native four-runtime conformance, live-evolution evidence, physical
audit retention, and R0 staging evidence remain unaccepted or pending.

[Fixes] Keep remote adapters disabled unless explicitly allowlisted; require
owner review for acceptance and release transitions; retain synthetic labels;
collect owner-supplied, hash-bound staging evidence and validate it with the R0
checker before requesting cutover review.
