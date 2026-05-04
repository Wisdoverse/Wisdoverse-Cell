# Contributing Guide

> Wisdoverse Cell is an AI-native operating company prototype: humans focus on high-leverage decisions while agents handle repeatable execution.

This guide is for both human contributors and AI agents working in this repository.

---

## 1. Branching

- Active trunk: `main`
- Internal archive: `intern-archive` is read-only history kept for reference only.
- Feature branches: `feat/<module>` such as `feat/pm-weekly-report`
- Bug-fix branches: `fix/<module>` such as `fix/sync-dedup`
- Do not push directly to `main`; all changes must go through a PR/MR.
- Do not merge `intern-archive` into `main`; bring forward required internal fixes with reviewed cherry-picks or patches.
- Create the branch before editing code.

```bash
git checkout main && git pull
git checkout -b feat/my-feature
```

---

## 2. Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
type(scope): description
```

| Type | Purpose |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Behavior-preserving refactor |
| `docs` | Documentation change |
| `test` | Test-related change |
| `ci` | CI/CD configuration |
| `perf` | Performance improvement |
| `revert` | Revert |

Common scopes: `chat`, `pm`, `sync`, `analysis`, `requirement`, `evolution`, `qa`, `gateway`, `frontend`, `shared`, `ci`.

Examples:

```text
feat(pm): add weekly report scheduling
fix(ci): guard .venv activation for pre-built image
refactor(shared): migrate outbound to hexagonal ports
test(qa): add acceptance gate unit tests
docs(sync): update Feishu webhook setup guide
perf(ci): use pull_policy if-not-present for test image
revert(ci): remove pull_policy because runner only allows always
```

---

## 3. PR Workflow

```text
Code -> Push -> CI Pipeline -> Code Review -> Merge
                  |
                  |-- ruff lint
                  |-- unit tests
                  |-- integration tests
                  `-- acceptance:l0-gate
```

### L0 Gate

- `ruff lint`: code style and static analysis with zero warnings.
- Type safety: Pydantic v2 validation.
- Test coverage: business logic must have tests.

### Merge Requirements

- All CI jobs pass.
- At least one reviewer approves.
- All review discussions are resolved.

---

## 4. Code Standards

See [`AGENTS.md` Part 4: Coding Standards](../AGENTS.md) for the canonical rules.

Core points:

- Python: async I/O, Pydantic v2 (`model_dump_json()` / `model_validate_json()`), repository pattern.
- Events: `Event(event_type="{domain}.{action}", source_agent="agent-id", ...)`; events are immutable and fire-and-forget.
- Imports: use canonical paths only. Do not add new imports from deprecated `shared.services.*` paths.
- Security: never log secrets, tokens, or PII.

```python
# Correct
from shared.integrations.feishu import FeishuPlatformAdapter
from shared.messaging.outbound.delivery_service import DeliveryService

# Deprecated
from shared.services.feishu import FeishuClient
```

---

## 5. AI Agent Collaboration

Human contributors and AI agents follow the same engineering workflow and quality gates.

- `AGENTS.md` is the canonical agent-rules file.
- Compatibility files such as `CLAUDE.md`, `GEMINI.md`, `.cursorrules`, and `.github/copilot-instructions.md` point back to `AGENTS.md`.
- AI-generated code must pass the same CI pipeline as human-written code.
- AI agents must not push directly to `main`; changes must go through the PR/MR workflow.
- AI agents must treat `intern-archive` as read-only historical context, not as a development base.

---

## 6. Documentation Language

Documentation is English-first.

- Public-facing docs should use English headings and English primary body text.
- Non-English text is allowed only for locale files, external platform field
  names, quoted source content, multilingual test fixtures, and user-facing
  product copy while an i18n path is being migrated.
- When updating a mixed-language document, convert repository-facing guidance
  to English instead of adding parallel non-English explanations.
- New docs should not be Chinese-only.

---

## 7. Testing

- Unit tests are required for business logic.
- Integration tests are required for API endpoints.
- Run `make test` before submitting a PR.

```bash
make test
ruff check agents/ shared/
make dev
make up-infra
make up-dev
```

### Test Style

- Use `pytest` and `pytest-asyncio`.
- Mock external dependencies.
- Prefer `patch.object(module, "attr")` over string-path patching.
- Test files: `test_<module>.py`.
- Test functions: `test_<behavior>()`.

---

Questions should be resolved through the PR discussion, linked issues, or the project maintainers.
