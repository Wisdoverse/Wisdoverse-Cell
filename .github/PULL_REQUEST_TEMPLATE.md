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

## Notes

- 
