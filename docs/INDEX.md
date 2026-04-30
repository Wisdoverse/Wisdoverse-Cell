# Wisdoverse Cell Documentation Index

> Last updated: 2026-04-28
>
> This is the entry point for Wisdoverse Cell documentation. Documentation is English-first; legacy Chinese content may remain where a detailed translation pass has not yet been completed.

---

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [README](./README.md) | Documentation landing page, architecture, quick start, agent matrix |
| [CONTRIBUTING](./CONTRIBUTING.md) | Branching, commits, PR workflow, AI collaboration rules |
| [CHANGELOG](./CHANGELOG.md) | Version history |

---

## Overview

For onboarding, architecture, and shared terminology.

| Document | Purpose |
|----------|---------|
| [Product Model](./overview/product-model.md) | Control-plane vocabulary: goals, org chart, work items, runs, governance, budgets, audit logs |
| [Architecture Overview](./overview/architecture.md) | System architecture, communication model, deployment topology |
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

---

## Specifications

| Document | Status | Purpose |
|----------|:------:|---------|
| [Wisdoverse Cell PRD](./specs/wisdoverse-cell-prd.md) | Published | Product vision, 26-agent plan, technical specs, roadmap |
| [Requirement Manager Agent PRD](./specs/requirement-manager-agent-prd.md) | Published | M1-M4 feature specs, APIs, test strategy |
| [Feishu Integration PRD](./specs/feishu-integration-prd.md) | Published | Bot, cards, event subscriptions, completed phase scope |
| [QA Agent Spec](./specs/qa-agent.md) | Complete | Event-driven acceptance checks and notifications |
| [Acceptance Framework Spec](./specs/acceptance-framework.md) | Complete | L0/L1/L2 quality gates |
| [Requirement Manager Verification](./specs/requirement-manager-verification.md) | Passed | F01-F18 verification and test evidence |
| [create_agent_app Migration Design](./specs/2026-03-20-requirement-manager-create-agent-app-design.md) | Complete | Requirement Manager migration to `create_agent_app` |
| [VectorStore Plugin Design](./specs/2026-03-20-vector-store-plugin-design.md) | Complete | Milvus VectorStore RuntimePlugin design |

---

## Guides

For contributors, operators, and deployers.

| Document | Purpose |
|----------|---------|
| [Agent Development Guide](./guides/agent-development.md) | New-agent template, `create_agent_app`, plugins, tests, deployment |
| [API Reference](./guides/api-reference.md) | REST endpoints, authentication, errors |
| [Event Catalog](./guides/event-catalog.md) | Event types, payload schemas, producer/consumer matrix |
| [Operations Guide](./guides/operations.md) | Deployment, scaling, monitoring, troubleshooting, backups |
| [Incident Response Guide](./guides/incident-response.md) | Severity model, response flow, playbooks, recovery |

---

## Configuration Reference

| File | Purpose |
|------|---------|
| [`.env.example`](../.env.example) | Environment variable template |
| [`docs/examples/cn-build-mirrors.env.example`](./examples/cn-build-mirrors.env.example) | Optional build mirror values for China mainland development |
| [`Makefile`](../Makefile) | Unified command entry point |
| [`docker-compose.yml`](../docker-compose.yml) | Docker Compose deployment |
| [`docker/compose/`](../docker/compose/) | Layered cloud-native Compose files |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | GitHub Actions CI |
| [`pyproject.toml`](../pyproject.toml) | Python project configuration |
| [`LICENSE`](../LICENSE) | Wisdoverse Cell Business Source License 1.1 |

---

## Documentation Conventions

### Naming

- ADRs: `docs/adr/NNNN-<topic>.md`
- PRDs and specs: `<module>-prd.md` or `<topic>-design.md`

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
├── specs/
├── guides/
└── workflows/
```
