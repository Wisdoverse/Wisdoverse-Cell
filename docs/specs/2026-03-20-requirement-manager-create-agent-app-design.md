# Design: Migrate requirement_manager to create_agent_app()

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

**Issue**: #2
**Date**: 2026-03-20
**Status**: Final — Round 10 (all findings resolved)
**Review rounds completed**: 10/10

## Problem

requirement_manager is the only agent with a hand-written lifespan (~130 lines), manual middleware, manual health checks, and manual evolution wiring. All other agents use `create_agent_app()`. This creates:

- Duplicated boilerplate that drifts from the shared standard
- Inconsistent health check format across agents
- No plugin reusability for gRPC, channel registry, or background tasks

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Health check extensibility | Each Plugin contributes its own checks | Single Responsibility; K8s readiness = sum of plugin health |
| Health check type | `HealthCheckResult` only — no mixed bool/dict | Single canonical type, enforced by type signature (R1-H1) |
| Custom startup logic | All as RuntimePlugins | Composable, testable, reusable across agents |
| Static file serving | Remove | Cloud-native: frontend served by CDN/Nginx, not API process |
| Factory health check | Extend to support critical vs degraded | Milvus down = degraded, PG down = not ready |
| Plugin placement | Agent-specific plugins in agent dir, shared plugins in shared/ | No upward dependencies from shared/ to agents/ |
| Rollback | Parallel module import, lazy load (R1-C5) | Python import-safety: both modules are always importable |
| CORS | Factory reads `settings.cors_*` directly, no getattr fallback | Fail loudly on misconfiguration (R1-SRE-CORS) |
| APIKeyMiddleware | Keep enabled; webhook routers use path exemptions | Preserve auth on admin/export/requirements endpoints (R1-C8) |
| Dependency injection | Constructor injection, not getattr on private attrs (R1-C1) | Testable, explicit, type-safe |
| Health check keys | Namespaced under plugin.name to prevent collision (R1-H3) | `infra-health.postgres`, `grpc.grpc`, etc. |
| Health check detail | Sanitized — `type(exc).__name__` only, no `str(exc)` (R1-C7) | Prevents credential leakage in health endpoint |
| Readiness endpoint | Two tiers: `/health/ready` (public, minimal) + `/health/ready/detail` (internal key) | Operational data requires auth (R1-H9) |
| Plugin startup timeout | 30s per plugin via `asyncio.wait_for` | Prevents indefinite hang (R1-SRE) |
| Plugin shutdown timeout | 10s per plugin, total < terminationGracePeriodSeconds (R1-H7) | K8s SIGKILL coordination |
| Health probes | Persistent connections, created at startup, reused in checks (R1-C2, R1-H6) | No thundering herd on probe cycle |
| K8s probes | Define startupProbe, livenessProbe, readinessProbe configs (R1-C9) | Cloud-native readiness |
| api_v1_redirect | Keep as deprecated route until client audit completes (R1-C6) | Safe migration, no silent 404s |

## Architecture

### Plugin Placement

```
shared/app/plugins/               # Reusable across agents
  __init__.py
  infra_health.py                  # InfraHealthPlugin (PG/Redis/Milvus/NATS probes)

agents/requirement_manager/app/plugins/   # Agent-specific
  __init__.py
  grpc.py                          # GrpcPlugin
  channel_registry.py              # ChannelRegistryPlugin
  feishu_gateway.py                # FeishuGatewayPlugin
  session_timeout.py               # SessionTimeoutPlugin
```

Rationale: `shared/app/plugins/` must not import from `agents/`. Agent-specific plugins that depend on agent internals live in the agent's own directory.

### HealthCheckResult (shared/app/runtime.py)

Single canonical type for all health check data. No mixed bool/dict returns.

```python
@dataclass(frozen=True)
class HealthCheckResult:
    """Typed health check result with criticality."""
    status: Literal["ok", "degraded", "down"]
    detail: str = ""

    @property
    def is_critical(self) -> bool:
        return self.status == "down"

    def __bool__(self) -> bool:
        """Backward compatible: True if ok or degraded."""
        return self.status != "down"

    def to_dict(self) -> dict[str, str]:
        """Serialize for JSON response."""
        return {"status": self.status, "detail": self.detail}
```

**Type enforcement**: `RuntimePlugin.health_check()` return type is `dict[str, HealthCheckResult]` (not `Any`).

**EvolutionPlugin migration** (R3-H2): Update `EvolutionPlugin.health_check()` in `shared/app/runtime.py`:
```python
# Before (current):
async def health_check(self) -> dict[str, Any]:
    return {"evolution_redis": self._redis_client is not None}

# After — preserves key name to avoid dashboard breakage (R5-Arch):
async def health_check(self) -> dict[str, HealthCheckResult]:
    if self._redis_client is not None:
        return {"evolution_redis": HealthCheckResult("ok")}
    return {"evolution_redis": HealthCheckResult("degraded", "kill switch not connected")}
```
This is a required change in this PR, not a follow-up. Key name preserved as `evolution_redis` (not renamed to `redis`) to avoid breaking existing dashboards — after namespacing it becomes `evolution.evolution_redis`.

### Health Check Aggregation (AgentRuntime)

```python
async def health_check(self) -> dict[str, HealthCheckResult]:
    """Aggregate all plugin health checks with namespacing and timeouts."""
    checks: dict[str, HealthCheckResult] = {}
    checks["agent_started"] = HealthCheckResult(
        "ok" if self._started else "down",
        "" if self._started else "runtime not started",
    )

    # Run all plugin health checks concurrently with per-plugin timeout
    async def _safe_check(plugin: RuntimePlugin) -> dict[str, HealthCheckResult]:
        try:
            return await asyncio.wait_for(plugin.health_check(), timeout=5)
        except asyncio.TimeoutError:
            return {"_timeout": HealthCheckResult("down", "health check timeout")}
        except Exception as e:
            return {"_error": HealthCheckResult("down", type(e).__name__)}

    results = await asyncio.gather(*[_safe_check(p) for p in self._plugins])
    for plugin, plugin_checks in zip(self._plugins, results):
        for key, result in plugin_checks.items():
            checks[f"{plugin.name}.{key}"] = result

    return checks
```

Key improvements:
- **Concurrent** — `asyncio.gather` not sequential (R1-Platform: probe timeout)
- **Namespaced** — `plugin.name.key` prevents collision (R1-H3)
- **Timeout** — 5s per plugin, prevents slow dependency from blocking entire probe
- **Exception-safe** — returns HealthCheckResult("down") on any failure

### Factory Readiness Endpoints (shared/app/factory.py)

Two-tier health endpoint (R1-H9):

```python
@app.get("/health/ready", tags=["health"])
async def readiness():
    """Public readiness probe — minimal response for K8s."""
    checks = await runtime.health_check()
    has_critical = any(r.status == "down" for r in checks.values())
    has_degraded = any(r.status == "degraded" for r in checks.values())

    if has_critical:
        status, code = "not_ready", 503
    elif has_degraded:
        status, code = "degraded", 200
    else:
        status, code = "ready", 200

    return JSONResponse(status_code=code, content={"status": status, "agent": runtime.agent_id})

@app.get("/health/ready/detail", tags=["health"], dependencies=[Depends(verify_internal_key)])
async def readiness_detail():
    """Internal readiness detail — requires API key. Includes all check results."""
    checks = await runtime.health_check()
    has_critical = any(r.status == "down" for r in checks.values())
    has_degraded = any(r.status == "degraded" for r in checks.values())

    if has_critical:
        status, code = "not_ready", 503
    elif has_degraded:
        status, code = "degraded", 200
    else:
        status, code = "ready", 200

    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "agent": runtime.agent_id,
            "checks": {k: v.to_dict() for k, v in checks.items()},
        },
    )
```

### Startup Probe Endpoint

```python
@app.get("/health/startup", tags=["health"])
async def startup_probe():
    """K8s startupProbe — 200 only after runtime fully initialized."""
    if runtime.is_started:  # R3-PM: public property, not private attr
        return {"status": "started"}
    return JSONResponse(status_code=503, content={"status": "starting"})
```

### K8s Probe Configuration (recommended)

```yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: 8000
  failureThreshold: 30
  periodSeconds: 2          # Max 60s startup window
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
  periodSeconds: 10
  timeoutSeconds: 10        # Must exceed sum of probe timeouts (5s gather timeout)
  failureThreshold: 2
```

### New Shared Plugin

#### InfraHealthPlugin (shared/app/plugins/infra_health.py)

Constructor injection. Persistent connections. Sanitized error detail.

```python
class InfraHealthPlugin(RuntimePlugin):
    """Readiness probes for infrastructure dependencies."""
    name = "infra-health"

    def __init__(
        self,
        *,
        db_manager=None,          # Injected, not getattr'd (R1-C1)
        event_bus=None,           # Injected
        milvus_uri: str = "",     # Validated (R1-Security-SSRF)
        check_postgres: bool = True,
        check_redis: bool = True,
        check_milvus: bool = False,
        check_nats: bool = False,
        check_postgres_replica: bool = False,
    ):
        self._db_manager = db_manager
        self._event_bus = event_bus
        self._milvus_uri = milvus_uri
        self._milvus_health_url: str | None = None
        self._redis_client = None     # Persistent connection (R1-C2)
        self._httpx_client = None     # Persistent connection (R1-H6)
        self._checks = {
            "postgres": check_postgres,
            "redis": check_redis,
            "milvus": check_milvus,
            "nats": check_nats,
            "postgres_replica": check_postgres_replica,
        }

    async def startup(self, runtime):
        """Create persistent probe connections. Fail-fast on misconfiguration."""
        # Late-bind db_manager/event_bus if not injected (from runtime.agent)
        if self._db_manager is None:
            self._db_manager = getattr(runtime.agent, "_db_manager", None)
        if self._event_bus is None:
            self._event_bus = getattr(runtime.agent, "_event_bus", None)

        # Validate required dependencies
        if self._checks["postgres"] and self._db_manager is None:
            raise RuntimeError("InfraHealthPlugin: check_postgres=True but db_manager is None")
        if self._checks["nats"] and self._event_bus is None:
            raise RuntimeError("InfraHealthPlugin: check_nats=True but event_bus is None")

        # Persistent Redis probe client (R1-C2: no new connection per probe)
        if self._checks["redis"]:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(
                settings.redis_url, socket_connect_timeout=2, decode_responses=True
            )

        # Persistent httpx client for Milvus probe (R1-H6)
        if self._checks["milvus"]:
            self._milvus_health_url = self._validate_milvus_url(self._milvus_uri or settings.milvus_uri)
            import httpx
            self._httpx_client = httpx.AsyncClient(timeout=2, follow_redirects=False)  # R3-H5: no redirect following

    async def shutdown(self, runtime):
        if self._redis_client:
            await self._redis_client.aclose()
        if self._httpx_client:
            await self._httpx_client.aclose()

    @staticmethod
    def _validate_milvus_url(uri: str) -> str:
        """Validate Milvus URI to prevent SSRF (R1-Security-SSRF, R3-C1 fix)."""
        from urllib.parse import urlparse
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"InfraHealthPlugin: invalid milvus scheme: {parsed.scheme}")

        # Block dangerous IPs (R3-C1: fixed operator precedence, separate try/except)
        import ipaddress
        hostname = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None  # hostname, not IP — DNS validation below

        if ip is not None:
            # Block link-local (169.254.x.x — cloud metadata) unconditionally
            if ip.is_link_local:
                raise ValueError(f"InfraHealthPlugin: link-local address blocked: {hostname}")
            # Block private/reserved IPs except known Milvus ports on loopback (dev only)
            if ip.is_private and not (ip.is_loopback and parsed.port in (19530, 9091)):
                raise ValueError(f"InfraHealthPlugin: private address blocked: {hostname}")

        # Known limitation: hostname-based URIs (not raw IPs) are not DNS-validated.
        # A resolvable internal hostname could bypass IP checks. Mitigated by:
        # 1. httpx follow_redirects=False prevents redirect-based SSRF
        # 2. milvus_uri is set by operators, not user input
        # 3. Health probe response is minimal (public endpoint shows no detail)

        # Derive health URL (Milvus standalone: port 9091)
        health_port = 9091
        return f"{parsed.scheme}://{hostname}:{health_port}"

    async def health_check(self) -> dict[str, HealthCheckResult]:
        results: dict[str, HealthCheckResult] = {}

        if self._checks["postgres"]:
            try:
                async with self._db_manager.session() as session:
                    await session.execute(text("SELECT 1"))
                results["postgres"] = HealthCheckResult("ok")
            except Exception as exc:
                results["postgres"] = HealthCheckResult("down", type(exc).__name__)

        if self._checks["redis"] and self._redis_client:
            try:
                await self._redis_client.ping()
                results["redis"] = HealthCheckResult("ok")
            except Exception as exc:
                results["redis"] = HealthCheckResult("down", type(exc).__name__)

        if self._checks["milvus"] and self._httpx_client:
            try:
                resp = await self._httpx_client.get(f"{self._milvus_health_url}/healthz")
                resp.raise_for_status()
                results["milvus"] = HealthCheckResult("ok")
            except Exception as exc:
                results["milvus"] = HealthCheckResult("degraded", type(exc).__name__)

        if self._checks["nats"]:
            try:
                if hasattr(self._event_bus, "is_connected") and self._event_bus.is_connected:
                    results["nats"] = HealthCheckResult("ok")
                else:
                    results["nats"] = HealthCheckResult("down", "disconnected")
            except Exception as exc:
                results["nats"] = HealthCheckResult("down", type(exc).__name__)

        if self._checks["postgres_replica"] and self._db_manager:
            if not self._db_manager.read_engine:
                results["postgres_replica"] = HealthCheckResult("degraded", "no read engine configured")
            else:
                try:
                    async with self._db_manager.read_session_ctx() as rsession:
                        result = await rsession.execute(text("SELECT pg_is_in_recovery()"))
                        if result.scalar():
                            results["postgres_replica"] = HealthCheckResult("ok")
                        else:
                            results["postgres_replica"] = HealthCheckResult("degraded", "not in recovery mode")
                except Exception as exc:
                    results["postgres_replica"] = HealthCheckResult("degraded", type(exc).__name__)

        # DB pool stats — informational, included in detail only (R3-M3)
        if self._db_manager and hasattr(self._db_manager, "pool_status"):
            try:
                pool = self._db_manager.pool_status()
                results["db_pool"] = HealthCheckResult("ok", str(pool))
            except Exception:
                pass  # Non-critical, skip silently

        return results
```

### Agent-Specific Plugins (agents/requirement_manager/app/plugins/)

#### 1. GrpcPlugin

```python
class GrpcPlugin(RuntimePlugin):
    """Starts/stops a gRPC server alongside the FastAPI process."""
    name = "grpc"

    def __init__(self, *, server_factory=None, port: int | None = None):
        self._server_factory = server_factory  # Injected for testability
        self._port = port
        self._server = None

    async def startup(self, runtime):
        factory = self._server_factory
        if factory is None:
            from agents.requirement_manager.grpc.server import run_with_fastapi
            factory = run_with_fastapi
        self._server = await factory(agent=runtime.agent, port=self._port)

    async def shutdown(self, runtime):
        if self._server:
            await asyncio.wait_for(self._server.stop(grace=5), timeout=8)

    async def health_check(self) -> dict[str, HealthCheckResult]:
        return {"server": HealthCheckResult("ok") if self._server else HealthCheckResult("down", "not started")}
```

#### 2. ChannelRegistryPlugin

```python
class ChannelRegistryPlugin(RuntimePlugin):
    """Registers messaging channels (Feishu, WeCom, OpenClaw) based on settings."""
    name = "channel-registry"

    def __init__(self):
        self._openclaw_client = None
        self._openclaw_task = None
        self._expected_channels = 0

    async def startup(self, runtime):
        if settings.feishu_enabled:
            self._expected_channels += 1
            feishu_adapter = FeishuChannelAdapter(client=get_feishu_client())
            ChannelRegistry.register(feishu_adapter)

        if settings.wecom_enabled:
            self._expected_channels += 1
            wecom_adapter = WecomChannelAdapter(client=get_wecom_client())
            ChannelRegistry.register(wecom_adapter)

        if settings.openclaw_enabled:
            self._expected_channels += 1
            self._openclaw_client = OpenClawClient(
                gateway_url=settings.openclaw_gateway_url,
                device_id=settings.openclaw_device_id,
                auth_token=settings.openclaw_gateway_token,
            )
            openclaw_adapter = OpenClawChannelAdapter(client=self._openclaw_client)
            ChannelRegistry.register(openclaw_adapter)
            self._openclaw_task = asyncio.create_task(self._openclaw_client.connect())

    async def shutdown(self, runtime):
        if self._openclaw_client:
            await self._openclaw_client.disconnect()
        if self._openclaw_task and not self._openclaw_task.done():
            self._openclaw_task.cancel()
            try:
                await asyncio.wait_for(self._openclaw_task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if self._expected_channels == 0:
            return {}  # No channels configured, skip
        registered = len(ChannelRegistry.list_channels()) if hasattr(ChannelRegistry, 'list_channels') else 0
        if registered >= self._expected_channels:
            return {"channels": HealthCheckResult("ok", f"{registered} registered")}
        return {"channels": HealthCheckResult("degraded", f"{registered}/{self._expected_channels} registered")}
```

#### 3. FeishuGatewayPlugin

```python
class FeishuGatewayPlugin(RuntimePlugin):
    """Initializes Feishu gateway with agent, DB, Redis, PM client."""
    name = "feishu-gateway"

    def __init__(self, *, pm_client_factory=None):
        self._pm_client_factory = pm_client_factory  # Injected for testability (R1-H2)
        self._redis_client = None
        self._initialized = False

    async def startup(self, runtime):
        if not settings.feishu_enabled:
            return  # Skip entirely if feishu disabled (R1-H4)

        if settings.feishu_message_recording_enabled:
            from redis.asyncio import Redis as AsyncRedis
            self._redis_client = AsyncRedis.from_url(
                settings.redis_url, decode_responses=False
            )

        factory = self._pm_client_factory
        if factory is None:
            from shared.infra.agent_client import PMAgentClient
            factory = PMAgentClient

        db_manager = getattr(runtime.agent, "_db_manager", None)
        result = await init_feishu_gateway(
            agent=runtime.agent,
            db=db_manager,
            redis=self._redis_client,
            pm_client=factory(),
        )
        # Fail-fast if init_feishu_gateway returns falsy (R1-C3)
        if not result:
            raise RuntimeError("FeishuGatewayPlugin: init_feishu_gateway failed")
        self._initialized = True

    async def shutdown(self, runtime):
        if self._redis_client:
            await self._redis_client.aclose()  # R3-M5: consistent with InfraHealthPlugin

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not settings.feishu_enabled:
            return {}  # Not applicable, skip entirely (R1-H4)
        return {"gateway": HealthCheckResult("ok" if self._initialized else "down", "")}
```

#### 4. SessionTimeoutPlugin

```python
class SessionTimeoutPlugin(RuntimePlugin):
    """Background task that checks session timeouts every N seconds."""
    name = "session-timeout"

    def __init__(self, *, interval: int = 10):
        self._interval = interval
        self._task = None
        self._session_manager = None

    async def startup(self, runtime):
        if not settings.feishu_message_recording_enabled:
            return
        self._session_manager = get_session_manager()
        self._task = asyncio.create_task(self._checker_loop())

    async def shutdown(self, runtime):
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def _checker_loop(self):
        while True:
            try:
                if self._session_manager:
                    await self._session_manager.check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("session_timeout_check_error", error=type(e).__name__)
            await asyncio.sleep(self._interval)

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not settings.feishu_message_recording_enabled:
            return {}
        if self._task is None:
            return {"checker": HealthCheckResult("down", "task not created")}
        if self._task.done():
            exc = self._task.exception() if not self._task.cancelled() else None
            detail = type(exc).__name__ if exc else "task exited"
            return {"checker": HealthCheckResult("degraded", detail)}
        return {"checker": HealthCheckResult("ok")}
```

### Runtime Plugin Lifecycle Enhancement

Two-phase plugin startup to maintain EvolutionPlugin compatibility (R3-H4):

**RuntimePlugin base class update** (R5-SRE: add `pre_agent_startup` with no-op default):
```python
class RuntimePlugin:
    name: str = "unnamed"

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        return agent

    async def pre_agent_startup(self, runtime: "AgentRuntime") -> None:
        """Called BEFORE agent.startup(). Use for configuring the wrapped agent."""

    async def startup(self, runtime: "AgentRuntime") -> None:
        """Called AFTER agent.startup(). Use for accessing agent dependencies."""

    async def shutdown(self, runtime: "AgentRuntime") -> None:
        """Called during shutdown, in reverse plugin order."""

    async def health_check(self) -> dict[str, HealthCheckResult]:
        return {}
```

**AgentRuntime changes**:
```python
class AgentRuntime:
    ...
    @property
    def is_started(self) -> bool:
        """Public accessor for startup state (R5-PM: no private attr access)."""
        return self._started

    async def startup(self) -> None:
        start = time.monotonic()
        logger.info("runtime_starting", agent_id=self._raw_agent.agent_id)

        # Phase 1: Apply plugin wrappings (in order)
        agent = self._raw_agent
        for plugin in self._plugins:
            agent = plugin.wrap_agent(agent)
        self._agent = agent

        # Phase 2: Pre-agent plugin startups (e.g., EvolutionPlugin wires KillSwitch)
        for plugin in self._plugins:
            try:
                await asyncio.wait_for(plugin.pre_agent_startup(self), timeout=30)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Plugin '{plugin.name}' pre_agent_startup timed out")

        # Phase 3: Agent startup (initializes DB, event bus, etc.)
        await self._agent.startup()

        # Phase 4: Post-agent plugin startups (can access runtime.agent._db_manager)
        for plugin in self._plugins:
            try:
                await asyncio.wait_for(plugin.startup(self), timeout=30)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Plugin '{plugin.name}' startup timed out (30s)")

        self._started = True

    async def shutdown(self) -> None:
        """Shutdown with per-plugin timeout enforcement (R5-Arch)."""
        logger.info("runtime_stopping", agent_id=self.agent_id)

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        # Plugin shutdowns (reverse order, with per-plugin timeout)
        for plugin in reversed(self._plugins):
            try:
                await asyncio.wait_for(plugin.shutdown(self), timeout=10)
            except asyncio.TimeoutError:
                logger.error("plugin_shutdown_timeout", plugin=plugin.name)
            except Exception as e:
                logger.error("plugin_shutdown_error", plugin=plugin.name, error=type(e).__name__)

        try:
            await self._agent.shutdown()
        except Exception as e:
            logger.error("agent_shutdown_error", agent_id=self.agent_id, error=type(e).__name__)

        self._started = False
```

**Key changes**:
- **Two-phase startup**: `pre_agent_startup()` runs before agent (for EvolutionPlugin KillSwitch wiring), `startup()` runs after agent (for InfraHealthPlugin db_manager access) (R3-H4)
- **EvolutionPlugin**: Move `set_kill_switch()` call from `startup()` to `pre_agent_startup()`
- **`is_started` property**: Class-level, not nested inside `startup()` (R5-SRE formatting fix)
- **Shutdown per-plugin timeout**: 10s per plugin via `asyncio.wait_for` in runtime (R5-Arch), not just in plugin internals
- **Shutdown total**: 6 plugins × 10s = 60s max theoretical. Actual: most plugins finish in <1s. `terminationGracePeriodSeconds: 75` to be safe

### Factory Changes (shared/app/factory.py)

1. **Add `plugins` parameter** with proper typing
2. **CORS from settings** — direct attribute access, no getattr fallback
3. **Keep `include_api_key_middleware=True` as default** — requirement_manager uses path exemptions instead (R1-C8)
4. **Readiness two-tier** + startup probe endpoints

```python
def create_agent_app(
    agent: BaseAgent,
    *,
    title: str = "",
    description: str = "",
    version: str = "1.0.0",
    routers: list[Any] | None = None,
    plugins: list[RuntimePlugin] | None = None,    # NEW
    on_startup: ... = None,
    on_shutdown: ... = None,
    evolution_enabled: bool = True,
    evolution_excluded: bool = False,
    include_api_key_middleware: bool = True,
) -> FastAPI:
    runtime = AgentRuntime(agent)
    if evolution_enabled:
        runtime.use(EvolutionPlugin(excluded=evolution_excluded))
    for plugin in plugins or []:
        runtime.use(plugin)
    ...
    # CORS — direct settings access with guards (R3-M1, R5-Arch CORS+credentials)
    cors_origins = settings.cors_origins_list
    if not cors_origins and not settings.debug:
        raise ValueError("CORS_ALLOWED_ORIGINS must be set in non-debug environments")
    effective_origins = cors_origins or ["*"]
    cors_credentials = settings.cors_allow_credentials
    if effective_origins == ["*"] and cors_credentials:
        raise ValueError("Cannot set cors_allow_credentials=True with allow_origins=['*']")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=effective_origins,
        allow_methods=settings.cors_allowed_methods.split(","),
        allow_headers=settings.cors_allowed_headers.split(","),
        allow_credentials=settings.cors_allow_credentials,
        max_age=settings.cors_max_age,
    )
```

### Migrated requirement_manager/app/main_factory.py

```python
"""Requirement Manager Agent — FastAPI entry point via create_agent_app."""
from fastapi import Depends

from shared.app import create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.config import settings
from shared.integrations.feishu.router import router as feishu_router
from shared.integrations.wecom.router import router as wecom_router
from shared.middleware import verify_internal_key

from ..api import (
    admin_router,
    export_router,
    feedback_router,
    ingest_router,
    messages_router,
    requirements_router,
)
from ..service import agent
from .plugins import (
    ChannelRegistryPlugin,
    FeishuGatewayPlugin,
    GrpcPlugin,
    SessionTimeoutPlugin,
)
from .routes import api_info_router, api_v1_redirect_router

app = create_agent_app(
    agent,
    title="Requirement Manager Agent",
    description="需求管理Agent - 从会议记录中提取、追踪、管理客户需求",
    include_api_key_middleware=True,   # Auth on all routes (R1-C8)
    routers=[
        ingest_router,                 # Has own webhook path exemptions
        requirements_router,
        feedback_router,
        export_router,
        (admin_router, [Depends(verify_internal_key)]),
        messages_router,
        feishu_router,                 # Has own webhook path exemptions
        wecom_router,                  # Has own webhook path exemptions
        api_info_router,
        api_v1_redirect_router,        # Keep until client audit (R1-C6)
    ],
    plugins=[
        InfraHealthPlugin(
            milvus_uri=settings.milvus_uri,
            check_milvus=True,
            check_nats=settings.event_bus_backend == "nats",
            check_postgres_replica=bool(settings.database_read_url),  # R5: correct property name from shared/config.py
        ),
        GrpcPlugin(),
        ChannelRegistryPlugin(),
        FeishuGatewayPlugin(),
        SessionTimeoutPlugin(),
    ],
)
```

### Shutdown Order

```
Registration:  Evolution → InfraHealth → Grpc → ChannelRegistry → FeishuGateway → SessionTimeout
Shutdown:      SessionTimeout(5s) → FeishuGateway(10s) → ChannelRegistry(5s) → Grpc(8s) → InfraHealth(2s) → Evolution(5s)
               Then: agent.shutdown()  →  shutdown_tracing()
```

**Total max plugin shutdown: 6 plugins × 10s timeout = 60s theoretical max.**
Practical: most plugins finish in <1s; worst-case is 2-3 slow shutdowns.
→ Set `terminationGracePeriodSeconds: 75` in K8s manifest (REQUIRED).
→ **Note**: No K8s manifests exist in repo yet (Docker Compose only). This value will be set when K8s deployment is added. Track as part of cloud-native migration.

**Shutdown order rationale**:
1. SessionTimeout — stop background work generation
2. FeishuGateway — close message recording Redis
3. ChannelRegistry — disconnect OpenClaw, cancel websocket
4. Grpc — drain in-flight Go Gateway calls (5s grace)
5. InfraHealth — close probe connections (Redis, httpx)
6. Evolution — close evolution Redis
7. agent.shutdown() — DB connections, event bus

### Rollback Strategy

Import-safe feature flag (R1-C5 fix):

```python
# agents/requirement_manager/app/main.py
import importlib
from shared.config import settings

def _load_app():
    """Lazy load to prevent import-time failures from blocking both paths."""
    if settings.use_factory_app:
        mod = importlib.import_module(".main_factory", package=__package__)
    else:
        mod = importlib.import_module(".main_legacy", package=__package__)
    return mod.app

app = _load_app()
```

This ensures:
- Syntax errors in `main_factory.py` don't crash the process when `use_factory_app=False`
- Rollback = set env var `USE_FACTORY_APP=false` + restart (no redeploy needed if image has both files)

Default: `use_factory_app = False` initially, flip to `True` after parity validation.

### Parity Validation Gate (R1-H5)

Before flipping the flag, run automated parity test:

```python
# agents/requirement_manager/tests/test_factory_parity.py
import importlib
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
def legacy_app():
    return importlib.import_module("agents.requirement_manager.app.main_legacy").app

@pytest.fixture
def factory_app():
    return importlib.import_module("agents.requirement_manager.app.main_factory").app

@pytest.mark.asyncio
async def test_parity_health_ready(legacy_app, factory_app):
    """Assert new factory health response is structurally compatible with legacy."""
    async with AsyncClient(transport=ASGITransport(app=legacy_app), base_url="http://test") as lc:
        legacy_resp = await lc.get("/health/ready")
    async with AsyncClient(transport=ASGITransport(app=factory_app), base_url="http://test") as fc:
        factory_resp = await fc.get("/health/ready")
    assert legacy_resp.status_code == factory_resp.status_code
    assert set(legacy_resp.json().keys()) <= set(factory_resp.json().keys())

@pytest.mark.asyncio
async def test_parity_routes(legacy_app, factory_app):
    """Assert factory app has all routes from legacy app."""
    legacy_routes = {r.path for r in legacy_app.routes if hasattr(r, 'path')}
    factory_routes = {r.path for r in factory_app.routes if hasattr(r, 'path')}
    assert legacy_routes <= factory_routes, f"Missing routes: {legacy_routes - factory_routes}"

@pytest.mark.asyncio
async def test_parity_middleware_headers(factory_app):
    """Assert security headers are present in factory responses."""
    async with AsyncClient(transport=ASGITransport(app=factory_app), base_url="http://test") as client:
        resp = await client.get("/health")
    for header in ["X-Content-Type-Options", "X-Frame-Options", "Strict-Transport-Security"]:
        assert header in resp.headers
```

## What Gets Removed (after rollback period)

- `agents/requirement_manager/app/main_legacy.py` (renamed current main.py)
- Manual EvolvedAgent wrapping → handled by EvolutionPlugin
- Manual middleware registration → handled by factory
- Manual Prometheus setup → handled by factory
- Manual health endpoints → handled by factory + InfraHealthPlugin
- Static file serving → removed (cloud-native)
- Manual exception handler → handled by factory
- `root()` endpoint → removed with static files

## What Gets Kept

- `api_info()` endpoint → extracted to `routes.py` router
- `api_v1_redirect()` → **kept as deprecated** until Go gateway + Feishu callback audit (R1-C6)
- All API routers → passed to create_agent_app()
- Custom readiness probes → InfraHealthPlugin
- gRPC, channels, feishu, session timeout → agent-specific plugins
- `include_api_key_middleware=True` — webhooks use path exemptions, not middleware removal

## File Changes

| File | Action |
|------|--------|
| `shared/app/runtime.py` | Add `HealthCheckResult`, concurrent health aggregation, startup order change, plugin timeout |
| `shared/app/factory.py` | Add `plugins` param, CORS from settings, two-tier readiness, startup probe |
| `shared/app/plugins/__init__.py` | New — export InfraHealthPlugin |
| `shared/app/plugins/infra_health.py` | New — constructor-injected PG/Redis/Milvus/NATS probes with persistent connections |
| `agents/requirement_manager/app/plugins/__init__.py` | New — export agent-specific plugins |
| `agents/requirement_manager/app/plugins/grpc.py` | New — GrpcPlugin with injected factory |
| `agents/requirement_manager/app/plugins/channel_registry.py` | New — ChannelRegistryPlugin |
| `agents/requirement_manager/app/plugins/feishu_gateway.py` | New — FeishuGatewayPlugin with injected PM client |
| `agents/requirement_manager/app/plugins/session_timeout.py` | New — SessionTimeoutPlugin |
| `agents/requirement_manager/app/routes.py` | New — extracted `api_info()` + `api_v1_redirect()` |
| `agents/requirement_manager/app/main.py` | Rewrite — import-safe lazy feature flag switch |
| `agents/requirement_manager/app/main_factory.py` | New — ~40 lines using create_agent_app() |
| `agents/requirement_manager/app/main_legacy.py` | Renamed from current main.py |
| `shared/config.py` | Add `use_factory_app: bool = False`, ensure `cors_*` fields typed |
| `shared/app/tests/test_runtime.py` | Add HealthCheckResult tests, concurrent aggregation tests |
| `shared/app/tests/test_factory.py` | Add plugins param tests, two-tier health tests, startup probe test |
| `agents/requirement_manager/tests/test_plugins.py` | New — unit tests per plugin |
| `agents/requirement_manager/tests/test_factory_parity.py` | New — parity validation gate |
| `shared/app/tests/test_infra_health_ssrf.py` | New — SSRF validator parameterized tests |

**Note on K8s manifest**: `terminationGracePeriodSeconds: 75` is REQUIRED when K8s deployment exists. Currently Docker Compose only — tracked as cloud-native migration prerequisite.

**Note on Prometheus**: Factory `excluded_handlers` must be updated to include `/health/startup` and `/health/ready/detail`.

## Testing Strategy

1. **Unit tests per plugin** — mock dependencies, verify startup/shutdown/health_check contract
2. **HealthCheckResult tests** — verify serialization, aggregation, namespacing
3. **Factory integration test** — create_agent_app with plugins, verify readiness two-tier response
4. **Startup probe test** — verify 503 before startup, 200 after
5. **CORS parity test** — verify factory CORS headers match current behavior
6. **Parity validation gate** — side-by-side legacy vs factory comparison
7. **Feature flag test** — verify lazy import loads correct module, syntax error in one doesn't crash other
8. **Existing e2e tests** — must pass with `use_factory_app=True`
9. **Shutdown order test** — verify plugins shutdown in correct reverse order with timeouts
10. **Security regression test** — verify health detail requires auth, no connection strings in public response
11. **SSRF validator test** — parameterized: `169.254.169.254` blocked, `fd00::1` blocked, `127.0.0.1:19530` allowed, hostname passthrough, private IPs blocked
12. **Prometheus exclusion test** — verify `/health/startup` and `/health/ready/detail` excluded from instrumentation

## Rollout Monitoring

Metrics and rollback criteria during `use_factory_app=True` rollout:

| Metric | Threshold | Action |
|--------|-----------|--------|
| Startup time | > 30s (vs baseline ±2s) | Investigate, do not rollback |
| `/health/ready` 5xx rate | > 1% over 5 min | Rollback: `USE_FACTORY_APP=false` + restart |
| gRPC error rate (Go gateway) | > 0.5% over 5 min | Rollback immediately |
| Feishu webhook delivery success | < 99% over 10 min | Rollback immediately |
| Session timeout log frequency | Drops to 0 for > 2 min | Investigate; rollback if confirmed |
| Milvus search latency p99 | > 2x baseline | Investigate degradation handling |

**Rollback procedure**: Set `USE_FACTORY_APP=false` in env → restart pods → verify `/health/ready` returns 200.
