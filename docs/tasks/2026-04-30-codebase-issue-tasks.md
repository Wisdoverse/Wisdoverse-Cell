# Codebase Issue Tasks (2026-04-30)

## 1) Typo Fix Task

**Task**: Fix typo in `shared/infra/event_bus.py` comments/docstring: `Agent启動時` mixes locale and uses non-standard wording; replace with clear Chinese (`Agent启动时`) or consistent English.

- **Why**: Reduces confusion in foundational EventBus docs used by multiple teams.
- **Scope**: `shared/infra/event_bus.py` docstring/comments only.
- **Acceptance**:
  - No mixed/incorrect wording in usage comments.
  - Formatting/lint unchanged.

## 2) Bug Fix Task

**Task**: Prevent redirect edge-cases in unversioned API redirect route.

- **Observed risk**: `api_v1_redirect_router` currently matches `/api/{path:path}` for common methods and blindly rewrites to `/api/v1/{path}`. This can mis-handle empty path (`/api`) and may create awkward redirects when path normalization differs by client/proxy.
- **Scope**: `agents/requirement_manager/app/routes.py`.
- **Suggested fix**:
  - Add explicit handling for `/api` and `/api/`.
  - Guard against double-prefixing (`/api/v1/...`) before redirecting.
  - Keep 307 behavior for write methods.
- **Acceptance**:
  - `/api` redirects to `/api/v1`.
  - `/api/foo` redirects to `/api/v1/foo`.
  - `/api/v1/foo` is not rewritten again.

## 3) Comment/Documentation Discrepancy Task

**Task**: Update onboarding docs to match actual repository and startup flow.

- **Observed discrepancy**: onboarding says clone `project-cell` and `cd project-cell`, while actual repo here is `Wisdoverse-Cell` and AGENTS quick-start uses `python -m venv ...` + `make dev` flow.
- **Scope**: `docs/overview/onboarding.md`.
- **Acceptance**:
  - Clone/cd commands align with current repository name.
  - Setup steps are consistent with AGENTS quick-start and current Make targets.

## 4) Test Improvement Task

**Task**: Add table-driven tests for API redirect behavior.

- **Why**: Current tests do not obviously pin down edge-cases for `/api`, trailing slash, and already-versioned paths.
- **Scope**: requirement_manager API route tests (create or extend test file under `agents/requirement_manager/tests/`).
- **Suggested cases**:
  - `/api` -> `/api/v1`
  - `/api/` -> `/api/v1/`
  - `/api/requirements` -> `/api/v1/requirements`
  - `/api/v1/requirements` -> no extra `/v1` prefix
- **Acceptance**:
  - Parameterized test covers these cases.
  - Assertions include status code + `Location` header.
