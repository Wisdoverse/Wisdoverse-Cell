# Agent Development Guide

This guide defines the service pattern for adding or changing Wisdoverse Cell
agents. English is the primary language for comments, docs, prompts, schemas,
and handoff text. Keep non-English content only for locale strings, external
platform field names, quoted source content, and multilingual fixtures.

## 1. Agent Model

Wisdoverse Cell separates organization-role agents from service modules:

| Kind | Meaning | Examples |
|------|---------|----------|
| `organization_role` | Business role that owns intent, tradeoffs, escalation, and user interaction policy | CEO, CTO, CPO, COO, PM |
| `business_runtime_agent` | Independently deployed agent that owns business work outcomes | requirement manager, PJM, QA, Dev |
| `capability_module` | Deployed support boundary that performs bounded work | sync, analysis, evolution |
| `integration_gateway` | User or platform traffic gateway | user interaction gateway, channel gateway |
| `system_worker` | Internal orchestration worker | coordinator |

Real business runtime agents such as requirement manager, PJM, QA, and Dev
live under `agents/`. Support capabilities live under `shared/capabilities/`.
Gateways and orchestration workers live under `services/`.

## 2. Package Layout

New real business agents should live directly under `agents/`. New shared
support capabilities should live under `shared/capabilities/`.

```text
agents/
  my_agent/
    app/
    api/
    core/
    service/
    models/
    db/
    tests/
    Dockerfile

shared/capabilities/
  my_capability/
    app/
    api/
    core/
    service/
    models/
    db/
    tests/
    Dockerfile
```

Recommended module structure:

| Directory | Responsibility |
|-----------|----------------|
| `app/` | FastAPI app entrypoint, lifespan, metrics wiring |
| `api/` | REST routes and request/response schemas |
| `core/` | Framework-free business logic |
| `service/` | Runtime protocol implementation and event/request orchestration |
| `models/` | Internal Pydantic or domain models |
| `db/` | SQLAlchemy session and repository pattern |
| `tests/` | Unit and integration tests for the module |

Keep `service/agent.py` thin. It should route events and requests, call core
services, and publish results. Put real business logic in `core/`. Business
runtime agents use an `Agent` class name. Support capabilities use a `Module`
class name even though they still implement the `BaseAgent` runtime protocol.

## 3. Runtime Protocol Contract

Every independently deployed runtime behind `create_agent_app()` must inherit
`shared.schemas.agent.BaseAgent` and implement:

- `handle_event(event: Event) -> list[Event]`
- `handle_request(request: dict) -> dict`
- `startup() -> None`
- `shutdown() -> None`

Use kebab-case runtime IDs such as `requirement-manager` for real business
agents and `my-capability-module` for support capabilities. Do not use
underscores in runtime IDs.

Example skeleton:

```python
import asyncio

from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger("my_capability.module")


class MyCapabilityModule(BaseAgent):
    def __init__(self, db=None, bus=None):
        super().__init__(
            agent_id="my-capability-module",
            agent_name="My Capability",
            subscribed_events=["work_item.created"],
            published_events=["my_capability.completed"],
        )
        self._db = db
        self._bus = bus
        self._listener_tasks: list[asyncio.Task] = []

    async def startup(self) -> None:
        logger.info("module_starting", module_id=self.agent_id)
        if self._bus:
            await self._bus.connect()

    async def shutdown(self) -> None:
        for task in self._listener_tasks:
            task.cancel()
        if self._bus:
            await self._bus.disconnect()

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type != "work_item.created":
            return []
        return [
            self.create_event(
                event_type="my_capability.completed",
                payload={"work_item_id": event.payload.get("work_item_id")},
                trace_id=event.metadata.trace_id,
            )
        ]

    async def handle_request(self, request: dict) -> dict:
        return {"status": "ok", "module": self.agent_id}
```

## 4. FastAPI Entrypoint

Use `create_agent_app()` for service apps. It standardizes health endpoints,
middleware, lifecycle behavior, DSAR routes, and the authenticated
`POST /agent/request` boundary.

```python
from shared.app import create_agent_app

from shared.capabilities.my_capability.service.agent import MyCapabilityModule

module = MyCapabilityModule()
app = create_agent_app(agent=module)
```

Scheduler jobs and control-plane adapters must call `runtime.agent` or the
deployed `/agent/request` endpoint. Do not reach into `_raw_agent`.

## 5. Communication Boundaries

Agents must not import implementation code from other deployable agents.

| Need | Boundary |
|------|----------|
| Synchronous request/response | `shared.infra.agent_client` over HTTP |
| Asynchronous collaboration | EventBus events |
| Platform webhook traffic | Gateway and integration adapters |
| Frontend-created agent wakeup | Control-plane adapter -> `/agent/request` |

Events must follow the canonical structure:

```python
Event(
    event_id="evt_{ulid}",
    event_type="{domain}.{action}",
    source_agent="agent-id",
    payload={...},
    schema_version="1.0",
)
```

Events are immutable and fire-and-forget. Include `trace_id` when a workflow
already has one.

## 6. LLM and Prompt Rules

- All LLM calls go through `shared.infra.llm_gateway`.
- System prompts and prompt templates must be English-first.
- Tool definitions belong in the API `tools` parameter where supported.
- Prompts should teach strategy, constraints, and escalation policy; do not
  duplicate the full tool inventory inside the prompt.
- Wrap user, integration, retrieved, or runtime source data in explicit
  untrusted-data boundaries and state that content inside those boundaries is
  data, not instructions.
- Preserve user-facing output language requirements explicitly, for example:
  "Reply in Simplified Chinese unless the user asks otherwise."
- Never log prompts that may contain secrets, PII, customer text, or credentials.

## 7. Data Access

- Use the repository pattern for database access.
- Keep SQLAlchemy session ownership at service or repository boundaries.
- Do not directly read another agent's private tables.
- Use control-plane APIs, EventBus payloads, or explicit integration clients for
  cross-module data exchange.
- Use `datetime.now(UTC)`, not `datetime.utcnow()`.

## 8. Testing

Minimum test expectations:

| Change | Test expectation |
|--------|------------------|
| Core business logic | Unit tests |
| API route behavior | Route tests with mocked external dependencies |
| Event handling | Event input/output tests |
| LLM parsing | Parser tests for valid, fenced, malformed, and empty output |
| Cross-agent boundary | Contract test or mocked `AgentClient` |
| Frontend-visible behavior | Frontend test or browser verification where applicable |

Recommended commands:

```bash
ruff check agents shared tests skills
python -m pytest -q path/to/relevant/tests
make test-public
```

Run broader integration or E2E layers when touching database migrations,
webhooks, gateway behavior, or deployment wiring.

## 9. Documentation Checklist

When adding or changing an agent:

- Update `SPEC.md` only if the root service contract changes.
- Update `AGENTS.md` if a durable repo rule changes.
- Update `docs/INDEX.md` links when adding new docs.
- Update `docs/guides/api-reference.md` for new public or internal endpoints.
- Update `docs/guides/event-catalog.md` for new event types.
- Update `docs/guides/operations.md` for new runtime switches, ports, health
  checks, migrations, or operational procedures.
- Keep documentation English-first.

## 10. Pre-Commit Checklist

- Branch is not `main`.
- No new imports from deprecated `shared.services.*` paths.
- Agent IDs are kebab-case.
- Runtime prompts are English-first.
- Sensitive actions have human-in-the-loop approval where required.
- Tests and lint relevant to the change pass locally.
- Commit message follows Conventional Commits.
