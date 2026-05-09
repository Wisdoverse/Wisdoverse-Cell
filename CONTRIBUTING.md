# Contributing Guide

Thank you for considering a contribution to Wisdoverse Cell. This guide covers
the contribution flow, expected quality bar, and the supporting policies that
apply to every contributor.

## Before You Contribute

- Read [SPEC.md](./SPEC.md) and [docs/INDEX.md](./docs/INDEX.md) before
  proposing or implementing changes that touch service contracts, runtime
  identifiers, or the documented architecture boundary rules.
- Follow the [Code of Conduct](./CODE_OF_CONDUCT.md) in all project spaces.
- Report suspected vulnerabilities through the private process in
  [SECURITY.md](./SECURITY.md), not through public issues or pull requests.
- Use [SUPPORT.md](./SUPPORT.md) to find the right channel for questions,
  discussions, and commercial inquiries.

## Communication

| Purpose | Channel |
|---------|---------|
| Reproducible defects and focused proposals | GitHub issues with the provided templates |
| Open-ended design questions | [GitHub Discussions](https://github.com/Wisdoverse/Wisdoverse-Cell/discussions) |
| Code review on a specific change | GitHub pull request thread |
| Vulnerability reports | Private process in [SECURITY.md](./SECURITY.md) |
| Conduct concerns | dev@wisdoverse.com |

The project does not provide synchronous support channels for general
contribution questions.

## Development Setup

### Prerequisites

- Python 3.11+
- Rust 1.86+
- Docker & Docker Compose
- Node.js 24+ (for frontend)

### Local Development

```bash
# Clone and setup
git clone https://github.com/Wisdoverse/Wisdoverse-Cell.git
cd Wisdoverse-Cell
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

1. Create a branch from `main` using the `feat/<name>` or `fix/<name>` prefix.
2. Implement the change with tests at the appropriate layer
   (`make test-public` minimum, broader layers when touching their runtime).
3. Run `ruff check`, the relevant `make test-*` targets, and `cargo fmt` /
   `cargo clippy` for Rust changes before pushing.
4. Open the pull request against `main` using the
   [pull request template](./.github/PULL_REQUEST_TEMPLATE.md). Complete every
   checklist item that applies, including the Risk section.
5. Address review feedback from the assigned code owners
   ([CODEOWNERS](./.github/CODEOWNERS)). Resolve conversations only after the
   reviewer agrees.
6. Squash-merge or rebase-merge once required reviews and CI checks pass. Do
   not merge your own pull request unless explicitly authorized.

### Review and Triage Targets

| Stage | Target |
|-------|--------|
| First triage on issues with required fields completed | Within 5 business days |
| First reviewer comment on a pull request | Within 5 business days of `Ready for review` |
| Required-reviewer response after author updates | Within 5 business days |

These targets are best-effort and may extend during release freezes or
incident response. Pull requests that have been idle for more than 30 days
without author activity may be closed.

## Sign-Off and Attribution

By submitting a pull request, the contributor confirms that:

- The contribution is the contributor's own work or is properly attributed.
- The contribution may be distributed under the project's
  [LICENSE](./LICENSE).
- The contribution does not include third-party code or data without a
  compatible license disclosed in the pull request.

Use clear commit messages and follow [Conventional Commits](https://www.conventionalcommits.org/).
Co-author trailers (`Co-authored-by:`) should reflect actual contributors.

## Reporting Issues and Misconduct

| Concern | Where |
|---------|-------|
| Reproducible bug | [Bug report template](./.github/ISSUE_TEMPLATE/bug_report.yml) |
| Feature or improvement | [Feature request template](./.github/ISSUE_TEMPLATE/feature_request.yml) |
| Suspected vulnerability | [SECURITY.md](./SECURITY.md) |
| Conduct concern | dev@wisdoverse.com (see [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md)) |
| Commercial use or licensing | dev@wisdoverse.com (see [SUPPORT.md](./SUPPORT.md)) |

## Architecture Decisions

See [docs/adr/](./docs/adr/) for Architecture Decision Records. Significant
architecture or contract changes should be proposed as a new ADR alongside
the implementation pull request.
