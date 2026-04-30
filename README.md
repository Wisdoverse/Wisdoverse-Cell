# Wisdoverse Cell

**Source-available control plane for AI-native companies** — a new organizational model where humans define values and make high-leverage decisions while an agent network handles repeatable execution.

---

## Vision / 愿景

Wisdoverse Cell explores how to operate a company in an AI-native way:

- Humans focus on high-leverage decisions; agents handle repeatable execution.
- The operating model evolves from Co-pilot to Agent to Orchestrator to DAO of Agents.

中文愿景：

探索如何以 AI 原生的方式运营一家公司：
人类专注于高杠杆决策，Agent 处理重复性执行。
从 Co-pilot 逐步演进到 Agent -> Orchestrator -> DAO of Agents。

---

## What Is Wisdoverse Cell?

Wisdoverse Cell is a self-hosted operating system and control plane for running company workflows with AI agents. It treats company goals, agent roles, work items, approvals, costs, and audit trails as first-class product objects instead of scattering them across chat windows, scripts, and task trackers.

Humans remain the board and operators. Agents do the repeatable work, report status through typed events, and escalate decisions that require judgment, budget, customer impact, legal review, or technical architecture approval.

```text
Mission -> Goals -> Work Items -> Agent Runs -> Decisions -> Audit Trail
              |             |             |
              |             |             +-> Cost, logs, artifacts, rollback notes
              |             +-> Owner, priority, dependency, approval state
              +-> Org chart, agent role, policy, budget
```

---

## Control Plane Primitives

Wisdoverse Cell treats an AI-native company as a governed operating system, not
just a collection of prompts. The product model is built around these control
plane primitives:

| Primitive | Purpose | Current Direction |
|-----------|---------|-------------------|
| Goals | Keep every task tied to business intent | Requirement extraction, PRD generation, and PJM decomposition |
| Org chart | Make agent roles, responsibilities, and reporting lines explicit | 26-agent operating model with independently deployed services |
| Work items | Track work as durable records, not transient chats | OpenProject and Feishu workflow integration |
| Agent runs | Preserve execution state, logs, tool calls, and outputs | AgentRuntime, events, tracing, QA checks |
| Governance | Let humans approve, pause, reject, or override sensitive work | Human-in-the-loop approvals for finance, legal, customer, and architecture decisions |
| Budgets | Bound LLM cost and prevent runaway automation | Tiered model strategy and real-time LLM budget controls |
| Audit trail | Explain what happened, who approved it, and why | Immutable events, trace IDs, metrics, logs, and DSAR support |
| Evolution | Improve prompts, architecture, and collaboration loops | L1 skill optimization, L2 architecture optimization, L3 collaboration optimization |

---

## Tech Stack

| Layer | Technology | Role |
|------|------------|------|
| AI Core | Python 3.13 / FastAPI | Agent services, LLM orchestration, business logic |
| Gateway | Go 1.25 / Gin | API gateway, Feishu/WeCom webhooks |
| Frontend | Next.js 16 / React 19 / shadcn/ui | Web console, i18n (zh/en/ja) |
| Database | PostgreSQL 18 + PgBouncer | Business data, connection pooling, per-agent isolation |
| Cache / EventBus | Redis 8 + Redis Streams | Cache, durable event bus, per-agent DB isolation |
| Messaging | NATS JetStream | Optional durable event streaming backend |
| Vector DB | Milvus | Semantic search and RAG |
| LLM | Claude API | Tiered reasoning strategy with cost controls |
| Reverse Proxy | Traefik v3 | Service discovery and L7 load balancing |
| Observability | Prometheus + Grafana + Jaeger | Metrics, alerts, logs, traces |
| Frontend Monitoring | OpenTelemetry + Sentry | Distributed tracing and error tracking |

---

## Repository Layout

```text
project-cell/
├── agents/                         # Independently deployed agent services
│   ├── chat_agent/                 # User-facing chat agent
│   ├── pjm_agent/                  # Project management agent
│   ├── sync_agent/                 # OpenProject <-> Feishu sync
│   ├── analysis_agent/             # Risk detection and analytics
│   └── requirement_manager/        # Requirement extraction and PRD generation
├── gateway/                        # Go API gateway
├── frontend/                       # Next.js web console
├── shared/                         # Shared Python runtime, schemas, infra, integrations
├── docker/                         # Cloud-native Docker Compose stack
├── docs/                           # Documentation
├── tests/                          # Top-level tests
├── scripts/                        # Operational scripts
└── .github/workflows/              # GitHub Actions CI
```

---

## Quick Start

### Docker Compose

```bash
# 1. Clone
git clone https://github.com/Wisdoverse/project-cell.git
cd project-cell

# 2. Configure environment
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and other required settings.

# 3. Start the development stack
make up-dev

# 4. Open services
# Frontend:  http://localhost:3000
# API:       http://localhost:8000/docs
# Traefik:   http://localhost:8080
# Grafana:   http://localhost:3001
```

### Local Development

```bash
# 1. Start infrastructure only
make up-infra

# 2. Python backend
pip install -r requirements.txt
make dev

# 3. Go gateway
make gateway-dev

# 4. Next.js frontend
make frontend-dev
```

### Common Commands

```bash
make help                # List all commands
make test                # Run the public no-infrastructure Python gate
make test-unit           # Run the broader stable Python unit layer
make frontend-test       # Run frontend tests
make proto               # Generate Python and Go gRPC code
make up-prod             # Start the production-style stack
make logs                # Tail service logs
make ps                  # Show service status
make scale-ai-core N=5   # Scale AI Core replicas
```

---

## Architecture

```text
                         ┌──────────────┐
                         │   Gateway    │  Go Gin + Webhook
                         │    (Go)      │
                         └──────┬───────┘
                                │ HTTP (X-Internal-Key)
               ┌────────────────┼────────────────┐
               │                │                │
         ┌─────┴──────┐   ┌────┴─────┐   ┌──────┴─────┐
         │ Chat Agent │   │ PJM Agent │   │ Sync Agent │  independent processes
         │ (FastAPI)  │   │ (FastAPI) │   │ (FastAPI)  │
         └─────┬──────┘   └────┬─────┘   └──────┬─────┘
               │  HTTP REST    │                │
               └──(AgentClient)┘                │
                       │                        │
        ┌──────────────┼────────────────────────┘
        │              │              │
   ┌────┴───┐   ┌─────┴─────┐   ┌────┴───┐
   │ Redis  │   │ EventBus  │   │  PG    │  per-agent isolation
   │  8     │   │ (Streams) │   │  18    │
   └────────┘   └───────────┘   └────────┘
```

### Inter-Agent Communication

Agents must not import each other directly in Python. They communicate through explicit runtime boundaries:

| Scenario | Mechanism | Example |
|----------|-----------|---------|
| Synchronous request/response | HTTP REST via `AgentClient` | Approval, status query |
| Asynchronous workflow | Redis Streams via `EventBus` | Requirement change -> sync task |
| Human approval | Feishu card callback -> Gateway -> Agent | WBS approval |

See [ADR-0004: Inter-Agent HTTP Communication](./docs/adr/0004-inter-agent-http-communication.md).

---

## Agent Operating Model

```text
Acquisition -> Conversion -> R&D -> Delivery -> Support -> Iteration
     |             |          |          |          |           |
   Agents        Agents     Agents     Agents     Agents      Agents
                              |
                              └── Requirement Manager Agent
```

Wisdoverse Cell is designed for 26 agents across the full company lifecycle. The current implementation includes the core agent runtime, gateway, requirement management, project management, sync, analysis, QA, and evolution foundations.

### Product Model Roadmap

| Layer | Current implementation | Next product milestone |
|-------|------------------------|------------------------|
| Goal layer | Requirement extraction and PRD generation | Goal hierarchy with ownership, success metrics, and ancestry on every work item |
| Work layer | PJM decomposition, OpenProject sync, Feishu approvals | Native ticket ledger with dependency, blocker, artifact, and decision records |
| Run layer | AgentRuntime, EventBus, tracing, QA checks | Heartbeat scheduler, resumable runs, and execution locks |
| Governance layer | Approval cards and service-level auth | Board console for approve, pause, resume, terminate, and rollback actions |
| Budget layer | LLM daily budget, fallback models, cost-aware routing | Per-agent and per-goal budget policies with hard stops |
| Portability layer | Docker Compose deployment and env templates | Exportable company templates with secret scrubbing |

---

## Core Concepts

### Event-Driven Communication

Agents publish immutable events through Redis Streams:

```json
{
  "event_id": "evt_01HQ3K4N...",
  "event_type": "requirement.confirmed",
  "source_agent": "requirement-manager",
  "payload": { "requirement_id": "req_001", "title": "..." },
  "schema_version": "1.0",
  "trace_id": "trace_01HQ3K...",
  "timestamp": "2026-01-20T14:30:00Z"
}
```

### HTTP Agent Calls

Synchronous calls use `AgentClient` and `X-Internal-Key` authentication:

```python
from shared.infra.agent_client import PMAgentClient

client = PMAgentClient()
result = await client.approve_decomposition(wp_id=42, operator="alice")
```

### Base Agent Interface

All agents inherit `BaseAgent` and implement the shared runtime contract:

```python
class MyAgent(BaseAgent):
    async def handle_event(self, event: Event) -> list[Event]:
        pass

    async def handle_request(self, request: dict) -> dict:
        pass
```

### Human-in-the-Loop

Finance, legal, customer relationship, and technical architecture decisions require human approval.

---

## Status

| Module | Status | Completion |
|--------|:------:|:----------:|
| Core infrastructure: EventBus, LLM Gateway, BaseAgent | Active | Implemented, still hardening |
| Requirement Manager Agent | Active | Implemented with tests |
| Go API Gateway | Active | Feishu/WeCom webhook paths implemented |
| Chat Agent | Active | User-facing workflow support |
| PJM Agent | Active | Task decomposition and approval flows |
| Sync Agent | Active | OpenProject and Feishu sync foundation |
| Inter-agent decoupling | Active | HTTP/EventBus contracts in place |
| Analysis Agent | In progress | Risk detection foundation |
| Observability | In progress | Metrics, tracing, and alert rules |
| Next.js frontend | In progress | Console UI and i18n foundation |
| Remaining agents | Planned | 0% |

---

## Architecture Decision Records

| ADR | Title | Status |
|-----|-------|:------:|
| [ADR-0001](./docs/adr/0001-redis-streams-eventbus.md) | Redis Streams EventBus | Accepted |
| [ADR-0002](./docs/adr/0002-per-agent-db-isolation.md) | Per-Agent Database Isolation | Accepted |
| [ADR-0003](./docs/adr/0003-tiered-llm-model-strategy.md) | Tiered LLM Model Strategy | Accepted |
| [ADR-0004](./docs/adr/0004-inter-agent-http-communication.md) | Inter-Agent HTTP Communication | Accepted |

---

## Documentation

See [docs/INDEX.md](./docs/INDEX.md) for the full documentation index.

Core documents:

- [Product Model](./docs/overview/product-model.md)
- [Wisdoverse Cell PRD](./docs/specs/wisdoverse-cell-prd.md)
- [Requirement Manager Agent PRD](./docs/specs/requirement-manager-agent-prd.md)
- [Architecture Overview](./docs/overview/architecture.md)
- [Onboarding Guide](./docs/overview/onboarding.md)
- [Agent Development Guide](./docs/guides/agent-development.md)
- [Operations Guide](./docs/guides/operations.md)

---

## Environment

See `.env.example` for the full configuration surface.

```bash
# LLM
ANTHROPIC_API_KEY=<your-anthropic-api-key>
REQUIRE_ANTHROPIC_PROXY=true
LLM_DAILY_BUDGET_USD=50

# Database
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=your_password

# Redis
REDIS_HOST=localhost
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# Inter-service communication
INTERNAL_SERVICE_KEY=your_internal_key
PM_AGENT_URL=http://pjm-agent:8012

# Feishu integration, optional
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
FEISHU_ENABLED=true
```

---

## Security

- Inter-agent authentication with `X-Internal-Key`
- Feishu and WeCom webhook signature verification
- Prompt-injection defenses with delimiter isolation
- PII controls before LLM calls
- Optional outbound proxy enforcement for Claude API calls
- DSAR APIs for data subject access, export, and deletion
- Per-agent Redis DB and PostgreSQL user isolation
- Real-time LLM budget controls with fallback behavior

See [SECURITY.md](./SECURITY.md).

---

## License

Wisdoverse Cell is source-available under the Wisdoverse Cell Business Source
License 1.1 (`LicenseRef-Wisdoverse-Cell-BSL-1.1`), aligned with the
Wisdoverse Nexus license model.

It permits personal learning, research, education, development and testing,
internal evaluation, and non-production use. Commercial production use, SaaS or
hosted services, managed services, resale, sublicensing, and competing products
require a separate commercial license.

Each version automatically becomes available under the Apache License, Version
2.0 four years after that version is first made publicly available. See
[LICENSE](./LICENSE).
