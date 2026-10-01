# Roadmap delivery closure engineering receipt

Verification date: 2026-10-01. Base revision:
`b585e849206c8a836449b2f26d745ab1d3a0a4a5` (merged native executor PR #397).
This receipt covers additional engineering and synthetic acceptance; it does
not certify FAANG affiliation, production readiness or all roadmap milestones.
The [machine-readable receipt](./roadmap-delivery-closure-2026-10-01.json)
freezes the changed source/configuration/documentation files by SHA-256.
Historical roadmap and native-executor receipts remain unchanged.

## Implemented behavior

- Reviewed Requirement Manager delivery maps a confirmed content hash to
  existing OpenProject IDs and company-local Goal/WorkItem IDs. Authenticated
  read-only Control Plane HTTP uses both operator and internal credentials.
  Immutable review receipts, unique work-package mapping and RM outbox commit
  together; replay/restart do not enqueue another request. PJM preserves the
  mapping through approval, and Dev stores trace metadata for QA/final events
  without adding it to AgentForge wire payloads.
- Default-off physical retention deletes eligible audit detail/published
  outbox payloads and expired knowledge pointers, while retaining pending and
  artifact-pinned evidence. Compact hashed-key replay receipts and permanent
  knowledge tombstones remain. Company locking prevents knowledge recreation
  during purge. Audit policy is at least 90 days; each batch inspects at most
  1,000 audit rows and 1,000 knowledge pointers. WAL/backups/source artifacts
  and native executor ledgers are outside this cleanup contract.
- Execution settlement now persists reported cost and estimate classification
  on the run in the same transaction as budget accounting.
- Integrated fixtures cover company-template/knowledge reuse, recurring
  scheduling/governance, paired evolution approval/release/regression rollback,
  retention races, and delivery handoff. The frontend retains FSD; a real
  browser drives its authenticated proxy to persisted work/run/artifact/cost/
  acceptance evidence. Independent widget queries are stubbed in its unit test
  so unrelated network retries cannot produce a spurious error assertion.

## Completed local checks

| Check | Result | Scope |
|-------|--------|-------|
| `make test-roadmap` with disposable PostgreSQL | 917 passed, no skips | Roadmap/governance/evolution/native receiver and new acceptance/domain/migration tests |
| Exact new PostgreSQL CI gate | 12 passed, no skips | Company reuse 1, paired evolution 1, recurring work 2, retention 7, RM handoff 1 |
| `make test-public` | 679 passed | Existing public regression suite |
| Architecture + runtime error + new migration guards | 252 passed | 236 architecture checks, 12 runtime error cases, 4 new migration cases |
| Dev unit tests | 181 passed | Trace persistence/recovery plus existing delivery regression |
| PJM unit tests + decomposition approval file | 159 + 14 passed | Company guard, persisted approved lineage, persistence failure before card/success |
| Frontend Vitest | 132 passed, 29 files | Existing operator/component tests with deterministic independent query fixtures |
| Playwright mocked workflow | 7 passed | Visible UI contracts for create/assign/run/denial/retry/approval/review/close |
| Playwright real API | 1 passed | Real Next proxy, operator/internal auth, restricted synthetic subprocess and isolated PostgreSQL |
| Mypy | 151 source files passed | Expanded explicit typed domain/port/adapter/API scope; not repository-wide typing |
| Ruff, ESLint, FSD, TypeScript, diff check | Passed | Required language and architecture checks |
| Production frontend build | Passed with `--webpack` locally | Managed sandbox blocks Turbopack internal port binding; CI retains the default build |
| PostgreSQL Alembic upgrade/down/upgrade | Passed | Separate empty disposable database, PostgreSQL GIN index and insert probe |
| Compose base + app configuration | Passed | Synthetic placeholder values; no deployment |
| Independent read-only boundary review | No remaining blockers | Fixed internal-key forwarding, knowledge purge/create race and duplicate mapping error handling |

CI now rejects missing/skipped collection for all 12 new PostgreSQL cases and
for the one real browser case, in addition to existing native/concurrency gates.
The frontend CI job provisions PostgreSQL and runs the default production build,
seven mocked cases and one authenticated real-API case. CI/CodeQL outcomes and
merge revision belong to the resulting PR; configured gates alone are not
recorded as completed remote results in this immutable local receipt.

## Interpretation and open acceptance

Every PostgreSQL fixture owns and drops only a fresh schema. Migration round-trip
uses a separate empty database. The browser backend has a synthetic company,
synthetic tokens and a restricted local subprocess reporting a declared cost;
no real model billing or customer workload is used. Local Playwright used
installed Chromium because the browser CDN download was forbidden; CI installs
Playwright's selected Chromium. No browser/API security guard was weakened.

Recurring work uses two deterministic due slots, contenders and fresh sessions;
it is not an observed multi-day pilot. Evolution uses 50 fixed paired synthetic
cases, injected regression and exact baseline restoration; it is not measured
live model improvement. The handoff checks real owner-local persistence and
HTTP contracts, with selected existing external IDs; it does not write to
OpenProject or prove a live RM→PJM→Dev→QA business outcome. Mocked browser cases
are UI contracts; the single real case does not cover live providers, external
QA, cancellation/restart or all approval/retry flows.

Live provider/platform conformance, observed recurring work, approved live
model experiments, broader organization reuse, target-environment retention/
restore sign-off, per-runtime migration cutover/Sync split and R0 deployment
acceptance remain open. R0 requires at least 14 continuous days and 1,000 actual
matching request samples, fixed revision, declared SLOs, daily coverage, replay/
rollback evidence and responsible-owner sign-off. No configured cloud identity
or deployment credentials were available. Synthetic fixtures cannot supply
those observations or authorize a production cutover.

Rollout, replay, irreversible cleanup and feature/schema rollback are documented
in the [delivery/retention runbook](../runbooks/roadmap-delivery-retention.md).
