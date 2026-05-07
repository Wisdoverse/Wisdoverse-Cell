# Agent Runtime Framework (`shared/app`)

> Eliminate boilerplate, standardize agent creation.

## Purpose

Every Agent in Wisdoverse Cell needs the same infrastructure: FastAPI wiring, health checks, middleware, Prometheus metrics, OpenTelemetry tracing, and evolution system integration. The `shared/app` module provides a single function -- `create_agent_app()` -- that configures all of this in one call.

Before this module existed, each agent duplicated ~100 lines of setup code. Now a complete agent entry point is three lines:

```python
from shared.app import create_agent_app
from ..service.agent import agent

app = create_agent_app(agent, title="My Agent")
```

---

## Quick Start

```python
from fastapi import APIRouter, Depends
from shared.app import create_agent_app
from shared.schemas.agent import BaseAgent

class MyAgent(BaseAgent):
    async def handle_event(self, event):
        return []

    async def handle_request(self, request):
        return {"status": "ok"}

router = APIRouter()

@router.get("/api/v1/my-endpoint")
async def my_endpoint():
    return {"data": "hello"}

app = create_agent_app(
    MyAgent(agent_id="my-agent", agent_name="My Agent"),
    title="My Agent",
    routers=[(router, [Depends(verify_internal_key)])],
)
```

This gives you:

- `/health` (liveness) and `/health/ready` (readiness) endpoints
- `RequestTracingMiddleware`, `APIKeyMiddleware`, `AccessLogMiddleware`, `RateLimitMiddleware`, `SecurityHeadersMiddleware`
- CORS (allow all origins)
- OpenTelemetry tracing (`init_tracing`, `instrument_fastapi`, `instrument_httpx`)
- Prometheus metrics at `/metrics`
- Evolution wrapping via `EvolutionPlugin` (opt-out with `evolution_excluded=True`)
- Unified exception handlers
- Lifespan-managed startup/shutdown

---

## Plugin System

### `RuntimePlugin` ABC

Plugins extend the agent runtime without modifying `AgentRuntime` itself (Open/Closed principle). Each plugin can hook into three lifecycle phases:

| Method | When | Purpose |
|--------|------|---------|
| `wrap_agent(agent)` | Before startup | Return a wrapped agent (decorator pattern) |
| `startup(runtime)` | After agent wrapping, before event loop | Async initialization (connect to Redis, etc.) |
| `shutdown(runtime)` | Before agent.shutdown() | Async cleanup |
| `health_check()` | On readiness check | Return dict of health indicators |

### Plugin Lifecycle

```
create_agent_app()
    |
    v
AgentRuntime(agent).use(plugin_1).use(plugin_2)
    |
    v  [startup]
1. plugin_1.wrap_agent(agent) -> wrapped_1
2. plugin_2.wrap_agent(wrapped_1) -> wrapped_2
3. plugin_1.startup(runtime)
4. plugin_2.startup(runtime)
5. agent.startup()
6. start_event_loop()
    |
    v  [shutdown]
1. cancel event listener
2. plugin_2.shutdown(runtime)   # reverse order
3. plugin_1.shutdown(runtime)   # reverse order
4. agent.shutdown()
```

### `EvolutionPlugin` (Built-in)

The default plugin wraps agents with `EvolvedAgent` for execution tracing and self-optimization. It:

1. **wrap_agent**: Creates `EvolvedAgent(agent, db_manager=...)` if evolution is enabled
2. **startup**: Connects Redis and wires the `KillSwitch`
3. **shutdown**: Closes the Redis connection
4. **health_check**: Reports `{"evolution_redis": true/false}`

Disable evolution wrapping for agents that should not self-evolve (e.g., evolution-module itself):

```python
app = create_agent_app(agent, evolution_excluded=True)
```

Or disable the entire evolution plugin:

```python
app = create_agent_app(agent, evolution_enabled=False)
```

---

## Writing a Custom Plugin

```python
from shared.app.runtime import RuntimePlugin, AgentRuntime
from shared.schemas.agent import BaseAgent

class MetricsPlugin(RuntimePlugin):
    """Example: custom business metrics collection."""

    name = "custom-metrics"

    def __init__(self, namespace: str = "project_cell"):
        self._namespace = namespace
        self._counter = 0

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        # Optionally wrap the agent to intercept handle_event calls.
        # Return agent unchanged to skip wrapping.
        return agent

    async def startup(self, runtime: AgentRuntime) -> None:
        # Initialize external connections, register Prometheus counters, etc.
        logger.info("metrics_plugin_started", agent_id=runtime.agent_id)

    async def shutdown(self, runtime: AgentRuntime) -> None:
        # Flush pending metrics, close connections.
        logger.info("metrics_plugin_stopped", agent_id=runtime.agent_id)

    async def health_check(self) -> dict[str, Any]:
        return {"custom_metrics_ok": True, "events_counted": self._counter}
```

Register it alongside built-in plugins:

```python
from shared.app.runtime import AgentRuntime, EvolutionPlugin

runtime = AgentRuntime(my_agent)
runtime.use(EvolutionPlugin())
runtime.use(MetricsPlugin(namespace="my_project"))
await runtime.startup()
```

Or use the factory's `on_startup` hook to access the runtime:

```python
async def wire_custom_plugins(runtime):
    runtime.use(MetricsPlugin())

app = create_agent_app(agent, on_startup=wire_custom_plugins)
```

---

## API Reference

### `create_agent_app()`

```python
def create_agent_app(
    agent: BaseAgent,
    *,
    title: str = "",
    description: str = "",
    version: str = "1.0.0",
    routers: list[Any] | None = None,
    on_startup: Callable[..., Coroutine] | None = None,
    on_shutdown: Callable[..., Coroutine] | None = None,
    evolution_enabled: bool = True,
    evolution_excluded: bool = False,
    include_api_key_middleware: bool = True,
) -> FastAPI
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `agent` | (required) | `BaseAgent` instance |
| `title` | `agent.agent_name` | FastAPI app title |
| `description` | auto-generated | FastAPI app description |
| `version` | `"1.0.0"` | API version |
| `routers` | `None` | List of `APIRouter` or `(router, [dependencies])` tuples |
| `on_startup` | `None` | Async callback after `runtime.startup()`, receives `runtime` |
| `on_shutdown` | `None` | Async callback before `runtime.shutdown()`, receives `runtime` |
| `evolution_enabled` | `True` | Register `EvolutionPlugin` |
| `evolution_excluded` | `False` | Skip evolution wrapping (pass-through) |
| `include_api_key_middleware` | `True` | Include `APIKeyMiddleware` |

### `AgentRuntime`

```python
class AgentRuntime:
    def __init__(self, agent: BaseAgent): ...
    def use(self, plugin: RuntimePlugin) -> AgentRuntime: ...
    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...
    def start_event_loop(self) -> None: ...
    async def health_check(self) -> dict[str, Any]: ...

    @property
    def agent(self) -> BaseAgent: ...      # The fully wrapped agent
    @property
    def agent_id(self) -> str: ...
```

### `RuntimePlugin`

```python
class RuntimePlugin(ABC):
    name: str = "unnamed"
    def wrap_agent(self, agent: BaseAgent) -> BaseAgent: ...
    async def startup(self, runtime: AgentRuntime) -> None: ...
    async def shutdown(self, runtime: AgentRuntime) -> None: ...
    async def health_check(self) -> dict[str, Any]: ...
```

---

## File Map

| File | Purpose |
|------|---------|
| `factory.py` | `create_agent_app()` — one-line FastAPI app creation |
| `runtime.py` | `AgentRuntime`, `RuntimePlugin`, `EvolutionPlugin` |
| `__init__.py` | Re-exports `create_agent_app` |
