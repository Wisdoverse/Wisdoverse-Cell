# Architecture Review Checklist

Last updated: 2026-05-18

Status: Foundation document.

This checklist runs on every PR that affects backend architecture: new
routes, new events, new tables, new ports, new runtimes, cross-boundary
contracts, or changes to the architecture-boundary tests.

Copy the checklist into the PR description and answer every item. If an
item does not apply, write "n/a" with a one-line reason.

---

## 1. Scope

- [ ] PR title follows `<type>(<scope>): <subject>` (Conventional Commits).
- [ ] PR description states the bounded contexts the change affects.
- [ ] PR description states whether this is documentation-only,
      structural, behavior-changing, or contract-changing.
- [ ] No unrelated cleanup is included. (`architecture-principles.md` §3
      rule 4.)
- [ ] PR size is reasonable for the change. Multi-file moves are split
      across multiple PRs.

## 2. Boundary Compliance

- [ ] No new cross-agent direct imports. (`AGENTS.md` Part 3 rule 1.)
- [ ] No new imports from `shared.services.*` deprecated paths.
- [ ] Domain layer does not import from infrastructure or interfaces.
- [ ] `controller / handler` does not contain business rules.
- [ ] `application service` is not a god service.
- [ ] `repository` does not encode business decisions.
- [ ] ORM `*Table` types do not appear in cross-context boundaries.
- [ ] LLM traffic uses `shared.infra.llm_gateway`; no direct provider
      SDK imports outside the gateway.

## 3. Data Ownership

- [ ] New tables ship with:
  - [ ] Alembic migration
  - [ ] Row in `docs/guides/backend-boundaries.md` §3
  - [ ] Entry in `docs/architecture/module-boundaries.md`
  - [ ] Up/down migration test
- [ ] Changed table owners ship a cutover plan + compatibility window.
- [ ] No cross-runtime direct DB access introduced.
- [ ] Distributed transactions are not introduced.

## 4. API Contract

- [ ] New routes follow `/api/v1/*` (or a new `/api/v2/*` for breaking).
- [ ] Request and response are Pydantic v2 DTOs with `extra="forbid"`
      where applicable.
- [ ] Error responses use the standard envelope (`code`, `message`,
      `trace_id`, optional `details`) + `X-Error-Code` and `X-Trace-ID`
      headers.
- [ ] Authentication and authorization are enforced at the right layer.
- [ ] Mutating endpoints support `Idempotency-Key` when retry-safe
      behavior matters.
- [ ] `docs/guides/api-reference.md` is updated.
- [ ] Per-agent OpenAPI snapshot is regenerated and committed.
- [ ] At least one HTTP contract test is added.

## 5. Event Contract

- [ ] New events have a Pydantic payload model in
      `shared/schemas/event_payloads.py`.
- [ ] New events have a row in `docs/guides/event-catalog.md`.
- [ ] Producers write through the outbox; no direct EventBus publish.
- [ ] Consumers are idempotent; idempotency key documented.
- [ ] `schema_version` is bumped on backward-incompatible payload
      change.
- [ ] At least one producer/consumer contract test is added.

## 6. Observability

- [ ] New cross-boundary code paths log `trace_id`, `agent_id`, and
      relevant business IDs on entry and exit.
- [ ] New external calls declare timeout, retry policy, failure
      classification, and idempotency strategy.
- [ ] New metrics follow the naming and cardinality rules in
      `observability-guidelines.md`.
- [ ] New alerts have a documented runbook entry in
      `docs/guides/operations.md`.
- [ ] Tracing is on (no-op exporter fallback if no endpoint).
- [ ] Logs never include secrets, tokens, signatures, or raw PII.

## 7. Testing

- [ ] Domain unit tests cover any new aggregates or state-machine
      transitions.
- [ ] Use-case tests cover orchestration and at least one failure mode
      per port.
- [ ] Repository tests use a real Postgres (testcontainers).
- [ ] API contract tests assert request/response shape + error envelope.
- [ ] Event contract tests assert payload shape + idempotency.
- [ ] Migration tests run Alembic up and down.
- [ ] Architecture-boundary tests are extended for any new structural
      rule.
- [ ] Regression test is added when this PR fixes a bug.

## 8. Operations and Rollout

- [ ] Documented rollback path for any behavior change.
- [ ] Production secrets and environment variables are unchanged
      (`architecture-principles.md` §3 rule 17).
- [ ] Authentication, authorization, validation, and security policies
      are not weakened (`architecture-principles.md` §3 rule 18).
- [ ] If a runtime is being extracted, the extraction playbook in
      `service-boundaries.md` §4 is followed and pre-conditions are
      evidenced.

## 9. Documentation Reconciliation

- [ ] `AGENTS.md` is updated if architecture constitution changes.
- [ ] `SPEC.md` is updated if a contract changes.
- [ ] `docs/overview/architecture.md` is updated if topology changes.
- [ ] `docs/architecture/architecture-principles.md` is updated if a
      principle changes.
- [ ] Sibling docs under `docs/architecture/` are reconciled.
- [ ] `docs/INDEX.md` is updated if a new doc is added.

## 10. Exceptions

If this PR cannot satisfy one of the items above, state which item, why,
and propose a follow-up. Request architecture review before merge.

---

## Usage Notes

- A PR that fails one item is not automatically blocked; author and
  reviewer decide whether the exception is acceptable. The decision is
  recorded in the PR description.
- A PR that fails an architecture-boundary test is blocked. That test is
  the executable form of these rules.
- A PR that adds a new principle or boundary rule must update this
  checklist in the same change.
