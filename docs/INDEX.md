# Wisdoverse Cell Documentation Index

> Last updated: 2026-05-04
>
> This is the entry point for Wisdoverse Cell documentation. Documentation is English-first. Non-English text should be limited to locale values, quoted source text, external platform contracts, and multilingual fixtures.

---

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [SPEC](../SPEC.md) | Root service specification and implementation contract |
| [README](./README.md) | Documentation landing page, architecture, quick start, agent matrix |
| [CONTRIBUTING](./CONTRIBUTING.md) | Branching, commits, PR workflow, AI collaboration rules |
| [CHANGELOG](./CHANGELOG.md) | Version history |

---

## Current Implementation Map

Use this section as the first handoff for any agent continuing product or
platform work. It links the product contract to the code-facing operator
surfaces that currently exist.

| Surface | Source of Truth | Notes |
|---------|-----------------|-------|
| Product contract | [SPEC](../SPEC.md) | Defines the control-plane goal and non-negotiable service boundaries |
| Product vocabulary | [Product Model](./overview/product-model.md) | Defines goals, work items, agent roles, runs, decisions, artifacts, budgets, approvals, and audit trails |
| Repository layout | [Project Layout](./overview/project-layout.md) | Maps source roots, current structure drift, cleanup phases, and ignored local-only paths |
| System architecture | [Architecture Overview](./overview/architecture.md) | Maps architecture boundary rules, frontend, gateway, independently deployed agents, shared runtime, control-plane ledger, and adapters |
| Backend boundaries | [Backend Boundaries](./guides/backend-boundaries.md) | Defines bounded contexts, table ownership, API/event/data contracts, and current backend governance gaps |
| Operator API | [API Reference](./guides/api-reference.md#control-plane-api) | Documents `/api/v1/control-plane/*`, `/agent/request`, wakeups, scheduler ticks, approvals, budgets, and timelines |
| Event contract | [Event Catalog](./guides/event-catalog.md#30-control-plane-domain) | Documents control-plane events and producer/consumer expectations |
| Operations | [Operations Guide](./guides/operations.md#10-control-plane-operations) | Documents migrations, runtime switches, local-adapter fail-closed policy, heartbeat execution, and run evidence |
| Frontend workbench | [`frontend/src/app/[locale]/(app)/workflows/`](<../frontend/src/app/[locale]/(app)/workflows/>) | Operator entry point backed by Feature-Sliced Design slices under `entities/`, `features/`, and `widgets/` |

---

## Overview

For onboarding, architecture, and shared terminology.

| Document | Purpose |
|----------|---------|
| [Product Model](./overview/product-model.md) | Control-plane vocabulary and implemented foundation: goals, org chart, work items, runs, governance, budgets, audit logs |
| [Project Layout](./overview/project-layout.md) | Repository source roots, architecture cleanup roadmap, docs map, and local-only file policy |
| [Architecture Overview](./overview/architecture.md) | Current system architecture, boundary rules, communication model, control-plane runtime, frontend slices, and deployment topology |
| [Onboarding Guide](./overview/onboarding.md) | First 30 minutes, first day, first week |
| [Glossary](./overview/glossary.md) | Core terminology grouped by domain |

---

## Architecture Decision Records

| ADR | Date | Purpose |
|-----|------|---------|
| [ADR-0001: Redis Streams EventBus](./adr/0001-redis-streams-eventbus.md) | 2026-03-07 | Redis LIST to Streams, consumer groups, durability, replay |
| [ADR-0002: Per-Agent Database Isolation](./adr/0002-per-agent-db-isolation.md) | 2026-03-07 | PostgreSQL per-agent users and Redis per-agent DBs |
| [ADR-0003: Tiered LLM Model Strategy](./adr/0003-tiered-llm-model-strategy.md) | 2026-03-07 | Opus/Sonnet/Haiku routing and cost control |
| [ADR-0004: Inter-Agent HTTP Communication](./adr/0004-inter-agent-http-communication.md) | 2026-03-07 | No direct Python imports between agents; HTTP plus EventBus |
| [ADR-0005: Channel Gateway Hexagonal Unification](./adr/0005-channel-gateway-hexagonal-unification.md) | 2026-03-08 | `core/messaging` ports and integration adapters |
| [ADR-0007: Rust and Python Backend Migration](./adr/0007-rust-python-backend-migration.md) | 2026-05-04 | Rust edge plane plus Python agent plane migration path |

---

## Guides

For contributors, operators, and deployers.

| Document | Purpose |
|----------|---------|
| [Agent Development Guide](./guides/agent-development.md) | New-agent template, `create_agent_app`, plugins, tests, deployment |
| [API Reference](./guides/api-reference.md) | REST endpoints, authentication, errors, control-plane API, agent wakeups |
| [Backend Boundaries](./guides/backend-boundaries.md) | Bounded contexts, table ownership, cross-boundary access rules, and known backend governance gaps |
| [Event Catalog](./guides/event-catalog.md) | Event types, payload schemas, producer/consumer matrix, control-plane lifecycle events |
| [Operations Guide](./guides/operations.md) | Deployment, scaling, monitoring, control-plane runtime switches, troubleshooting, backups |
| [Incident Response Guide](./guides/incident-response.md) | Severity model, response flow, playbooks, recovery |

---

## Architecture

The backend architecture is governed by the foundation documents under
`docs/architecture/`. They reconcile to the constitution documents
(`AGENTS.md`, `SPEC.md`, `architecture.md`, `backend-boundaries.md`) rather
than the other way around. Every architecture-affecting PR must satisfy the
Architecture Review Checklist before merge.

| Document | Purpose |
|----------|---------|
| [Architecture Principles](./architecture/architecture-principles.md) | Binding layering rules, boundary rules, and engineering constraints |
| [Module Boundaries](./architecture/module-boundaries.md) | Bounded context catalog with responsibility, data, dependencies, and split fitness |
| [Service Boundaries](./architecture/service-boundaries.md) | Decision matrix for runtime extraction; default modular-monolith posture |
| [Data Ownership](./architecture/data-ownership.md) | Per-table write owner rules, cross-boundary read patterns, migration rules |
| [API Guidelines](./architecture/api-guidelines.md) | HTTP/REST/RPC contract: versioning, DTOs, error envelope, OpenAPI, idempotency |
| [Event Guidelines](./architecture/event-guidelines.md) | Domain vs integration events, envelope, producer/consumer contract, schema evolution |
| [Testing Strategy](./architecture/testing-strategy.md) | Test pyramid, test types per layer, CI gates, mocking and data strategy |
| [Observability Guidelines](./architecture/observability-guidelines.md) | Minimum logs, traces, metrics, alerts, SLOs, health endpoints |
| [Architecture Review Checklist](./architecture/architecture-review-checklist.md) | Per-PR checklist used by author and reviewer |
| [Migration Plan](./architecture/migration-plan.md) | Six-stage phased roadmap (Stage 0 docs → Stage 5 quality) |
| [Backend Target Architecture](./architecture/backend-target-architecture.md) | Phase 2 target architecture and first-step proposal |
| [Backend Architecture Analysis](./architecture/backend-architecture-analysis.md) | Phase 1 read-only audit (current state) |
| [Backend Evolution Plan](./architecture/backend-evolution-plan.md) | Earlier follow-up plan after the PR #121 backend modularization slice |

---

## Configuration Reference

| File | Purpose |
|------|---------|
| [`.env.example`](../.env.example) | Environment variable template |
| [`docs/examples/cn-build-mirrors.env.example`](./examples/cn-build-mirrors.env.example) | Optional build mirror values for China mainland development |
| [`Makefile`](../Makefile) | Unified command entry point |
| [`docker-compose.yml`](../docker-compose.yml) | Docker Compose deployment |
| [`docker/compose/`](../docker/compose/) | Layered cloud-native Compose files |
| [`rust/Cargo.toml`](../rust/Cargo.toml) | Rust workspace for gateway and future edge-plane services |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | GitHub Actions CI |
| [`pyproject.toml`](../pyproject.toml) | Python project configuration |
| [`LICENSE`](../LICENSE) | Wisdoverse Cell Business Source License 1.1 |

---

## Documentation Conventions

Documentation should describe current truth first, then planned work. If a page
contains roadmap material, label it explicitly and link to the implementation
evidence that proves what has already shipped.

### Language

- English is the primary language for repository documentation and code-facing
  explanations.
- New or changed docs must not be Chinese-only.
- Non-English text is allowed only for locale files, quoted source content,
  external platform field names, and test fixtures that intentionally exercise
  multilingual behavior.

### Naming

- ADRs: `docs/adr/NNNN-<topic>.md`

### Status

| Status | Meaning |
|--------|---------|
| Published | Reviewed and accepted as implementation guidance |
| In progress | Currently being implemented |
| Complete | Implemented and verified |
| Accepted | ADR-specific accepted decision |

### Directory Structure

```text
docs/
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── INDEX.md
├── overview/
├── adr/
├── architecture/
├── examples/
├── guides/
└── workflows/
```
