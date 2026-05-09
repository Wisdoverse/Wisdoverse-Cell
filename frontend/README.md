# Wisdoverse Cell Frontend

This package is the Next.js operator console for Wisdoverse Cell. It renders the
control-plane workbench, evolution proposals, agent fleet, approvals,
requirements, activity, and monitoring surfaces used by operators.

The product contract lives at the repository root. Read these before changing a
cross-boundary workflow:

- [`../SPEC.md`](../SPEC.md)
- [`../docs/INDEX.md`](../docs/INDEX.md)
- [`../docs/overview/architecture.md`](../docs/overview/architecture.md)
- [`../docs/overview/project-layout.md`](../docs/overview/project-layout.md)
- [`../docs/guides/api-reference.md`](../docs/guides/api-reference.md)

## Stack

- Next.js 16 App Router, React 19, and TypeScript
- Tailwind CSS 4 with Radix/shadcn-compatible UI primitives
- `next-intl` for locale routing and messages
- `next-auth` for authentication integration
- SWR, TanStack Table, Recharts, Zod, Sentry, and OpenTelemetry
- Vitest, Testing Library, and Playwright

## Quick Start

From the repository root:

```bash
make frontend-dev
```

From this package:

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`. Pages that call backend APIs require the
corresponding backend services, gateway routes, and environment variables from
the repository root `.env.example`.

## Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start the local Next.js dev server |
| `npm run build` | Build the standalone production artifact |
| `npm run start` | Serve the built production artifact |
| `npm run lint` | Run ESLint and FSD boundary checks |
| `npm run lint:fsd` | Check Feature-Sliced Design layer and public API boundaries |
| `npm run test` | Run Vitest once |
| `npm run test:watch` | Run Vitest in watch mode |
| `npm run test:e2e` | Run Playwright end-to-end tests |
| `make frontend-dev` | Root-level wrapper for `npm run dev` |
| `make frontend-build` | Root-level wrapper for `npm run build` |
| `make frontend-lint` | Root-level wrapper for `npm run lint` |
| `make frontend-test` | Root-level wrapper for `npm test` |

## Source Layout

```text
frontend/
|-- src/app/          # App Router layouts, routes, route handlers, and CSS entry
|-- src/entities/     # Domain data, API hooks, models, and entity UI
|-- src/features/     # User actions and intent-level UI flows
|-- src/widgets/      # Composed operator surfaces assembled from slices
|-- src/shared/       # Business-neutral UI primitives, providers, and foundations
|-- src/lib/          # API transport, auth, telemetry, registries, and neutral utilities
|-- src/i18n/         # Locale routing and request configuration
|-- src/messages/     # Locale message catalogs
|-- src/test/         # Test setup and shared test utilities
`-- e2e/              # Playwright scenarios
```

## Architecture Rules

The frontend follows strict Feature-Sliced Design.

- Route files in `src/app/` stay thin. They compose widgets and pass route or
  search parameters; they do not own control-plane state.
- Domain data, API hooks, and entity-level presentation live in
  `src/entities/<domain>/`.
- User actions live in `src/features/<action>/`.
- Full operator surfaces live in `src/widgets/<surface>/`.
- Business-neutral UI primitives, providers, and UI-only hooks live in
  `src/shared/`.
- `src/components/` is retired. Do not add files there.
- `src/hooks/`, `src/lib/hooks/`, and `src/lib/registry/` are retired. New code
  imports canonical shared UI hooks from `src/shared/` and domain hooks or
  registry data through each slice public API.
- Frontend code calls documented HTTP/API contracts and typed hooks. It must not
  import backend, agent, adapter, database, or LLM implementation modules.
- Preserve runtime identifiers exactly, including names such as `projectcell`,
  `project-cell`, `project_cell`, and existing agent IDs.
- Project language is English for docs, code comments, API descriptions, and
  internal prompts. Locale files and intentional user-facing copy may use other
  languages.

Recommended dependency direction:

```text
src/app -> src/widgets -> src/features -> src/entities -> src/shared and src/lib
```

`entities` must not import from `features` or `widgets`. `features` should not
own long-lived domain state. `widgets` may compose slices, but should avoid
duplicating API clients or registry data already owned by entities.
Cross-slice imports must use the target slice public API, such as
`@/entities/agent`, not a deep path under `ui/`, `model/`, or `api/`.

## Working on a Slice

1. Put backend contract usage in an entity API module or hook.
2. Put operator actions in a feature package.
3. Put page-level composition in a widget package.
4. Keep route files to layout, metadata, params, and widget composition.
5. Place tests beside the slice they protect.
6. Update the API docs or event catalog when a cross-boundary contract changes.

## Testing and Quality Gates

Use the narrowest useful check while iterating, then run the broader gates before
handing off frontend changes.

```bash
npm run test -- --run <path-or-pattern>
npm run lint
npm run test
npm run build
```

Run Playwright when changing navigation, authentication, route behavior,
operator workflows, or browser-only integrations:

```bash
npm run test:e2e
```

For a local full-stack E2E run, point the browser tests at the live backend and
keep the frontend dev server explicit:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
E2E_BACKEND_HEALTH_URL=http://127.0.0.1:8000/health \
npm run test:e2e
```

Playwright starts its own Next.js server on `127.0.0.1:3100` by default so
local development servers on port 3000 cannot leak stale environment variables
into E2E runs. Use `PLAYWRIGHT_PORT=<port>` for a different isolated port, or
`PLAYWRIGHT_BASE_URL=<url>` when intentionally reusing an external server.

For UI changes, verify desktop and mobile layouts, text wrapping, loading
states, error states, and empty states. Keep route-level experiences dense and
operator-focused rather than marketing-oriented.

## Environment and Observability

- Use the repository root `.env.example` as the environment contract.
- Do not document secrets or check local `.env` values into the repository.
- Sentry source map upload is activated by `SENTRY_AUTH_TOKEN`,
  `SENTRY_ORG`, and `SENTRY_PROJECT` during build pipelines.
- Browser telemetry should remain centralized under `src/lib/telemetry/` and
  `src/instrumentation.ts`.

## Ownership Notes

- This README owns frontend package guidance only.
- Product-wide rules belong in `SPEC.md` and the docs index.
- Repository layout and migration state belong in
  `docs/overview/project-layout.md`.
- API shape belongs in `docs/guides/api-reference.md`.
