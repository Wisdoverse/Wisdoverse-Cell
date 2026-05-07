# Wisdoverse Cell

Wisdoverse Cell is a source-available control plane for AI-native companies:
humans set goals and approve high-leverage decisions while agent services
handle repeatable operational work with traces, budgets, approvals, and audit
trails.

It packages a FastAPI agent runtime, a Rust/Axum gateway, a Next.js console, and
PostgreSQL/Redis/NATS/Milvus infrastructure for requirement extraction, task
decomposition, Feishu/OpenProject sync, QA checks, and self-evolution loops.

> [!WARNING]
> Wisdoverse Cell is an engineering preview for trusted development and
> evaluation environments. Review [SECURITY.md](./SECURITY.md) before
> production-like deployment.

## Agent Handoff

New implementation agents should read the root contracts before entering module
code:

| Read first | Use for |
|------------|---------|
| [SPEC.md](./SPEC.md) | Root service contract, domain model, and implementation requirements |
| [docs/INDEX.md](./docs/INDEX.md) | Documentation map for product, architecture, specs, guides, and ADRs |
| [docs/guides/agent-development.md](./docs/guides/agent-development.md) | New-agent service pattern, tests, and deployment checklist |

Concise continuation prompt:

> Continue Wisdoverse Cell from the current repository state. Read `SPEC.md`
> and `docs/INDEX.md` first. Preserve the `SPEC.md` contract, keep runtime
> identifiers such as `projectcell`, `project-cell`, and `project_cell` stable
> unless a migration is explicitly planned, and verify changes with the
> narrowest relevant tests.

### Frontend Console Direction

The frontend is an operator console, not a marketing site. Prefer a compact,
high-signal workbench where goals, work items, agent runs, approvals, budgets,
audit evidence, and integration health are visible in one scannable flow. Useful
patterns include split-pane inspection, status rails, timeline and replay
views, inline approvals, and proof-of-work panels. Avoid decorative hero
surfaces, low-information cards, and views that hide operational evidence behind
chat alone.

## Running Wisdoverse Cell

### Requirements

- Docker and Docker Compose for local infrastructure.
- Python 3.11+, Rust 1.86+, Node.js/npm, and Go 1.25 only when exercising the
  legacy gateway rollback path
  for local development.
- LiteLLM provider keys and other secrets configured in `.env`.

### Option 1. Docker Compose stack

```bash
git clone https://github.com/Wisdoverse/project-cell.git
cd project-cell
cp .env.example .env
# Fill in POSTGRES_PASSWORD, AUTH_SECRET, and provider keys for the selected LiteLLM models.
make up-dev
```

Default local endpoints:

- Compose ingress and frontend: <http://localhost>
- Compose API docs: <http://localhost/docs> when `DEBUG=true`
- Traefik dashboard: <http://localhost:8081/dashboard/>
- Local frontend dev server: <http://localhost:3000> when running `make frontend-dev`
- Grafana: <http://localhost:3001> when running `make monitoring-up`

### Option 2. Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
make up-infra
make dev
```

Additional services:

```bash
make rust-gateway-run
make gateway-dev  # legacy Go rollback path only
make frontend-dev
```

## What Is Included

- `agents/`: real business runtime agents: requirement manager, PJM, QA, and Dev.
- `services/`: non-agent gateways and orchestration workers.
- `shared/`: runtime, schemas, integrations, messaging, observability, and
  infra clients, plus support capabilities that are not business agents.
- `rust/gateway/`: default Rust gateway for edge HTTP and webhook entry points;
  it preserves the existing gateway routes and calls Python requirement services
  through the shared gRPC contract.
- `gateway/`: legacy Go gateway retained only for explicit rollback drills.
- `frontend/`: Next.js console for operators.
- `docs/`: product model, architecture, guides, ADRs, and specs.
- `docker/`: Compose assets for local and production-style deployments.

See [Project layout](./docs/overview/project-layout.md) for the full source
root map, structure cleanup roadmap, and local-only file policy.

## Documentation

- [SPEC.md](./SPEC.md)
- [docs/INDEX.md](./docs/INDEX.md)
- [Product model](./docs/overview/product-model.md)
- [Architecture overview](./docs/overview/architecture.md)
- [Agent development guide](./docs/guides/agent-development.md)
- [Operations guide](./docs/guides/operations.md)
- [Security policy](./SECURITY.md)
- [Contributing guide](./CONTRIBUTING.md)

## License

Wisdoverse Cell is source-available under the Wisdoverse Cell Business Source
License 1.1 (`LicenseRef-Wisdoverse-Cell-BSL-1.1`).

Each version automatically becomes available under the Apache License, Version
2.0 four years after that version is first made publicly available. See
[LICENSE](./LICENSE).
