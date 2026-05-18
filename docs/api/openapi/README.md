# Per-runtime OpenAPI Snapshots

Last updated: 2026-05-18

Status: Foundation. Stage 4 pre-condition per
[`../../architecture/migration-plan.md`](../../architecture/migration-plan.md)
§Stage 4: "Publish per-agent OpenAPI snapshot; lock contract."

Each `<runtime>-v1.json` is the OpenAPI document for one
`create_agent_app()`-built FastAPI application. Snapshots are checked
in so route or schema changes surface as a diff in PR review before
they ship.

## How to Regenerate

```bash
make openapi-snapshots
```

Equivalent:

```bash
python scripts/generate_openapi_snapshots.py
```

The script:
- Sets `CONTROL_PLANE_ENABLED=false` so per-agent snapshots do not
  include the optional control-plane router.
- Imports each runtime's `app/main.py` and calls
  `app.openapi()`.
- Writes one JSON per runtime, canonicalised
  (`sort_keys=True`, two-space indent, trailing newline).

No network or DB call is required.

## Coverage

| Runtime | File |
|---------|------|
| QA Agent | `qa-agent-v1.json` |
| PJM Agent | `pjm-agent-v1.json` |
| Dev Agent | `dev-agent-v1.json` |
| Requirement Manager | `requirement-manager-v1.json` |

Gateway services (`user_interaction`, `channel`), the orchestrator
coordinator, and support capabilities (`sync`, `analysis`,
`evolution`) are not yet covered. Add their entry points to
`scripts/generate_openapi_snapshots.py` `RUNTIMES` when those runtimes
gain public HTTP routes.

The control-plane API (`/api/v1/control-plane/*`) is documented in
[`docs/guides/api-reference.md`](../../guides/api-reference.md)
§Control Plane API; it is not split per-runtime because it is one
operator surface.

## When to Regenerate

- Whenever a route is added, removed, or changes shape.
- Whenever a request or response Pydantic model field is added,
  renamed, removed, or changes type.
- Before tagging a release (see
  [`release-checklist.md`](../../architecture/release-checklist.md)
  §3).

PR review must include the snapshot diff. Reviewers treat the diff
as the contract change and validate it against the API guidelines
([`docs/architecture/api-guidelines.md`](../../architecture/api-guidelines.md)).

## Compatibility Rules

- Adding optional fields → backward compatible. Snapshot diff is
  additive.
- Removing a field, renaming, or changing required-ness → breaking.
  Ship under `/api/v2/*` and add a new snapshot file
  (`<runtime>-v2.json`); preserve `<runtime>-v1.json` until the
  documented sunset.

See `docs/architecture/api-guidelines.md` §6 for the full
compatibility rules.
