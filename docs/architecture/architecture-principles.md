# Architecture Principles

Last updated: 2026-05-18

Status: Foundation document. Every PR that affects architecture must reconcile
with this file before merge.

This document is the architecture constitution for the Wisdoverse Cell Python
backend. It is normative. It overrides convenience, taste, and individual
PR-level decisions. When this document conflicts with another doc, this one
wins until reconciled.

Companion documents:

- [Module Boundaries](./module-boundaries.md)
- [Service Boundaries](./service-boundaries.md)
- [Data Ownership](./data-ownership.md)
- [API Guidelines](./api-guidelines.md)
- [Event Guidelines](./event-guidelines.md)
- [Testing Strategy](./testing-strategy.md)
- [Observability Guidelines](./observability-guidelines.md)
- [Architecture Review Checklist](./architecture-review-checklist.md)
- [Migration Plan](./migration-plan.md)
- [Backend Target Architecture](./backend-target-architecture.md)
- [Backend Architecture Analysis](./backend-architecture-analysis.md)

These principles also reconcile with `AGENTS.md` Part 3, `SPEC.md` §3, and
`docs/overview/architecture.md`. When this file changes, those three must
be reviewed in the same PR.

---

## 1. Layering Rules

The backend uses Clean Architecture inside each runtime service.

| Layer | Packages | Owns | Forbidden |
|-------|----------|------|-----------|
| Interfaces | `agents/<a>/api/`, `agents/<a>/app/`, `services/gateways/*/api/`, `shared/control_plane/api.py`, gRPC servers, FastAPI middleware | HTTP/RPC/MQ entry, DTO conversion, auth/dependency wiring, error mapping, response shaping | Business rules; SQL; direct ORM session except behind a port; transaction control |
| Application | `agents/<a>/core/use_cases/`, `agents/<a>/core/ports/`, `agents/<a>/service/`, `shared/control_plane/*_use_cases.py`, capability use cases | Use-case orchestration; transaction boundary; commands and queries; port composition; outbox writes | DB row construction; ORM imports mixed with domain; god-service patterns |
| Domain | `agents/<a>/core/domain/` (NEW after Stage 1), `agents/<a>/core/<aggregate>_lifecycle.py` until migrated | Entities, value objects, aggregates, invariants, state machines, in-memory domain events, domain services that span aggregates | Imports from `shared.db`, SQLAlchemy, `shared.infra.*` adapters, HTTP clients, LLM SDKs, config providers |
| Infrastructure | `agents/<a>/db/`, `agents/<a>/adapters/`, `shared/integrations/`, `shared/infra/`, `shared/db/`, `shared/messaging/`, `shared/observability/` | Port implementations; persistence; external SDK calls; cache; configuration loading; retries; circuit breakers | Domain decisions; orchestration; business rules |

Cross-cutting:

1. Interfaces must not write business rules.
2. Application service must not become a god service. Split by use-case intent, not by entity.
3. Repository interface and implementation live on opposite sides of the ports/adapters seam.
4. State transitions are modeled explicitly in the domain layer. Status strings outside the FSM definition are not allowed to drive behavior.
5. External calls declare timeout, retry policy, failure classification, and idempotency strategy.
6. Domain layer must not import from infrastructure or interfaces.
7. Tests at each layer use the layer below through ports; integration tests wire real implementations.
8. `controller / handler` does not write business rules.
9. `repository` does not encode business decisions.
10. `application service` does not become a universal service.

---

## 2. Boundary Rules

These restate and extend `AGENTS.md` Part 3 rules. They are normative.

1. Agents must not directly import another independently deployed agent.
2. Agents communicate through HTTP clients or EventBus events.
3. External platforms must be accessed through ports and adapters.
4. `shared/control_plane` owns durable product objects: `Goal`, `WorkItem`, `AgentRole`, `AgentRun`, `Approval`, `Budget`, `Artifact`, `AuditEvent`, `EvolutionProposal`, `AgentPromptConfig`.
5. `shared/core` owns abstract ports and protocols only.
6. `shared/integrations` owns platform adapters.
7. `shared/utils` must not contain business logic.
8. `shared/services` is a compatibility surface only. New imports use canonical paths.
9. Frontend route files must stay thin (Feature-Sliced Design; out of scope here).
10. Frontend domain data belongs to `entities` (out of scope here).
11. All cross-boundary contracts must be documented in `SPEC.md`, the API reference, or the Event Catalog.
12. Canonical runtime identifiers and agent IDs after the 2026-05-10 brand unification are stable (`AGENTS.md` Part 3 rule 13).

---

## 3. Constraints (Engineering Guardrails)

These constraints come from the senior-architect brief that scoped the
backend refactor. They are binding. They apply to every PR until removed.

1. No one-shot rewrites of the project.
2. No mass file moves in a single PR.
3. No architecture aesthetics at the cost of existing functionality.
4. No unrelated code changes inside a refactor PR.
5. No new framework unless explicitly approved.
6. No abstractions without business meaning.
7. No empty `Entity` / `Service` / `Repository` shells.
8. No business logic dumped into `common` / `shared` / `utils`.
9. Domain must not depend on infrastructure.
10. Controllers / handlers must not contain business rules.
11. Repositories must not carry business decisions.
12. Application services must not become universal services.
13. No cross-service direct database access.
14. No shared ORM Entity as a cross-service contract.
15. No fabricated test results.
16. No hiding of uncertainty.
17. No changes to production configuration, secrets, or environment variables.
18. No weakening of authentication, authorization, validation, or security policies.
19. No deletion of "looks unused" code without explicit confirmation.
20. No microservices for the sake of microservices.

When a PR cannot avoid violating one of these constraints, the PR description
must call it out explicitly, propose a mitigation, and request architecture
review before merge.

---

## 4. Tactical Guidance

### 4.1 Use Cases

- One use case = one purpose. If a use case name contains "and", split it.
- Use cases own the transaction boundary. Implicit `async with session()` is
  acceptable for one aggregate; multi-aggregate writes require an explicit
  `UnitOfWork`.
- Use cases depend on ports (`*_ports.py`), not on adapters.
- Domain events emitted by aggregates are collected by the use case and
  written to the outbox in the same transaction as the aggregate state.

### 4.2 Ports

- Ports live in `agents/<a>/core/ports/` or `shared/<package>/<aggregate>_ports.py`.
- Use `typing.Protocol` to keep ports lightweight and adapters duck-typed.
- Ports do not return ORM rows. They return domain models or DTOs.

### 4.3 Stores / Repositories

- One store per aggregate (`<aggregate>_store.py`).
- Stores implement persistence only. No "if status == X then ..." inside a
  store.
- Stores return domain models. ORM `*Table` types do not escape the store.

### 4.4 Domain Events vs Integration Events

- Domain events: internal to one boundary, never published through the
  EventBus.
- Integration events: published through the EventBus; payload model in
  `shared/schemas/event_payloads.py`; row in the Event Catalog.

### 4.5 LLM Calls

- All LLM traffic flows through `shared.infra.llm_gateway`. No direct
  `anthropic.*` / `openai.*` / `google.generativeai.*` imports outside the
  gateway. Enforced by `tests/unit/test_architecture_boundaries.py`.

### 4.6 External Calls

- Every external HTTP call declares timeout, retry, failure classification,
  and idempotency strategy at the adapter layer.
- Circuit breaker protects integrations that can fail-storm (LLM, Feishu,
  OpenProject, GitLab, AgentForge).

### 4.7 Security

- Webhooks verify signatures before any business logic runs.
- Logs never contain secrets, tokens, signatures, or raw PII.
- Internal endpoints verify `X-Internal-Key` unless explicitly public.

---

## 5. PR Compliance

Every architecture-affecting PR must answer the questions in the
[Architecture Review Checklist](./architecture-review-checklist.md). When a
principle here cannot be honored, the PR description must say so and request
an explicit exception.

When this document changes, the change must update or reconcile:

- `AGENTS.md` Part 3 (architecture constitution section).
- `SPEC.md` §3 (architecture boundary rules).
- `docs/overview/architecture.md` (boundary rules section).
- All sibling docs under `docs/architecture/`.
