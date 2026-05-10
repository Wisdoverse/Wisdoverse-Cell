# Wisdoverse Cell

Wisdoverse Cell turns company operations into governed, autonomous agent runs, allowing teams to
manage goals and approvals instead of supervising agents.

_Wisdoverse Cell models goals, work items, agent roles, runs, approvals, budgets, and audit trails
as first-class control-plane objects. Humans set direction and approve high-leverage decisions while
agent services handle repeatable operational work with full traces, cost controls, and proof of
work. Each agent run produces verifiable evidence: events, artifacts, approvals, and audit logs._

> [!WARNING]
> Wisdoverse Cell is an engineering preview for trusted development and evaluation environments.
> Review [SECURITY.md](./SECURITY.md) before any production-like deployment.

## Running Wisdoverse Cell

### Requirements

Wisdoverse Cell is built around an explicit service contract ([SPEC.md](./SPEC.md)) and a control
plane vocabulary ([docs/overview/product-model.md](./docs/overview/product-model.md)). Implementing
or extending it works best when your coding agent has read both before touching code.

Local development requires Docker, Python 3.11+, Rust 1.86+, Node.js, and LiteLLM provider keys.

### Option 1. Build your own

Hand the contract to your coding agent and let it implement Wisdoverse Cell in the language and
runtime of your choice:

> Implement Wisdoverse Cell according to the following spec:
> https://github.com/Wisdoverse/Wisdoverse-Cell/blob/main/SPEC.md
>
> Use the canonical runtime identifiers `wisdoverse-cell` (kebab — services,
> networks, compose), `wisdoverse_cell` (snake — Python distribution), and
> `Wisdoverse Cell` (display). Treat the documents under `docs/overview/` and
> `docs/guides/` as the operator-facing contract.

### Option 2. Use the reference implementation

This repository ships a FastAPI agent runtime, a Rust/Axum gateway, a Next.js operator console, and
PostgreSQL/Redis/NATS/Milvus infrastructure.

```bash
git clone https://github.com/Wisdoverse/Wisdoverse-Cell.git
cd Wisdoverse-Cell
cp .env.example .env
make up-dev
```

For local Python development against shared infra:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make up-infra
make dev
```

You can also ask your coding agent to bring up the reference implementation:

> Set up Wisdoverse Cell for my environment based on
> https://github.com/Wisdoverse/Wisdoverse-Cell/blob/main/README.md and
> https://github.com/Wisdoverse/Wisdoverse-Cell/blob/main/docs/guides/operations.md

## Agent Handoff

Implementation agents should read the root contracts before entering module code:

| Read first | Use for |
|------------|---------|
| [SPEC.md](./SPEC.md) | Service contract, domain model, normative requirements |
| [docs/INDEX.md](./docs/INDEX.md) | Documentation map: product, architecture, guides, ADRs |
| [docs/guides/agent-development.md](./docs/guides/agent-development.md) | New-agent service pattern, tests, deployment checklist |
| [AGENTS.md](./AGENTS.md) | Repository-level rules for AI agents working in this codebase |

## License

Wisdoverse Cell is source-available under the Wisdoverse Cell Business Source License 1.1
(`LicenseRef-Wisdoverse-Cell-BSL-1.1`). Each version automatically converts to Apache License 2.0
four years after first public release. See [LICENSE](./LICENSE).
