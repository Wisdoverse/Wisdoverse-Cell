# Wisdoverse Cell Operations Guide

Last updated: 2026-05-03

This runbook describes local development, production-style Docker operation,
health checks, scaling, observability, and control-plane runtime switches.
English is the primary language for operational documentation.

## 1. Deployment Modes

Wisdoverse Cell uses layered Docker Compose files under `docker/compose/`:

| Layer | File | Responsibility |
|-------|------|----------------|
| Base infrastructure | `docker-compose.base.yml` | PostgreSQL, PgBouncer, Redis, NATS, Milvus |
| Application | `docker-compose.app.yml` | Core application services: requirements runtime (`ai-core` runtime id), gateway, and web |
| Proxy | `docker-compose.proxy.yml` | Traefik reverse proxy |
| Observability | `docker-compose.observability.yml` | Prometheus, Grafana, Loki, Tempo, exporters |
| Development override | `docker-compose.override.yml` | Exposed debug ports, single replicas |
| Production override | `docker-compose.prod.yml` | Prebuilt images, rolling updates, replicas |
| Load testing | `docker-compose.loadtest.yml` | k6 profiles |

Common modes:

| Mode | Command | Use case |
|------|---------|----------|
| Development stack | `make up-dev` | Local Compose stack with debug-friendly defaults and Traefik ingress |
| Infrastructure only | `make up-infra` | Run Python/Go/Node processes locally against shared infra |
| Production-style stack | `make up-prod` | Production-like Compose topology |
| Observability | `make monitoring-up` | Prometheus/Grafana/Loki/Tempo stack |

## 2. Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
make up-infra
make dev
```

Additional services:

```bash
make gateway-dev
make frontend-dev
```

Default local endpoints:

| Surface | URL |
|---------|-----|
| Compose ingress and frontend | `http://localhost` |
| Compose API docs | `http://localhost/docs` when `DEBUG=true` |
| Traefik dashboard | `http://localhost:8081/dashboard/` |
| Local frontend dev server | `http://localhost:3000` when running `make frontend-dev` |
| Grafana | `http://localhost:3001` when running `make monitoring-up` |

## 3. Production-Style Settings

Required environment values for production-like deployments:

```bash
POSTGRES_PASSWORD=<strong-password>
AUTH_SECRET=<nextauth-secret>
REGISTRY=registry.example.com/
VERSION=1.0.0
OPENAI_API_KEY=<openai-api-key-for-openai-models>
# Or set ANTHROPIC_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY for those LiteLLM routes.
FEISHU_APP_ID=cli_xxxx
FEISHU_APP_SECRET=xxxx
FEISHU_VERIFICATION_TOKEN=xxxx
FEISHU_ENCRYPT_KEY=xxxx
ALERTMANAGER_FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
```

Production expectations:

- `DEBUG=false`
- `LOG_LEVEL=INFO`
- `LOG_FORMAT=json`
- Infrastructure ports are not exposed publicly.
- Traefik is the public ingress.
- Local execution adapters are disabled unless explicitly reviewed.
- Default development passwords are replaced before deployment.
- `FEISHU_VERIFY_SIGNATURE=true` and `FEISHU_ENCRYPT_KEY` is populated before
  exposing Feishu webhook routes; invalid signatures must fail before JSON
  parsing or event dispatch.

### 3.1 LLM Provider Selection

All agents call models through `shared.infra.llm_gateway.LLMGateway`. LiteLLM is
the only supported runtime provider boundary.

```bash
# Multi-provider path through LiteLLM.
LLM_PROVIDER=litellm
DEFAULT_MODEL=openai/gpt-5
CHAT_MODEL=openai/gpt-5
SUMMARY_MODEL=openai/gpt-5-mini
OPENAI_API_KEY=<openai-api-key>
```

Model names follow LiteLLM's `provider/model-name` convention, for example
`openai/gpt-5`, `anthropic/claude-sonnet-4-20250514`, or
`openrouter/google/gemini-2.5-pro`. Native Claude names such as
`claude-sonnet-4-20250514` are still normalized to
`anthropic/claude-sonnet-4-20250514` for compatibility.

Docker Compose passes the common LiteLLM provider keys into Python agent
containers: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, and
`GOOGLE_API_KEY`. Add additional provider keys to the Compose `x-llm-env`
anchor when a new provider is promoted to production use.

## 4. Service Topology

| Service | Internal port | Purpose |
|---------|---------------|---------|
| PostgreSQL | `5432` | Durable storage |
| PgBouncer | `6432` | Database connection pooling |
| Redis | `6379` | EventBus, cache, sessions, budget state |
| NATS | `4222`, `8222` | Optional durable event streaming |
| Milvus | `19530`, `9091` | Vector storage and health |
| Requirement manager agent (`ai-core` runtime id) | `8000`, `50051` | FastAPI/gRPC service |
| Sync support capability | `8010` | OpenProject and Feishu sync |
| Analysis support capability | `8011` | Reports and risk checks |
| PJM agent | `8012` | Decomposition, alerts, reports |
| User interaction gateway | `8013` | Chat/webhook gateway |
| QA agent | `8014` | Acceptance checks |
| Dev agent | `8015` | AgentForge-backed delivery |
| Go gateway | `8080` | API gateway and webhook entry points |
| Web | `3000` | Next.js frontend |
| Traefik | `80`, `443`, `8081` | Ingress and dashboard |

## 4.1 Docker Build Targets

`docker/Dockerfile.agents` is the canonical Python service image. Compose target
names preserve runtime identifiers for compatibility even when a service is a
gateway or support capability.

Python service images use a runtime-only dependency split:

- `docker/requirements/agent-base.txt` contains shared runtime dependencies for
  `shared/app`, middleware, control-plane clients, EventBus, metrics, and
  tracing.
- Each service target installs only its own package requirements on top, for
  example `agents/requirement_manager/requirements.txt`.
- Root `requirements.txt` remains the local development and CI dependency set;
  it intentionally includes test and developer tooling and is not used by
  production agent images.
- `.dockerignore` excludes test trees from production image build context.
- Requirement vector-search dependencies are optional because local
  `sentence-transformers` pulls a large torch stack. Build `ai-core` with
  `--build-arg INSTALL_VECTOR_DEPS=true` only when local Milvus semantic
  indexing is required.

| Target | Package | Runtime kind |
|--------|---------|--------------|
| `ai-core` | `agents.requirement_manager` | Requirements business runtime agent, using the historical `ai-core` service id |
| `sync-agent` | `shared.capabilities.sync` | Support capability |
| `analysis-agent` | `shared.capabilities.analysis` | Support capability |
| `pjm-agent` | `agents.pjm_agent` | Business runtime agent |
| `chat-agent` | `services.gateways.user_interaction` | User interaction gateway runtime id |
| `qa-agent` | `agents.qa_agent` | Business runtime agent |
| `dev-agent` | `agents.dev_agent` | Business runtime agent |

Build a single target before changing Compose service wiring:

```bash
docker build --target dev-agent -f docker/Dockerfile.agents .
```

## 5. Health Checks

Every `create_agent_app()` service exposes:

```bash
curl -f http://localhost:<port>/health
curl -f http://localhost:<port>/health/ready
```

Detailed health/status routes require the internal key:

```bash
curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  http://localhost:<port>/health/ready/detail

curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  http://localhost:<port>/status
```

Channel Gateway keeps `/health` public for liveness. Adapter inventory and
adapter-detail health expose runtime platform state and require the internal
key:

```bash
curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  http://localhost:<channel-gateway-port>/health/adapters

curl -H "X-Internal-Key: $INTERNAL_SERVICE_KEY" \
  http://localhost:<channel-gateway-port>/api/admin/adapters
```

Gateway health:

```bash
curl -f http://localhost:8080/health
curl -f http://localhost:8080/ready
```

## 6. Scaling

Common scaling commands:

```bash
make scale-ai-core N=5
make scale-gateway N=5
make scale-web N=3
```

Scaling signals:

| Signal | Action |
|--------|--------|
| API P99 latency above 2s and CPU above 80% | Add application replicas |
| Gateway P99 latency above 500ms and connection count high | Add gateway replicas |
| PostgreSQL connections above 80% | Check PgBouncer and connection pooling |
| Redis memory above 80% | Inspect large keys and retention settings |
| Event queue backlog above 1000 for sustained periods | Scale consumers or inspect failures |

## 7. Observability

The observability stack includes Prometheus, Alertmanager, Grafana, Loki, Tempo,
Promtail, and database/cache exporters.

Start it with:

```bash
make monitoring-up
```

Critical signals:

| Signal | Target |
|--------|--------|
| HTTP P99 latency | Below 2s |
| HTTP 5xx rate | Below 1% |
| LLM API error rate | Below 5% |
| Event queue backlog | Below 1000 |
| PostgreSQL connection usage | Below 80% |
| Redis memory usage | Below 80% |

Log expectations:

- Production logs use structured JSON.
- Logs must include `trace_id`, `agent_id`, `run_id`, or `work_item_id` when
  available.
- Logs must never include secrets, full API keys, credentials, or raw prompt
  text containing user-sensitive data.

## 8. Troubleshooting

### Service Unavailable

```bash
make ps
make logs-app
curl -f http://localhost:8080/ready
curl -f http://localhost:8000/health/ready
```

If a service is unhealthy:

1. Check container status and restart count.
2. Read service logs around the failing timestamp.
3. Check database, Redis, NATS, and Milvus readiness.
4. Confirm required environment variables are present.
5. Restart only the failed service when the root cause is isolated.

### High Latency

1. Check API P99 latency in Prometheus/Grafana.
2. Inspect PostgreSQL slow queries and PgBouncer pool usage.
3. Inspect Redis latency and memory.
4. Check LLM gateway retries, fallback, and circuit-breaker state.
5. Scale the bottlenecked service only after confirming the bottleneck.

### PostgreSQL Connection Exhaustion

```sql
select state, count(*) from pg_stat_activity group by state;
select count(*) from pg_stat_activity;
```

Use PgBouncer first. Do not raise PostgreSQL connection limits without checking
application connection ownership.

### Redis Memory Pressure

```bash
redis-cli INFO memory
redis-cli --bigkeys
```

Inspect retention policies before deleting keys. Prefer targeted cleanup over
global flush operations.

### LLM API Failure

1. Check `shared.infra.llm_gateway` logs.
2. Confirm the API key is configured without exposing it in logs.
3. Check model fallback and retry categories.
4. Check budget enforcement state.
5. Check the LiteLLM proxy and active provider status if failures are external.

## 9. Control Plane Operations

The control-plane ledger is opt-in until migrations are applied and the operator
API is ready for the target environment.

```bash
CONTROL_PLANE_ENABLED=true
CONTROL_PLANE_COMPANY_ID=cmp_projectcell
CONTROL_PLANE_APPROVAL_ENFORCED=true
CONTROL_PLANE_LLM_BUDGET_ENFORCED=true
CONTROL_PLANE_TOOL_BUDGET_ENFORCED=true
CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=false
CONTROL_PLANE_LOCAL_ADAPTER_ALLOWLIST=
```

Production policy:

- Keep `CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=false`.
- Use the `http` adapter to call deployed `create_agent_app()` services.
- Require `X-Internal-Key` for control-plane service routes.
- Record run, approval, artifact, budget, and audit evidence on the same trace.
- Fail closed when an adapter is missing or not allowlisted.

Manual wakeup path:

```text
operator -> POST /api/v1/control-plane/agents/{agent_id}/wake
         -> AgentRun created
         -> adapter resolved
         -> POST /agent/request on deployed service
         -> output/error/budget/artifact evidence persisted
```

Heartbeat path:

```text
scheduler -> POST /api/v1/control-plane/scheduler/heartbeats/run-once
          -> due active AgentRole records selected
          -> one AgentRun per due wakeup
          -> evidence appended to timeline
```

Budget policy:

- LLM usage is recorded through `LLMGateway`.
- Tool usage is recorded when `ToolRegistry` entries declare
  `estimated_cost_usd`.
- When budget enforcement is enabled, `BudgetGuard` must approve the estimated
  cost before the call runs.

Approval policy:

- Finance, legal, customer-impacting, and technical high-risk actions require
  human approval.
- `ToolRegistry` blocks `is_destructive` or `requires_approval` tools before
  the handler runs when `CONTROL_PLANE_APPROVAL_ENFORCED=true` unless the tool
  context carries an already approved `approval_id`.
- Approval resolution must be append-only and visible in the control-plane
  timeline.

EventBus failure visibility:

- Redis EventBus exposes `get_pending_count(event_type, group)` for consumer lag.
- Redis EventBus writes failed handler events and malformed payloads to
  `dlq.failed`; operators can inspect it with `get_dead_letter_count()` and
  `list_dead_letters()`.
- NATS deployments use JetStream redelivery and consumer stats instead of the
  Redis DLQ stream.

## 10. Local E2E Verification

Use real browser E2E after Docker, routing, authentication, or frontend route
changes. The frontend Playwright suite enables local development credentials
only through explicit environment variables.

Minimal browser run:

```bash
cd frontend
npm run test:e2e
```

Full-stack browser run against a live backend:

```bash
cd frontend
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
E2E_BACKEND_HEALTH_URL=http://127.0.0.1:8000/health \
npm run test:e2e
```

Playwright starts an isolated Next.js server on `127.0.0.1:3100` by default
with dev auth enabled. Use `PLAYWRIGHT_PORT=<port>` for a different isolated
port. When the frontend server is already running and has the correct auth
environment, use `PLAYWRIGHT_BASE_URL=<url>` to reuse it instead of starting a
second dev server.

## 11. Command Reference

```bash
make up-dev
make down-dev
make up-prod
make down-prod
make up-infra
make down-infra
make restart
make logs
make logs-app
make logs-obs
make ps
make build
make build-no-cache
make test
make test-public
make test-unit
make test-integration
make docker-test
make load-smoke
make clean
make proto
make proto-python
make proto-go
```

Update this guide whenever Compose layers, runtime switches, ports, health
checks, alert rules, or operational procedures change.
