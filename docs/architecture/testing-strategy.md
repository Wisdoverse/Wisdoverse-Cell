# Testing Strategy

Last updated: 2026-05-18

Status: Foundation document.

This document defines the testing contract for the backend. It is binding for
every PR that touches backend code. The strategy maps the senior-architect
brief's 10-item list to the current repository layout, and adds rules for
mocking, data, and CI gates.

The authoritative test surface today is documented in:

- `tests/` (cross-cutting tests)
- `tests/unit/test_architecture_boundaries.py` (executable architecture
  rules; 4583 LOC, ~10 rule categories)
- `agents/*/tests/` (service-local tests)

---

## 1. Test Pyramid

```text
                 ┌────────────────────────┐
                 │   E2E (golden paths)   │   slow, few
                 ├────────────────────────┤
                 │   Contract (HTTP/Event)│
                 ├────────────────────────┤
                 │   Integration (DB,     │
                 │   external mocks)      │
                 ├────────────────────────┤
                 │   Use-case (ports      │
                 │   mocked)              │
                 ├────────────────────────┤
                 │   Domain unit (pure)   │   fast, many
                 └────────────────────────┘
```

Aim for many fast tests at the bottom; few slow tests at the top. CI's
default regression gate is the union of domain unit + use-case +
contract + selected integration tests. Full e2e runs on release branches.

---

## 2. Test Types and Targets

### 2.1 Domain Unit Tests

- Location: `agents/<a>/tests/unit/domain/`.
- Purpose: verify aggregate invariants, value object equality, FSM
  transitions, domain error raising.
- Requirements:
  1. Pure Python. No I/O. No DB. No HTTP.
  2. No mocks. Use real domain objects.
  3. Cover every state-machine transition (allowed + illegal).
  4. One test file per aggregate.

### 2.2 Use-Case Tests

- Location: `agents/<a>/tests/unit/use_cases/`.
- Purpose: verify orchestration, transaction boundary, port interactions,
  emitted events.
- Requirements:
  1. Mock at the port boundary only (`*_ports.py`).
  2. Assert the sequence of port calls; assert the events written to the
     fake outbox.
  3. Cover happy path + at least one failure path per port.

### 2.3 Repository / Store Integration Tests

- Location: `agents/<a>/tests/integration/db/` or `tests/integration/db/`.
- Purpose: verify SQL against real Postgres.
- Requirements:
  1. Real Postgres in CI (testcontainers preferred).
  2. No mocking of SQLAlchemy.
  3. One test per store method.
  4. Transactions are explicit; tests assert rollback on error.

### 2.4 API Contract Tests

- Location: `tests/contract/http/<runtime>/`.
- Purpose: verify HTTP request and response shape per route.
- Requirements:
  1. Each public route has at least one request + one response snapshot.
  2. OpenAPI snapshot per agent committed under
     `docs/api/openapi/<runtime>-v1.json`.
  3. Snapshot diffs are part of PR review.
  4. Tests cover the documented error envelope (code, message, trace_id,
     `X-Error-Code`, `X-Trace-ID`).

### 2.5 Message Consumer Tests

- Location: `tests/contract/events/<runtime>/`.
- Purpose: verify each consumer handles the published payload shape and is
  idempotent.
- Requirements:
  1. One producer test per integration event (asserts payload matches the
     Pydantic model in `shared/schemas/event_payloads.py`).
  2. One consumer test per (consumer × event_type).
  3. Idempotency test: same `event_id` consumed twice yields the same
     observable state.

### 2.6 Migration Tests

- Location: `tests/integration/migrations/`.
- Purpose: verify Alembic up and down on a clean database.
- Requirements:
  1. CI runs `alembic upgrade head` and `alembic downgrade base` against a
     test database.
  2. Tests assert that no migration leaves orphan data.
  3. Per-runtime migration directories (after Stage 4) each get their own
     up/down test.

### 2.7 Critical Flow E2E Tests

- Location: `tests/e2e/`.
- Purpose: end-to-end golden paths (meeting → requirement → PRD →
  decomposition → delivery → QA).
- Requirements:
  1. One golden-path test per quarter, minimum.
  2. Per-runtime smoke: `/agent/<id>/request` accepts a wakeup and returns
     a valid response.
  3. Uses real services in a docker-compose test stack.

### 2.8 Regression Tests

- Location: beside the related unit/use-case test.
- Purpose: ensure every fixed bug stays fixed.
- Requirements:
  1. Every bugfix PR adds a regression test that fails before the fix and
     passes after.
  2. The test name references the issue or PR number.

### 2.9 Mocking Strategy

- Mock at the port boundary only. Never mock SQLAlchemy, httpx, or other
  framework primitives directly.
- Mocks live in `tests/fakes/` or beside the test file, never inside the
  production package.
- Mocking the LLM Gateway is allowed; mocking individual provider SDKs
  (`anthropic.*`, `openai.*`) is forbidden — go through the gateway port.

### 2.10 Test Data Strategy

- Factories live under `tests/factories/`.
- Use deterministic IDs from `shared.core.ids` to keep snapshots stable.
- Per-test isolation: each test gets its own DB transaction and rolls back
  on teardown.
- No production data in fixtures. No real secrets, tokens, or PII.

---

## 3. Architecture-Boundary Tests

`tests/unit/test_architecture_boundaries.py` is the executable form of the
architecture rules. Treat it as a first-class test, not infrastructure.

- New boundary rules ship with new assertions in this file.
- The file must stay readable. Group assertions by rule category and keep
  comments concise.
- Failures in this file block merge regardless of which agent caused them.

---

## 4. Coverage Targets

- Domain unit: 100% of state transitions covered.
- Use-case: each use case has at least one happy-path test and one failure
  test per declared failure mode.
- Contract: every route + every integration event covered.
- Repository: every store method exercised by at least one integration
  test.
- E2E: at least one golden path per business flow.

Line coverage is not the gate; transition and contract coverage are.

---

## 5. CI Gates

The CI workflow runs:

1. `ruff check agents/ shared/ services/` (lint, errors only).
2. `pytest tests/ agents/*/tests/` (full regression).
3. Architecture-boundary tests (subset of (2); blocks merge on its own).
4. Per-agent OpenAPI snapshot diff.
5. Alembic up/down on a clean DB (the migration tests above).
6. Rust gateway tests (out of scope here).
7. Frontend lint/tests/audit (out of scope here).
8. CodeQL (security; out of scope here).

A green run requires every gate green.

---

## 6. Performance and Load Tests

- `make load-smoke` runs a k6 smoke (10 VUs) against the gateway. Use it
  before release.
- Per-route P95/P99 SLOs are tracked in the observability dashboard
  (see [`observability-guidelines.md`](./observability-guidelines.md)).
- Load tests are not part of the default regression gate.

---

## 7. Forbidden Patterns

- Mocks at the SQLAlchemy or httpx level.
- Tests that depend on real external services (Feishu, GitLab,
  OpenProject) in the default regression gate.
- Tests that reuse fixtures across files without an explicit factory.
- Tests asserting on log strings as the primary contract — use structured
  events or function return values instead.
- Hand-written contract tests when an OpenAPI snapshot would do the same
  job.

---

## 8. Maintenance

When this document changes:

- Update `docs/guides/agent-development.md` testing section.
- Update CI workflow files in `.github/workflows/` if a new gate is
  introduced.
