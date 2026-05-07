# Project Layout

This repository is organized around runtime boundaries first, then shared
contracts and tooling. Keep new files close to the service or contract they
change, and avoid adding top-level compatibility packages.

## Target Shape

The target layout is a small set of top-level product surfaces. Everything else
should live under one of these surfaces or remain a root-level project contract.

```text
.
├── agents/          # Real business runtime agents only
├── services/        # Non-agent gateway and orchestration services
├── shared/          # Reusable runtime, contracts, ports, adapters, and infra
├── rust/            # Rust gateway workspace
├── gateway/         # Legacy Go gateway rollback path
├── frontend/        # Next.js operator console
├── docker/          # Dockerfiles and service configuration
├── infra/           # Infrastructure entry points
├── migrations/      # Alembic migrations
├── tests/           # Cross-cutting repository tests
├── docs/            # Current public documentation
├── scripts/         # Maintenance and developer automation
├── plugins/         # External plugins shipped with the repository
└── .acceptance/     # QA acceptance framework
```

Root-level files should be limited to project contracts, dependency locks,
tooling configuration, and public entry points such as `README.md`, `SPEC.md`,
`AGENTS.md`, `pyproject.toml`, `Makefile`, Compose files, and security or
contribution documents.

## Source Roots

| Path | Ownership |
|------|-----------|
| `agents/` | Real business runtime agents: requirement manager, PJM, QA, and Dev |
| `services/gateways/` | User-facing and platform-facing gateway services |
| `services/orchestration/` | Cross-module orchestration workers |
| `shared/capabilities/` | Shared support capabilities, not business agents |
| `shared/control_plane/agent_catalog.py` | Runtime metadata catalog and `AgentRole` template factory; not a runtime boundary |
| `agents/README.md` | Directory-local boundary rules and runtime-role map |
| `shared/app/` | Agent runtime factory and plugin system |
| `shared/control_plane/` | Control-plane ledger, runs, approvals, budgets, and APIs |
| `shared/core/` | Port interfaces, channel abstractions, ID contracts, and domain-neutral contracts |
| `shared/db/` | Shared database primitives and repositories |
| `shared/grpc/` | Shared protocol artifacts; capability gRPC runtimes live under their owning agent |
| `shared/messaging/` | Messaging orchestration and outbound/inbound adapters |
| `shared/integrations/` | External platform adapters |
| `shared/infra/` | Infrastructure clients and resilience helpers |
| `shared/schemas/` | Shared Pydantic event, agent, and error schemas |
| `rust/gateway/` | Default Rust edge gateway |
| `gateway/` | Legacy Go gateway rollback path |
| `frontend/` | Next.js operator console |
| `plugins/` | External plugin packages shipped with the repository |
| `skills/` | Deprecated root compatibility stubs for requirements skills |

`shared/services/` is a legacy compatibility surface. Existing files can remain
until a planned migration removes them, but new imports should use canonical
paths such as `shared.integrations.*`, `shared.messaging.*`, and
`shared.infra.*`.

## Current Structure Assessment

The current repository has the right high-level idea, but several boundaries
have drifted and should be cleaned in phases:

| Area | Current State | Target |
|------|---------------|--------|
| `agents/` | Contains only real business runtime agents | Keep non-agent services and common capabilities out of this tree |
| `agents/requirement_manager/` | Large business agent with `api/`, `app/`, `core/`, `db/`, `grpc/`, `integrations/`, `prompts/`, `skills/`, and devtools | Keep service-owned backend pieces here; move real UI to root `frontend/` and keep dev-only artifacts under `devtools/` |
| `services/gateways/channel/` | Implemented channel gateway runtime | Keep gateway lifecycle and event dispatch here; reusable messaging primitives remain under `shared/messaging/outbound/`; not part of the default Compose topology yet |
| `shared/services/` | Deprecated compatibility re-export layer | Do not add code; migrate consumers to canonical paths, then remove in a planned compatibility release |
| `shared/integrations/` | Reusable platform adapters, clients, routers, and card builders | Keep platform primitives here; capability-owned Feishu gateway handlers belong under `agents/requirement_manager/integrations/feishu/` |
| `shared/integrations/feishu/cards/` | Platform-level Feishu card builder plus shared Feishu presentation contracts | Keep `CardBuilder` and cross-capability Feishu card payload contracts here. These files must only build Feishu payloads and action values; workflow logic stays inside the owning capability |
| `shared/grpc/server.py` | Deprecated compatibility entry point | Use `agents/requirement_manager/grpc/server.py` for the requirements gRPC runtime |
| Root `skills/` | Deprecated compatibility re-export layer for requirements skills | Keep only while old imports are supported; new code should import `agents.requirement_manager.skills.*` |
| `frontend/src/components/agents/` | Legacy agent detail UI location | Migrated to `frontend/src/widgets/agent-detail/`; do not add new agent surfaces under `components/agents` |
| Tests | Mixed module-local tests and cross-cutting root tests | Keep module-local tests beside their service; use root `tests/` only for cross-module, protocol, e2e, and load tests |

## Migration Rules

- Do not move runtime code only to make the tree look cleaner. Move code only
  when the dependency direction becomes clearer after the move.
- `shared/` must not import from `agents/`. If shared code needs capability
  behavior, define a port or callback and let the capability inject the
  implementation.
- New shared imports should use canonical paths. Do not add new imports from
  `shared.services.*`.
- Compatibility stubs should be thin re-exports with a deprecation docstring,
  no business logic.
- Business agents should keep runtime entry points in `app/`, API routers in
  `api/`, orchestration/business logic in `service/` or `core/`, persistence in
  `db/` and `models/`, and service-local tests in `tests/`.
- Generated or local-only files should remain ignored. If reproducibility needs
  an example, commit a sanitized template instead.

## Cleanup Roadmap

| Phase | Scope | Risk |
|-------|-------|------|
| 1 | Document ownership, ignore local-only artifacts, and stop new imports from legacy paths | Low |
| 2 | Keep empty placeholders documented as Reserved, or implement the runtime before marking them Active | Low |
| 3 | Move requirements-specific Feishu gateway handlers, recorder, and session behavior out of `shared/integrations/feishu/` | Done |
| 4 | Collapse root `skills/` into compatibility-only tests and migrate remaining direct consumers | Medium |
| 5 | Retire `shared/services/` after compatibility consumers are gone | Medium |
| 6 | Split overgrown requirements-only UI/dev artifacts into root `frontend/` or explicit dev tooling; agent detail UI is already under FSD widgets | Medium |

## Operations And Verification

| Path | Purpose |
|------|---------|
| `.acceptance/` | Quality acceptance framework used by the QA capability |
| `tests/` | Repository-level unit, integration, e2e, load, and protocol tests |
| `migrations/` | Alembic database migrations |
| `docker/` | Dockerfiles, Compose overlays, and service configuration |
| `infra/` | Infrastructure compose entry points and environment scaffolding |
| `scripts/` | Repository maintenance, migration, lint, and setup scripts |
| `.github/` | GitHub CI, issue templates, and public collaboration metadata |

## Documentation

| Path | Purpose |
|------|---------|
| `SPEC.md` | Root product and service contract |
| `AGENTS.md` | Mandatory repository workflow and agent rules |
| `README.md` | Public project entry point |
| `docs/INDEX.md` | Documentation map |
| `docs/overview/` | Current architecture, product vocabulary, onboarding, glossary, and layout |
| `docs/guides/` | API, operations, agent development, events, and incident response |
| `docs/adr/` | Architecture decision records |
| `docs/examples/` | Checked-in examples and templates |
| `docs/workflows/` | Machine-readable workflow templates |

Private plans, reviews, and archives should stay out of public history. The
repository ignore rules reserve `docs/plans/`, `docs/reviews/`, and
`docs/archive/` for local-only planning material.

## Local-Only Files

The following paths are intentionally ignored and should not become project
sources:

| Path | Reason |
|------|--------|
| `.env`, `.env.*` | Secrets and local environment overrides |
| `.venv/`, `frontend/node_modules/` | Local dependencies |
| `frontend/.next/`, `frontend/tsconfig.tsbuildinfo`, `frontend/next-env.d.ts` | Frontend build outputs |
| `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `.coverage` | Test, lint, and Python caches |
| `.claude/`, `.ralph/`, `.remember/`, `.playwright-mcp/`, `.ai_context/` | Agent and browser automation workspace state |
| `data/` | Local databases, indexes, and generated runtime data |
| `.worktrees/` | Isolated local development worktrees |

If a file from this list becomes necessary for reproducible builds, add a
sanitized example or template instead of committing the local instance.
