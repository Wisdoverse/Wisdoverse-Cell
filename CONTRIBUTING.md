# Contributing Guide

## Development Setup

### Prerequisites

- Python 3.11+
- Rust 1.86+
- Docker & Docker Compose
- Node.js 24+ (for frontend)

### Local Development

```bash
# Clone and setup
git clone https://github.com/Wisdoverse/project-cell.git
cd project-cell
cp .env.example .env

# Python dependencies
make setup
source .venv/bin/activate

# Start infrastructure
make up-infra

# Run the default development agent
make dev

# Rust gateway
make rust-gateway-run
```

### Testing

```bash
# Public Python gate, same layer used by GitHub CI
make test-public

# Broader local Python layers
make test-unit
make test-unit-full      # broader unit debt sweep, excludes known DB integration tests
make test-integration   # requires local infra from make up-infra or equivalent
make test-e2e           # requires full app stack
make test-python-full   # maintenance target; currently includes legacy cleanup debt

# Rust gateway tests
make rust-gateway-test

# Lint
.venv/bin/python -m ruff check agents/ shared/
```

`make test` is intentionally mapped to `make test-public` so new contributors
get a deterministic no-infrastructure signal first. Integration and E2E tests
must not be added to the public gate unless they provision their own services
or skip cleanly when required dependencies are unavailable.

## Code Standards

### Python
- Async I/O everywhere (no blocking calls)
- Pydantic v2: `model_dump_json()` / `model_validate_json()`
- Repository pattern for database access
- `datetime.now(UTC)` (not `utcnow()`)
- Never log secrets or PII

### Rust
- Propagate request context and trace headers through HTTP handlers
- Use constant-time comparison for security-sensitive checks
- Keep gateway routes and gRPC contracts covered by Rust tests

### Events
```python
Event(
    event_id="evt_{ulid}",
    event_type="{domain}.{action}",  # e.g., "pm.decomposition_completed"
    source_agent="agent-name",       # kebab-case
    payload={...},
)
```

### Agents
- Inherit `BaseAgent`
- Implement `handle_event()`, `startup()`, `shutdown()`
- Use LLMGateway for all model calls; never instantiate provider SDK clients directly.
- Register tools with `@register_tool("name")`

### Inter-Agent Communication

Agents MUST NOT directly import Python code from other independently deployed
agents. Use explicit service boundaries:

```python
# Synchronous calls: AgentClient over HTTP REST
from shared.infra.agent_client import PMAgentClient
client = PMAgentClient()  # URL comes from settings
result = await client.approve_decomposition(wp_id=42, operator="alice")

# Asynchronous collaboration: EventBus over Redis Streams
await event_bus.publish(Event(event_type="pm.decomposition_completed", ...))
```

See [ADR-0004](./docs/adr/0004-inter-agent-http-communication.md).

## Commit Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(chat): add daily progress tracking
fix(gateway): prevent timing attack in signature verification
chore: upgrade Python to 3.13
docs: update architecture diagram
refactor(pm): extract DecompositionOrchestrator
```

## Branch Strategy

- `main` — public-first production-ready code and the only active development trunk
- `intern-archive` — read-only archive of the pre-public internal history; never merge it into `main`
- `feat/<name>` — feature development
- `fix/<name>` — bug fixes

**Rules:**
- Never commit directly to `main`
- Never merge `intern-archive` into `main`; recover needed changes with reviewed cherry-picks or patches only
- Create feature branch before any changes
- Run `ruff check` and `pytest` before pushing
- Run `make test-public` before every PR; run broader layers when touching their
  runtime surface.
- Squash-merge or rebase preferred

## Pull Request Process

1. Create branch from `main`
2. Implement with tests
3. Ensure lint + tests pass
4. Create PR with description template
5. Get review approval
6. Merge via GitHub PR

## Architecture Decisions

See [docs/adr/](./docs/adr/) for Architecture Decision Records.
