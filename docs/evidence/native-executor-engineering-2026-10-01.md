# Native executor engineering receipt — 2026-10-01

Base revision: `1704d615cadcde311af80aaf85cdbcb0b994b39e`.
Scope: four native runtimes and the Control Plane HTTP executor boundary.
This receipt records local engineering validation, not deployment acceptance.

## Implemented behavior

A strict versioned request now translates nested native inputs through an
owner-local application use case, ledger port and SQL adapter. Each runtime
uses its own table and session. A dispatch intent commits before effects;
completed identical requests replay the stored receipt. Conflicting requests
and running/uncertain intents never automatically redispatch. Handler timeout,
cancellation, malformed output and receipt failure preserve uncertainty.

The feature defaults off; deployed startup checks require migrated schemas.
Legacy HTTP adapters omit the executor version header unless explicitly opted
into v1. Native acknowledgements are `recorded`, not accepted business outcomes.
Unmetered costs carry `cost_is_estimate: true` and settle conservatively against
the reservation ceiling. Nonempty ledger downgrade is refused; feature rollback
preserves rows. The [runbook](../runbooks/native-executor.md) documents rollout,
rollback, action allowlists and remaining delivery gaps.

## Local verification

| Check | Result | Scope |
| --- | --- | --- |
| Roadmap regression | 890 passed, no skips | Includes 15 real PostgreSQL ownership/concurrency cases |
| Public regression | 679 passed | Existing runtime/API behavior |
| Architecture, migration guard and error contracts | 253 passed | Service boundaries, portable DDL and standard errors |
| Focused native receiver, migration and HTTP regression | 35 passed | Four owner HTTP apps; synthetic business handlers |
| Strict mypy | 141 source files passed | Includes new executor modules |
| Ruff | Passed | Python sources, tests and migrations |
| PostgreSQL migration round trip | Passed | Full upgrade/downgrade/upgrade and QA JSONB probe |
| OpenAPI generation and Compose configuration | Passed | Four changed snapshots; configuration validation only |

PostgreSQL 18 ran in a task-owned disposable Docker container. Tests use isolated
schemas and separate sessions to verify claim contention, durable replay after
store restart, conflicting payload rejection and uncertainty preservation.
They do not certify live business handlers, platform integration or provider
performance. The migration guard separately verifies all four owner tables,
metadata parity and refusal to drop any nonempty ledger.

Independent read-only architecture review found a legacy header routing
regression; it was fixed and regression-tested. Re-review found no scoped blocker.
Real PostgreSQL is Docker-managed rather than testcontainers. No new bus events
or runtime extraction were introduced. Frontend is unchanged; its FSD boundary
remains mandatory.

## Open acceptance

Requirement confirmation still needs a validated mapping into OpenProject/PJM
and linked Dev/QA business delivery. Live providers, platform pilots, recurring
operation, physical audit retention and R0 staging observation/owner acceptance
remain open. Historical Dev S4.1 restore evidence excludes the new receipt
ledger; enabled deployments must extend backup/restore scope. No production
rollout or measured production SLO is claimed.

The adjacent JSON receipt fingerprints the changed source, configuration,
tests and reconciled documentation; evidence files are excluded from their own
fingerprint. CI and merge results are recorded in the pull request.
