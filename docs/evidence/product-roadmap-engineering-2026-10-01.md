# Product Roadmap Engineering Receipt — 2026-10-01

This change delivers the engineering surfaces for M0–M4 and R0 preparation.
The validated scope is local engineering behavior and synthetic fixtures.
Milestone acceptance remains separate: native four-runtime delivery,
provider/platform pilots, physical retention and realistic staging are open.
The machine-readable [validation receipt](product-roadmap-validation-2026-10-01.json)
binds the changed source/configuration inputs to their SHA-256 hashes.

| Area | Delivered behavior | Evidence and limits |
|---|---|---|
| M0 | First-success report CLI; durable goal, work item, role, run, artifact, cost and reviewer links; closure requires intact latest-run acceptance | Actual PostgreSQL + HTTP + subprocess report accepted; replay across app restart reused the existing run and decision. Report figures are synthetic; native software delivery remains open. |
| M1 | Company-ordered claims; bounded leases; approval bound to current input/configuration; concurrent budget reservations; explicit uncertain-effect recovery; authenticated scheduler worker | Fault tests cover single ownership, budget contention, heartbeat interval, revoked/changed approval, unknown HTTP effects and no automatic replay. Recurring-work pilot and physical audit retention remain open. |
| M2 | Versioned HTTP executor envelopes; empty allowlist by default; bounded timeout/response; trusted local subprocess adapter; process-group lifecycle controls | Real subprocess tests cover inherited-secret exclusion, timeout child cleanup, pause/resume and terminate. The process adapter is trusted-command development execution, not filesystem/network isolation for untrusted code. Native executor/platform conformance remains open. |
| M3 | Frozen comparative evidence; signed shadow/canary/promote/rollback commands; native owner CAS; receipt reconciliation and explicit expired-command recovery | HTTP/SQL tests plus real PostgreSQL replay, competing canaries, later-version rollback protection and expiry fencing. Default-off HTTP skill selection applies the actual frozen prompt/model/parameters through LLM Gateway, preserving budget checks and zero scores. No live model-quality result is claimed. |
| M4 | Secret-scrubbed versioned company templates including role hierarchy, goal ownership and budget references; imports paused and unprivileged; scoped knowledge lifecycle | Round-trip/collision/validation tests; provenance, owner/role ACL, optimistic versions, expiry and tombstones. Deployment-specific product reuse acceptance remains open. |
| FSD and DDD | Thin frontend routes; entity reads, feature mutations, composed widgets; pure domain policy, application ports, SQL/HTTP adapters and owned runtime contracts | FSD checks and executable architecture tests pass. Existing service boundaries remain independently deployable; no gratuitous service extraction is introduced. |
| Cloud and operations | Hardened HTTP scheduler worker; migration; low-cardinality metrics; authenticated opt-in Prometheus scrape; seven alert rules; evidence checker | Compose configuration and migration round trip pass. Prometheus file-header syntax is verified against v2.55.1; scraping, alert delivery and staging have not been deployed here. |

## Verification

- Roadmap suite: **854 passed**, including **7 real PostgreSQL tests**, no skips
  with the disposable PostgreSQL 18.6 database configured.
- Public regression suite: **679 passed**; architecture suite: **236 passed**.
- LLM Gateway regression suite: **15 passed**.
- Python Ruff passes across agents, shared code, tests, scripts and migrations;
  scoped strict Mypy passes for **136 source files**. This is not repository-wide
  type coverage.
- Frontend Vitest (**132 tests**), lint/FSD, TypeScript, production webpack build and two mocked
  Playwright workflows pass; the JSON receipt records the final test count.
  These browser tests use mocked backend responses, not a live distributed flow.
- Shared Alembic chain: upgrade head → downgrade base → upgrade head and
  PostgreSQL JSONB default insert probe pass in a separate disposable database.
- S4.1 Dev restore rehearsal: **13 checks passed**, including backup/restore,
  drift rejection, failure atomicity and preservation of other runtime tables.
  The final input fingerprint is recorded in the validation receipt. Historical
  [PR #395](https://github.com/Wisdoverse/Wisdoverse-Cell/pull/395) evidence remains intact.

## Actual synthetic report and restart evidence

The current-source report run is `run_01m3vhg02yew057db5xp1yyxjz`; its artifact
is `art_01m3vhg08vm2h6bj1jsm7m4f05`, with SHA-256
`16fec4bcb58fc3f546f5e0d613c5e637c5740e6b6faec26ffa8f64f3abaa455a`.
Review accepted the actual structured output; closure persisted. The linked
usage is $0.00 and explicitly marked actual, not an estimated ceiling charge.
Fixture-object setup took 0.212213 seconds; execution-to-output took 0.29428
seconds. These measurements exclude infrastructure setup and use an existing
company; they are not clean-install or production performance claims.

After restarting the app, checkpoint replay reused run
`run_01m3vghndddbw7vwywgfvypszj` and acceptance
`acc_ede700a1b7974cffad274cd7e662fe74`, without another execution.
The JSON receipt includes sanitized links and full payload hashes; it excludes
credentials, private endpoints and raw production data.

## Review and remaining acceptance

Independent review identified and corrected unrouted canary scoring, zero-score
inflation, duplicate trace accounting, expired-command recovery, stale ORM
ownership checks, and missing frontend internal authentication.
Final review also verified frozen baseline selection after rollback and that a
stale rollback cannot displace the current active release. The shared
architecture checklist applies; the PR records the large integrated scope and
remaining acceptance exceptions. No new cross-runtime database access or
unapproved service split is introduced by the HTTP execution/worker contracts.
Existing legacy migration/coupling closures still follow the canonical backend
migration plan.

Native Requirement Manager → PJM → Dev → QA delivery still needs a stable,
linked executor/handoff contract and real acceptance. The diagnostic CLI does
read-only health probes and explicitly reports completion as false. Live
provider/platform conformance, measured model improvements, an observed
recurring-work pilot, physical audit purge and R0 owner sign-off remain open.
R0 requires at least 14 days and 1,000 matching staging requests, declared SLOs,
restore and rollback evidence; the checker only qualifies evidence for review.

See the [governance runbook](../runbooks/product-governance.md),
[metrics runbook](../runbooks/control-plane-metrics.md), and
[canonical roadmap](../overview/roadmap.md).
