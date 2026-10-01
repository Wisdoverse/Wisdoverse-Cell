# Dev Migration S4.1 Engineering Evidence

Date: 2026-10-01
Scope: synthetic PostgreSQL engineering acceptance for the rehearsal-only Dev
candidate baseline
Status: Passed for the synthetic engineering scope; operational rollout
acceptance remains pending.

## Environment and result

The rehearsal passed against PostgreSQL 18.6 in a disposable local Docker
database. It exercised the frozen candidate baseline against independently
materialized legacy Dev DDL in an isolated generated schema. The legacy global
Alembic chain remains the active migration owner.

All 13 runner checks passed, including fresh upgrade/downgrade/upgrade,
ownership and schema parity, synthetic task/log/outbox preservation through
stamp rollback/restamp, separate version tracking, legacy and outside-runtime
sentinel preservation, injected version-plus-DDL failure rollback, actual
missing-index drift rejection, refusal of inherited destructive downgrade,
custom-format `pg_dump`, complete synthetic schema loss, `pg_restore` with a
single transaction, post-restore schema/data comparison and tracking
rollback/restamp, source fingerprint stability, and final schema cleanup.

Final verification on 2026-10-01:

| Gate | Result |
|------|--------|
| PostgreSQL 18.6 synthetic rehearsal | All 13 checks passed |
| Candidate unit and PostgreSQL integration suites | 14 unit + 15 integration tests passed |
| Migration, unit/integration and architecture-boundary suites | 268 passed (includes the 29 candidate tests) |
| Public regression (`make test-public`) | 678 passed (includes candidate unit tests) |
| Legacy shared-chain PostgreSQL round trip | Upgrade → downgrade → upgrade and JSONB default insert probe passed |
| Scoped Mypy | 88 source files passed, including all four candidate paths |
| Ruff and changed Python formatting | Passed |
| Documentation links and `git diff --check` | Passed |

The full public suite ran with a 30-second per-test timeout. The existing
local HTTP TestClient test stalled inside the default filesystem/network
sandbox, passed independently with local process access, and then the full
public suite passed with that access. No test was skipped to obtain this result.
Test counts above overlap and must not be added together.

- Source base commit: `c3878771b242b8003c1c7aace6a7767a5604cdc6`.
- Verified input SHA-256: `e5c29adad52427a86b27035707c73e0c7619880f6679ba7b8a0fc4b833a16f47`.
- Worktree state: uncommitted feature-branch changes (`feat/dev-migration-rehearsal`).
- Evidence time: `2026-10-01T08:13:05.721613+00:00`.
- Machine-readable report: `.artifacts/s41-dev-postgresql.json`; a sanitized
  snapshot is retained at [dev-migration-s41.json](./dev-migration-s41.json).

The input fingerprint binds the candidate, runner, legacy DDL, tests, Makefile,
Mypy scope and CI configuration. The runner verifies it is unchanged before
accepting the result. Later code changes require a new run; this record does
not establish a GitHub CI result or a different deployed revision.

The generated JSON report is written by default to
`.artifacts/s41-dev-postgresql.json`. It records the base commit, worktree
dirty flag, SHA-256 fingerprint of the input files, check statuses and
PostgreSQL server version. The report is machine-readable and excludes
connection URLs, credentials and synthetic row payloads. Do not copy private
deployment details or raw production evidence into this public record.

## Acceptance boundary

This record accepts the synthetic PostgreSQL engineering behavior of the
candidate. It does not authorize or record a production cutover, production
data rehearsal, staging deployment, operator backup sign-off, observation
window or production acceptance. Production-copy validation and all physical
cutover preconditions remain pending. Stage 4 remains partial until each
selected runtime completes its own staging and release acceptance.

This change has no public API contract or event-payload change. Candidate
migration ownership has not replaced the legacy chain.
