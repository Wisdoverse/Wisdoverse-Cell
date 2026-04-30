# Contributing Guide

## Development Setup

### Prerequisites

- Python 3.11+
- Go 1.25+
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

# Go gateway
cd gateway && go run ./cmd/gateway
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

# Go tests
cd gateway && go test ./... -race

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

### Go
- `errors.Is()` for error comparison
- `subtle.ConstantTimeCompare` for security-sensitive comparisons
- Context propagation through all HTTP handlers
- Table-driven tests

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
- Use LLMGateway for all Claude API calls (never direct `anthropic.Anthropic()`)
- Register tools with `@register_tool("name")`

### Agent 间通信 (重要)

Agent 之间**禁止 Python 直接 import**。通信方式：

```python
# 同步调用 — 使用 AgentClient (HTTP REST)
from shared.infra.agent_client import PMAgentClient
client = PMAgentClient()  # URL 从 settings 读取
result = await client.approve_decomposition(wp_id=42, operator="alice")

# 异步事件 — 使用 EventBus (Redis Streams)
await event_bus.publish(Event(event_type="pm.decomposition_completed", ...))
```

详见 [ADR-0004](./docs/adr/0004-inter-agent-http-communication.md)。

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
