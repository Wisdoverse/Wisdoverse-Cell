# Backend Migration Plan

Last updated: 2026-10-01

Status: Maintained backend implementation roadmap. Canonical six-stage
execution plan for [Backend Target Architecture](./backend-target-architecture.md)
§5. The [Product Roadmap](../overview/roadmap.md) owns project delivery order;
this plan owns architecture status and extraction acceptance gates.

## Current Baseline

This review uses main at commit c387877 (2026-10-01). Implementation status
is based on tracked source, CI configuration, and the
[DDD Compliance Audit](./ddd-compliance-audit.md). No staging observation,
production telemetry, or release sign-off was reviewed for this update.

[PR #393](https://github.com/Wisdoverse/Wisdoverse-Cell/pull/393) supplies a
tested engineering baseline: six CI and four CodeQL jobs passed on a tree
identical to this main revision. See the
[Product Roadmap baseline](../overview/roadmap.md#verified-baseline-and-open-acceptance)
for exact run references and coverage limits. Deployment acceptance remains
pending.

For the 2026-10-01 implementation snapshot across product milestones, see the
[Product Roadmap engineering snapshot](../overview/roadmap.md#engineering-delivery-snapshot-2026-10-01)
and [engineering receipt](../evidence/product-roadmap-engineering-2026-10-01.md).
Operational boundaries are in the [product governance](../runbooks/product-governance.md)
and [Control Plane metrics](../runbooks/control-plane-metrics.md) runbooks.

**Implemented** means the capability is represented in the repository.
**Accepted** requires dated verification for the target revision and environment.
Code closure, a configured CI job, or a checklist alone does not establish
deployment acceptance.

| Stage | Implementation status | Repository evidence | Remaining acceptance |
|-------|-----------------------|---------------------|----------------------|
| 0. Architecture docs and standards | Implemented | [Foundation index](../INDEX.md#architecture), [review checklist](./architecture-review-checklist.md) | Maintain reconciliation when contracts change |
| 1. Code structure cleanup | Implemented | [Control Plane composition](../../shared/control_plane/api.py), [routers](../../shared/control_plane/api_routes/), [boundary tests](../../tests/unit/test_architecture_boundaries.py) | Run current regression gates for affected changes |
| 2. Core domain modeling | Implemented for the audited scope | [DDD audit](./ddd-compliance-audit.md#2-executive-summary) records 22/22 remediation rows closed at code-architecture level | Promote additional aggregates when new invariants justify them |
| 3. Data ownership and boundaries | Implemented at code level | [Analysis projections](../../shared/capabilities/analysis/), [Identity write owner](./identity-boundary.md), [Chat Agent](../../agents/chat_agent/), boundary tests | Verify migrations, projection freshness/backfill and deployment compatibility for each rollout |
| 4. Service boundary evolution | Partial; deployment acceptance pending | [Migration cutover plan](./per-runtime-migrations.md), [OpenAPI snapshots](../api/openapi/), [Sync split ADR](../adr/0009-sync-sub-runtime-split.md) | Physical migration cutover, staging observations, replay and rollback rehearsal |
| 5. Engineering quality | Partial; several gates configured | [CI](../../.github/workflows/ci.yml), [Mypy scope](../../pyproject.toml), [CodeQL](../../.github/workflows/codeql.yml), [release](./release-checklist.md) and [rollback](./rollback-checklist.md) checklists | Route-level contracts, broader type coverage and verified operational gates |

The public Identity API remains a future extraction prerequisite. Stage 3
closure means a single internal write owner, not an implemented public
user/profile API. The Chat Agent gateway boundary is implemented per
[ADR-0010](../adr/0010-chat-agent-runtime-extraction.md); staging parity and
runtime isolation still need deployment evidence.

## Next Delivery Priorities

Responsibility below describes a role, not an assigned person. Assignment and
release dates remain open until a delivery issue records them. Public issues
carry sanitized acceptance summaries; restricted operational evidence stays
in its authorized system.

| Priority / item | Deliverable | Responsible role | Dependency | Exit evidence |
|-----------------|-------------|------------------|------------|---------------|
| P0 / M0 / S5.4 | Validate the task operation flow and its boundary contracts | Product maintainer + runtime maintainer + QA | Existing work-item commands, operator surfaces and execution gates | Create → assign → real run → QA/required approval → accepted artifact → close; failure/recovery and durable goal/cost/audit links |
| P1 / M1–M3 | Reliable scheduling, policy enforcement, executor conformance and integrated evolution | Relevant runtime/product maintainer + operator | M0 evidence; M1 gates before wider execution or live experiments | [Product milestone criteria](../overview/roadmap.md#delivery-order); route/event contracts, fault cases and comparative evaluation |
| R0 / S4.1 | Rehearse per-runtime migration cutover for Dev, or QA if its readiness evidence is stronger | Runtime maintainer + release operator | Stage 3 code boundaries; [physical cutover pre-conditions](./per-runtime-migrations.md#3-pre-conditions) | Dev synthetic PostgreSQL engineering scope passed: schema/ownership parity, backup-loss-restore, tracking rollback/restamp, failure guards and source-fingerprinted evidence; production-copy validation and operational cutover sign-off remain pending |
| R0 / S4.2 | Accept one independent runtime in staging when extraction is justified | Release operator + runtime maintainer | S4.1; contracts, outbox, replay, idempotency and dashboards ready | At least two weeks of realistic staging load within declared SLOs; successful replay and rollback |
| R0 / S4.3 | Complete the planned Sync deployment split under ADR-0009 when its gates pass | Sync maintainer + release operator | Per-side migration readiness, projection compatibility, baseline observations | Dual-write parity, per-side dispatcher verification, two-week staging observation and tested compatibility fallback |

M0 moves first in project delivery order; it can be accepted in the bundled,
trusted-development topology. R0 preparation proceeds alongside it and still
blocks production-like promotion. S4.1/S4.2 establish the extraction pattern;
S4.3 remains the already-decided Sync split with its own ADR pre-conditions.
Each selected runtime requires its own acceptance; product progress does not
waive any migration, staging or rollback gate.

---

## Stage 0 — Architecture Docs and Standards

- **Goal**: maintain the contract for subsequent work.
- **Delivered scope**: foundation documents, index, repository constitution
  references, architecture and release review checklists.
- **Risk**: low for documentation; inaccurate status can misdirect delivery.
- **Verification**: `git diff --check`, internal links and sibling-document
  reconciliation. Documentation-only changes use these checks.
- **Done criteria**: docs are available and aligned; status changes cite
  repository evidence and identify pending acceptance.

## Stage 1 — Code Structure Cleanup

- **Goal**: keep module boundaries explicit and use cases observable.
- **Delivered scope**: domain packages and canonical lifecycle paths;
  per-surface Control Plane routers; store factories and explicit command UoWs;
  use-case logging; retirement of compatibility import roots.
- **Risk**: medium for future moves or internal port changes.
- **Verification**: run `make test` (`make test-public`), affected runtime suites,
  architecture-boundary tests and HTTP smoke when code changes. Record current
  results and exclusions; the original 1860-test count is historical evidence,
  not the current regression target.
- **Done criteria**: touched boundaries pass current regression checks and
  preserve their documented public contracts.

## Stage 2 — Core Domain Modeling

- **Goal**: keep invariants and lifecycle decisions on domain objects.
- **Delivered scope**: typed aggregates/value objects, FSMs, domain events,
  transaction policies and matching tests for the tracked DDD remediation.
  The audit records 22/22 code-level closures; deployment remains in Stage 4.
- **Risk**: medium for future FSM or invariant changes.
- **Verification**: aggregate and use-case tests cover legal/illegal
  transitions, durable outcomes and collected events.
- **Done criteria**: product-owning contexts enforce actual invariants through
  domain objects. Simple records gain aggregates when behavior requires them;
  additional class moves are not a delivery milestone.

## Stage 3 — Data Ownership and Boundaries

- **Goal**: preserve one write owner and explicit cross-boundary read contracts.
- **Delivered scope**: Analysis report/milestone projection ports and tables;
  Identity write owner and PII-safe outbox; infrastructure-private ORM rows;
  Chat Agent ownership of chat product state; gateway HTTP adapters and
  executable cross-runtime import rules.
- **Risk**: medium-high for migration, backfill and compatibility changes.
- **Verification**: migration round trips, projection event contracts,
  idempotent backfill/replay and architecture tests for affected code.
  Rollouts also verify projection freshness and read parity on sanitized data.
- **Done criteria**: Analysis consumes projection ports, Identity has one
  documented internal write owner, and gateways do not own Chat Agent product
  state. A public Identity API is required before extracting that boundary.

## Stage 4 — Service Boundary Evolution

- **Goal**: prove independent operation for ready runtimes.
- **Status**: code seams and playbooks exist; acceptance is pending.
- **Scope**:
  1. Adopt per-runtime migration surfaces and version-table ownership per
     [Per-Runtime Migrations](./per-runtime-migrations.md). Start with Dev;
     QA is an alternative when its readiness evidence is stronger.
  2. Verify remote EventBus consumption, idempotency, outbox recovery, replay,
     DLQ handling and provider/consumer contracts for the selected runtime.
  3. Keep per-agent OpenAPI snapshots aligned with deployed routes.
  4. Exercise separate-container staging operation, dashboards and rollback.
  5. Execute the Sync split per [ADR-0009](../adr/0009-sync-sub-runtime-split.md):
     establish the existing-runtime baseline, validate dual-write parity and
     per-side dispatchers, then split containers. Retire the legacy runtime
     only after the ADR's observation and compatibility windows are satisfied.
     Existing runtime IDs remain stable; new IDs follow the ADR's catalog and
     constitution reconciliation before activation.
  6. Verify Chat Agent deployment read/write parity and gateway HTTP routing
     per [ADR-0010](../adr/0010-chat-agent-runtime-extraction.md).
- **Risk**: high. Independent migrations, duplicate delivery and split topology
  introduce operational failure modes even with code-level closure.
- **Verification**:
  - Evidence all [service split pre-conditions](./service-boundaries.md#1-default-posture)
    and runtime-specific ADR pre-conditions.
  - Record at least two weeks of realistic staging load after cutover, with
    declared request latency/error, outbox age, DLQ, projection freshness and
    LLM-cost thresholds. Record thresholds and observation dates before acceptance.
  - Rehearse worker recovery, duplicate events, replay and rollback; confirm
    durable task/run state and no duplicate business effects.
- **Done criteria**: S4.2 accepts the first independent runtime. Stage 4 remains
  partial until each selected cutover, including S4.3, has its own acceptance
  evidence and release-checklist sign-off.

## Stage 5 — Engineering Quality

- **Goal**: preserve code boundaries and verify operator-visible behavior.
- **Status**: continuous work alongside Stage 4. Cutover-critical quality
  checks must pass before that cutover is accepted.
- **Scope and remaining work**:

  | Item | Implemented baseline | Next verification or extension |
  |------|----------------------|--------------------------------|
  | 1. CI | Python, Rust, frontend and image jobs configured | Record current results, runtime coverage and exclusions on the target revision |
  | 2. Lint | Ruff, frontend lint and Rust formatting/Clippy configured | Keep affected paths clean and document supported exceptions |
  | 3. Type checking | `make typecheck` runs Mypy over the explicit `pyproject.toml` file list | Expand ports, use cases and runtime paths incrementally; coverage is not repository-wide |
  | 4. Tests and task flow | Regression, domain, boundary, event and operator-surface tests exist | Add route-specific HTTP/provider-consumer contracts; validate S5.4, including policy denial, approval, timeout and recovery |
  | 5. Migration checks | CI runs `make migration-test` against PostgreSQL | Cover new per-runtime chains and cutovers; a shared-chain round trip alone does not verify extraction |
  | 6. Dependencies | Dependabot, Python audit and frontend audit configured | Triage actionable alerts and verify issue/release handling |
  | 7. Security/privacy | Scheduled CodeQL and existing privacy/secret tests | Review affected public artifacts and remediation; record the actual review scope, cadence and ownership |
  | 8. Release | Release checklist documented | Attach dated completion to the selected release |
  | 9. Rollback | Rollback checklist documented | Rehearse the actual runtime/data/event path in staging |
  | 10. Incident response | Outbox, DLQ and budget runbooks documented | Verify alert routing, thresholds and recovery drills for the selected topology |

- **Risk**: low to medium for gate expansion; failed recovery or missing
  contracts can block release.
- **Verification**: relevant CI results plus staging drills for operational
  changes. Documentation-only changes use Stage 0 checks.
- **Done criteria**: affected architecture and operator flows pass applicable
  checks with current evidence. Remaining coverage stays explicit as the
  product grows.

## Cross-Stage Rules

1. Stage 0–3 code boundaries are prerequisites for extraction. Verify them
   on the target revision before each Stage 4 cutover.
2. Stage 5 may proceed alongside Stage 4; release-critical checks cannot be
   deferred until after deployment acceptance.
3. Deliver cohesive boundary or operator-flow changes. Each implementation
   PR cites its stage, scope, dependencies, verification and remaining work.
4. Reverts reopen affected milestones and dependent acceptance claims,
   rather than resetting unrelated completed work.
5. Public progress records contain source/PR references, responsibility
   roles and sanitized results. Keep personal contacts, credentials, internal
   infrastructure links, raw production logs and customer data out of the
   repository. Restricted evidence stays in its authorized system; only its
   sanitized outcome belongs in public docs.

### S4.1 Engineering Evidence — 2026-10-01

Dev has a [rehearsal-only candidate migration surface](../../agents/dev_agent/migrations/)
and [isolated runner](../../scripts/dev_migration_rehearsal.py). The actual
PostgreSQL 18.6 synthetic rehearsal passed all 13 runner checks, including
`pg_dump`, full generated-schema loss, `pg_restore`, post-restore stamp
rollback/restamp, injected transactional failure, real drift rejection and
verified cleanup. See the [S4.1 evidence record](./evidence/dev-migration-s41.md)
for scope and the location/fields of the machine-readable report. The
record includes final gate counts, source commit, input fingerprint and worktree
state from the verified input snapshot. The legacy
chain remains the active migration owner.

The synthetic engineering scope is complete. Production-copy validation,
physical cutover preconditions, cutover scheduling, operator backup sign-off,
staging observation and production acceptance remain pending; these are not
inferred from the synthetic checks. See [candidate scope and ownership](./per-runtime-migrations.md#21-dev-s41-engineering-acceptance).

Merge-status note: the S4.1 rehearsal work merged as PR #395 at
`42b06d0c1a9de9f2878ead1b0b5c6d011979a0f4`. This records the merge of the
S4.1 synthetic engineering scope only. It does not report a new S4.2 staging
observation or change the Stage 4 exit criteria above.

## Acceptance Record

For each pending milestone, record target commit, status, responsible role,
dependencies, verification date, observation interval, check results, declared
SLOs, rollback outcome and remaining blockers. Use synthetic examples and a
sanitized public summary. Missing evidence remains pending; it is not inferred
from another milestone or a code-architecture score.

## Maintenance

- Reconcile [Backend Target Architecture](./backend-target-architecture.md) §5
  and [Backend Evolution Plan](./backend-evolution-plan.md) §0 in the same change.
- Keep [Product Model](../overview/product-model.md) aligned with task-flow and
  production-hardening dependencies.
- Keep project order aligned with the [Product Roadmap](../overview/roadmap.md);
  use [Public Project Landscape](../overview/public-project-landscape.md) for
  dated external design evidence, not deployment acceptance.
- Reconcile the [Architecture Review Checklist](./architecture-review-checklist.md)
  when evidence requirements change, and update the index.
- This roadmap records delivery work; it does not change public contracts or
  activate a new runtime, deployment or migration.
