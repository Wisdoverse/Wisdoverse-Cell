## Summary

- 

## Verification

- [ ] `python -m ruff check agents/ shared/ skills/ tests/`
- [ ] `python -m pytest -q`
- [ ] `cargo fmt --manifest-path rust/Cargo.toml --check`
- [ ] `make rust-gateway-test`
- [ ] `cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings`
- [ ] `make rust-gateway-build`
- [ ] `make rust-gateway-local-shadow-gate` when this PR changes Rust gateway runtime, gateway routing, or local shadow evidence behavior
- [ ] `make rust-python-migration-audit`
- [ ] `make rust-python-migration-audit-prod` when this PR changes production Rust gateway deployment behavior
- [ ] `make rust-gateway-prod-shadow-config`
- [ ] `make rust-gateway-prod-cutover-config`
- [ ] `make up-prod-rust-gateway-shadow` config path reviewed when this PR changes production shadow routing
- [ ] `make rust-gateway-prod-shadow-check` with `GATEWAY_HOST` matching the baseline gateway host and distinct globally routable baseline / shadow gateway URLs when this PR changes production gateway rollout or shadow evidence behavior
- [ ] `docker build -f rust/gateway/Dockerfile -t wisdoverse/cell-rust-gateway:local .`
- [ ] `cd frontend && npm ci && npm run lint && npm test && npm audit --omit=dev --audit-level=high && npm run build`
- [ ] Public hygiene checks pass

## Risk

- [ ] Security/auth behavior changed
- [ ] Database schema or migration changed
- [ ] Event schema or agent contract changed
- [ ] Deployment, Docker, or CI behavior changed
- [ ] Architecture boundary touched (new aggregate, port, store, route group, runtime split, capability split)

## Architecture Review

If any "Architecture boundary touched" box above is checked, work through
[`docs/architecture/architecture-review-checklist.md`](../docs/architecture/architecture-review-checklist.md)
and confirm:

- [ ] PR conforms to [Architecture Principles](../docs/architecture/architecture-principles.md) (layering rules, constraints, no empty shells)
- [ ] If a new table is added: row in `docs/guides/backend-boundaries.md` §3 and entry in `docs/architecture/module-boundaries.md`
- [ ] If a new HTTP route is added: follows [API Guidelines](../docs/architecture/api-guidelines.md) (versioning, DTO, error envelope, idempotency)
- [ ] If a new integration event is added: payload model in `shared/schemas/event_payloads.py`, row in `docs/guides/event-catalog.md`
- [ ] Architecture-boundary tests (`tests/unit/test_architecture_boundaries.py`) extended for any new structural rule
- [ ] [Observability Guidelines](../docs/architecture/observability-guidelines.md) §2 followed for new cross-boundary code paths
- [ ] No `AsyncSession` leaks into route handlers; cross-runtime ORM imports forbidden

If proposing service extraction:

- [ ] [Service Boundaries](../docs/architecture/service-boundaries.md) §4 pre-conditions evidenced (outbox + projection + idempotency + replay, per-runtime migrations, dashboards, non-prod proof)

## Notes

- 
