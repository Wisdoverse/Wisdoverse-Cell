# ADR-0007: Rust and Python Backend Migration

## Status

Accepted. Rust gateway is the only gateway runtime; the Go rollback path has
been removed.

## Context

Wisdoverse Cell runs Python FastAPI agent services, support capability modules,
and shared runtime infrastructure, with a Rust/Axum gateway handling edge HTTP
and webhook traffic. The repository architecture already requires service
boundaries, ports/adapters, and event contracts, so runtime language can change
behind stable HTTP, gRPC, and EventBus contracts.

The project should move toward a Rust + Python backend without converting the
AI agent runtime into Rust prematurely.

## Decision

Use a two-plane backend:

- Rust edge plane: API gateway, webhook ingress, authentication/rate limiting,
  request hardening, gRPC/HTTP clients, and future EventBus bridge workers.
- Python agent plane: business runtime agents, support capability modules,
  LLM orchestration, control-plane ledger, adapters, prompts, and fast-changing
  product workflows.

The canonical `gateway` Compose service uses the Rust gateway image in local
and production-style topologies. Rust must continue to preserve the existing
`GATEWAY_*` environment variable contract and public route boundaries while it
owns the edge path.

## Migration Stages

1. Keep the canonical Compose `gateway` service on Rust for development and
   production-style deployments.
2. Keep the Python agent plane as the product workflow and LLM orchestration
   runtime.
3. Remove the old Go gateway implementation, toolchain CI job, and rollback
   Compose overlays.
4. Use Rust shadow/canary checks for release evidence and incident drills.
5. Consider Rust EventBus bridge workers only after the Rust edge plane remains
   stable as the default runtime.

## Non-Goals

- Do not rewrite `AgentRuntime`, `create_agent_app()`, or business agents in
  Rust as part of gateway ownership.
- Do not migrate `shared/control_plane` durable ledger code until the Rust edge
  plane has production evidence.
- Do not rename stable runtime identifiers as part of language migration.

## Verification

The Rust gateway slice includes route boundaries, stable `GATEWAY_*`
configuration loading, Feishu signature verification, Feishu
AES-CBC encrypted payload decoding, WeCom SHA1 URL verification, and WeCom
AES-CBC message decoding. It also includes the Redis-backed gateway state
foundation for message deduplication, event deduplication, and conversation
sessions, with an in-memory fallback for local standalone gateway runs. The
Rust gateway now also generates a tonic/prost client from the existing
`requirement.proto` contract and wires `/ready` to the Python requirement
manager `HealthCheck` RPC without renaming the legacy `GATEWAY_GRPC_AI_SERVICE_ADDR`
environment variable. It also owns the command matcher contract and executes
Feishu and WeCom text-message requirement skills through the
Python requirement gRPC service with duplicate message suppression. The Rust
gateway also preserves the `GATEWAY_RATELIMIT_*` configuration contract with
an async token-bucket middleware for edge request protection. Feishu
requirement-skill outbound cards are now rendered in Rust and delivered through
the Feishu Open API client with tenant-token caching. WeCom requirement-skill
text and markdown responses are also rendered in Rust and delivered through
the WeCom `message/send` API with access-token caching. Feishu requirement
card callbacks for confirm, reject, and list pagination now execute against
the Python requirement gRPC service and preserve the gateway response shape for
both v2 `card.action.trigger` and legacy `card_action` callbacks. Feishu
messages that do not match a gateway-owned requirement command are forwarded
to the Python chat gateway through the existing `/webhook/feishu` boundary
with the internal service key header when configured; downstream non-2xx
responses are surfaced as forwarding errors and logged on the Rust webhook
path. Feishu PJM decomposition
approval and rejection card callbacks now forward to the Python PJM agent
through `/api/v1/pm/decompose/{wp_id}/{action}` with the same internal service
key contract and return Rust-rendered result cards. Feishu Bitable update,
create, and reject card callbacks now forward to the Python chat gateway
through `/api/bitable/{confirm,create,reject}`, preserve the internal service
key contract, and deduplicate repeated confirm clicks in the Rust edge plane.
The Rust gateway now also propagates `X-Request-ID` and `X-Trace-ID`, generates
missing IDs, and logs completed requests with `request_id`, `trace_id`, method,
path, status, and latency fields. WeCom `template_card_event` callbacks now
parse the Python adapter-compatible `EventKey` contract and execute
requirement confirm, reject, list, and help actions through the Rust gateway;
confirm and reject callbacks update the original WeCom template card through
`message/update_template_card` when `ResponseCode` is present.

The Rust gateway is now the only gateway runtime.

The migration slice is verified by:

```bash
cargo fmt --manifest-path rust/Cargo.toml --check
make rust-gateway-test
cargo clippy --manifest-path rust/Cargo.toml --all-targets -- -D warnings
make rust-gateway-build
make up-dev
RUST_GATEWAY_URL=http://127.0.0.1:8080 make rust-gateway-canary-check
GATEWAY_PORT=18081 make up-dev-rust-gateway-shadow
LEGACY_GATEWAY_URL=http://127.0.0.1:18081 \
  RUST_GATEWAY_URL=http://127.0.0.1:18080 \
  make rust-gateway-shadow-check
LEGACY_GATEWAY_URL=http://127.0.0.1:18081 \
  RUST_GATEWAY_URL=http://127.0.0.1:18080 \
  make rust-gateway-local-shadow-gate
GATEWAY_HOST=gateway.prod.company.com \
RUST_GATEWAY_SHADOW_HOST=gateway-shadow.prod.company.com \
  make rust-gateway-prod-shadow-config
GATEWAY_HOST=gateway.prod.company.com \
  make rust-gateway-prod-cutover-config
GATEWAY_HOST=gateway.prod.company.com \
RUST_GATEWAY_SHADOW_HOST=gateway-shadow.prod.company.com \
  make up-prod-rust-gateway-shadow
LEGACY_GATEWAY_URL=https://gateway.prod.company.com \
  RUST_GATEWAY_URL=https://gateway-shadow.prod.company.com \
RUST_GATEWAY_PROD_EVIDENCE_REPORT=/path/to/prod-shadow-report.json \
  make rust-gateway-prod-shadow-check
RUST_GATEWAY_PROD_EVIDENCE_REPORT=/path/to/prod-shadow-report.json \
  make rust-gateway-prod-gate
make rust-python-migration-audit
docker compose -f docker/compose/docker-compose.base.yml \
  -f docker/compose/docker-compose.app.yml \
  -f docker/compose/docker-compose.proxy.yml \
  config
docker compose -f docker/compose/docker-compose.base.yml \
  -f docker/compose/docker-compose.app.yml \
  -f docker/compose/docker-compose.proxy.yml \
  -f docker/compose/docker-compose.observability.yml \
  -f docker/compose/docker-compose.prod.yml \
  config
docker build -f rust/gateway/Dockerfile -t projectcell/rust-gateway:local .
```

The canary and shadow targets produce evidence reports under `.artifacts/` by
default. `rust-gateway-local-shadow-gate` runs the same report through the
evidence validator with local URLs explicitly allowed, which makes rollback
comparison drills repeatable without weakening the production gate. Production
rollout evidence still requires running the same checks against real public
listeners and attaching the generated reports to the release record.
`up-prod-rust-gateway-shadow` keeps `gateway` on Rust and adds a separate
`rust-gateway-shadow` service with the prebuilt Rust image and a Traefik route
bound to `RUST_GATEWAY_SHADOW_HOST`.
`up-prod-rust-gateway` depends on `rust-gateway-prod-gate`, which requires a
fresh globally routable evidence report with successful health and `ok`
readiness before running the default Rust production topology.
`rust-gateway-prod-shadow-check` runs a preflight that requires explicit,
distinct, globally routable base URLs for the baseline and shadow Rust gateways
before it writes the production evidence report. Path-scoped URLs, query
strings, and fragments are rejected.

GitHub Actions now runs the Rust gateway format, test, clippy, build, and
Docker build checks as a first-class CI job so Rust/Python migration regressions
do not depend on one-off local verification. `tests/unit/test_rust_gateway_contracts.py`
locks the public Rust gateway route table and asserts that the Rust gateway CI
job remains enabled.
`scripts/rust_python_migration_audit.py` provides a repo-local completion audit
for the Rust + Python backend default and can be promoted to a production audit
with `--require-prod-evidence`.
