# Frontend browser checks

`control-plane-workflow.spec.ts` exercises the Workflow Desk through visible
operator controls while Playwright intercepts the control-plane HTTP routes.
These cases check the browser/API contract and state rendering for work
creation, reassignment, execution denial, failure/retry, approval decisions,
execution-key reuse, artifact review, and closure. The mock does not verify
backend persistence, runtime delivery, QA behavior, or restart recovery; it is
not roadmap acceptance for a live business flow.

Run the mocked browser cases from `frontend/` with:

```bash
npm run test:e2e -- e2e/control-plane-workflow.spec.ts
```

`live-cell-home.spec.ts` is an opt-in, read-only check against an existing
deployment. `live-stack.spec.ts` checks only a configured backend health URL.
Neither spec creates work or validates the full operator lifecycle.

`control-plane-real-api.spec.ts` is an opt-in create/assign/run/review/close
acceptance case. It makes no `page.route` mocks: its browser requests pass
through the authenticated Next.js operator proxy to a separately prepared,
isolated Control Plane and PostgreSQL fixture. Start that backend and the Next
server with `CONTROL_PLANE_API_BASE_URL`, `CONTROL_PLANE_OPERATOR_TOKEN`, and
`CONTROL_PLANE_INTERNAL_KEY` configured for the test fixture, then run:

```bash
REAL_CONTROL_PLANE_E2E=1 \
PLAYWRIGHT_BASE_URL=http://localhost:3200 \
PLAYWRIGHT_SKIP_WEB_SERVER=1 \
npm run test:e2e -- e2e/control-plane-real-api.spec.ts
```

From the repository root, `TEST_DATABASE_URL=<disposable-postgres-url>
PYTHONPATH=. python scripts/roadmap_acceptance_server.py` starts the isolated
loopback API fixture on port 8101 and drops its own fresh schema on graceful
shutdown. It enforces the synthetic internal key `synthetic-browser-internal`
and operator token `synthetic-browser-operator`. Configure the Next proxy with
those values and `CONTROL_PLANE_API_BASE_URL=http://127.0.0.1:8101/api/v1`,
`AUTH_SECRET=<synthetic-local-secret>`, and `NEXTAUTH_URL=http://localhost:3200`;
start Next with `npm run dev -- --hostname localhost --port 3200`.
The CI frontend job provisions PostgreSQL and runs both the seven mocked cases
and this one real case; its JUnit gate rejects skips or missing collection.

The browser's configured base URL should match the origin used to start Next;
the spec supplies that same `Origin` header for writes because the operator
proxy enforces an exact same-origin check. In this local fixture, use
`http://localhost:3200` for both. The spec defaults to the
`cmp_roadmap_browser` company, `g_browser` goal, and
`dev-browser` runnable agent; `REAL_CONTROL_PLANE_COMPANY_ID`,
`REAL_CONTROL_PLANE_GOAL_ID`, and `REAL_CONTROL_PLANE_AGENT_ID` can override
those fixture identifiers. Use only a disposable isolated database: the case
creates and closes a real work item and writes run, artifact, cost, acceptance,
and audit evidence. It does not claim provider-platform, QA-agent, retry,
restart, or staging acceptance.
