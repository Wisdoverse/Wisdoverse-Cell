"""create_agent_app — one-line FastAPI app creation for any BaseAgent.

Eliminates all boilerplate: middleware, health checks, observability,
Prometheus, evolution wiring, CORS — all configured by default.

Usage::

    from shared.app import create_agent_app

    app = create_agent_app(
        MyAgent(agent_id="my-agent", agent_name="My Agent"),
        title="My Agent",
        routers=[(my_router, [Depends(verify_internal_key)])],
    )
"""

from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

from .runtime import AgentRuntime, RuntimePlugin

logger = get_logger("agent.factory")


def create_agent_app(
    agent: BaseAgent,
    *,
    title: str = "",
    description: str = "",
    version: str = "1.0.0",
    routers: list[Any] | None = None,
    on_startup: Callable[..., Coroutine[Any, Any, None]] | None = None,
    on_shutdown: Callable[..., Coroutine[Any, Any, None]] | None = None,
    evolution_enabled: bool = True,
    evolution_excluded: bool = False,
    control_plane_enabled: bool = False,
    control_plane_company_id: str = "cmp_projectcell",
    harden_excluded: bool = False,
    include_api_key_middleware: bool = True,
    plugins: list[RuntimePlugin] | None = None,
) -> FastAPI:
    """Create a fully configured FastAPI app for a BaseAgent.

    Args:
        agent: The BaseAgent instance.
        title: App title (defaults to agent_name).
        description: App description.
        version: API version.
        routers: List of routers or (router, dependencies) tuples.
        on_startup: Async callback after runtime.startup(). Receives runtime.
        on_shutdown: Async callback before runtime.shutdown(). Receives runtime.
        evolution_enabled: Wrap agent with EvolvedAgent.
        evolution_excluded: Skip evolution wrapping (for evolution-module itself).
        control_plane_enabled: Record agent run/audit evidence in the shared ledger.
        control_plane_company_id: Default company ID for control-plane records.
        include_api_key_middleware: Include APIKeyMiddleware (False for public APIs).

    Returns:
        Fully configured FastAPI application.
    """
    title = title or agent.agent_name
    description = description or f"Wisdoverse Cell Agent: {agent.agent_name}"

    runtime = AgentRuntime(agent)

    # Register built-in plugins
    if evolution_enabled:
        from .runtime import EvolutionPlugin

        runtime.use(EvolutionPlugin(excluded=evolution_excluded))

    if not harden_excluded:
        from .plugins.harden import HardenPlugin

        runtime.use(HardenPlugin())

    if control_plane_enabled:
        from .plugins.control_plane import ControlPlanePlugin

        runtime.use(ControlPlanePlugin(default_company_id=control_plane_company_id))

    # Register user-provided plugins
    for plugin in plugins or []:
        runtime.use(plugin)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──
        from shared.observability.tracing import (
            init_tracing,
            instrument_fastapi,
            instrument_httpx,
            shutdown_tracing,
        )
        from shared.utils.logger import setup_logging

        setup_logging(level="DEBUG" if settings.debug else "INFO")
        init_tracing(service_name=runtime.agent_id)
        instrument_fastapi(app)
        instrument_httpx()

        await runtime.startup()
        runtime.start_event_loop()

        if on_startup:
            try:
                await on_startup(runtime)
            except Exception as e:
                logger.error(
                    "on_startup_callback_failed", error=str(e), error_type=type(e).__name__
                )
                raise

        yield

        # ── Shutdown (fail-safe: each step isolated) ──
        if on_shutdown:
            try:
                await on_shutdown(runtime)
            except Exception as e:
                logger.error(
                    "on_shutdown_callback_failed", error=str(e), error_type=type(e).__name__
                )

        try:
            await runtime.shutdown()
        except Exception as e:
            logger.error("runtime_shutdown_failed", error=str(e), error_type=type(e).__name__)

        try:
            shutdown_tracing()
        except Exception as e:
            logger.error("tracing_shutdown_failed", error=str(e), error_type=type(e).__name__)

    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )
    app.state.runtime = runtime

    # ── Middleware (outermost first, each added independently) ──
    try:
        from shared.middleware import (
            AccessLogMiddleware,
            RateLimitMiddleware,
            RequestTracingMiddleware,
            SecurityHeadersMiddleware,
        )

        app.add_middleware(RequestTracingMiddleware)
        app.add_middleware(AccessLogMiddleware)
        app.add_middleware(RateLimitMiddleware)
        app.add_middleware(SecurityHeadersMiddleware)

        if include_api_key_middleware:
            from shared.middleware import APIKeyMiddleware

            app.add_middleware(APIKeyMiddleware)
    except ImportError as e:
        logger.warning("middleware_module_unavailable", error=str(e))

    # ── CORS (enterprise pattern: warn + safe default, never crash) ──
    cors_origins = settings.cors_origins_list
    is_production = settings.app_env.lower() in ("production", "prod")

    if not cors_origins:
        if is_production:
            logger.error(
                "cors_origins_not_configured",
                detail="CORS_ALLOWED_ORIGINS is empty in production — defaulting to reject all. "
                "Set CORS_ALLOWED_ORIGINS to fix.",
            )
            effective_origins: list[str] = []  # Deny all CORS in prod if not configured
        else:
            logger.warning(
                "cors_origins_not_configured", detail="Defaulting to ['*'] in non-production"
            )
            effective_origins = ["*"]
    else:
        effective_origins = cors_origins

    cors_credentials = settings.cors_allow_credentials
    if effective_origins == ["*"] and cors_credentials:
        logger.error(
            "cors_credentials_wildcard_conflict",
            detail="allow_credentials=True with allow_origins=['*'] is invalid per CORS spec. "
            "Forcing allow_credentials=False.",
        )
        cors_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=effective_origins,
        allow_methods=settings.cors_allowed_methods.split(","),
        allow_headers=settings.cors_allowed_headers.split(","),
        allow_credentials=cors_credentials,
        max_age=settings.cors_max_age,
    )

    # ── Health checks ──
    @app.get("/health", tags=["health"])
    async def liveness():
        return {"status": "alive", "agent": runtime.agent_id}

    @app.get("/health/ready", tags=["health"])
    async def readiness():
        checks = await runtime.health_check()
        has_down = any(v.status == "down" for v in checks.values())
        has_degraded = any(v.status == "degraded" for v in checks.values())
        if has_down:
            status = "not_ready"
        elif has_degraded:
            status = "degraded"
        else:
            status = "ready"
        return JSONResponse(
            status_code=200 if not has_down else 503,
            content={"status": status, "agent": runtime.agent_id},
        )

    @app.get("/health/ready/detail", tags=["health"], dependencies=[Depends(verify_internal_key)])
    async def readiness_detail():
        checks = await runtime.health_check()
        has_down = any(v.status == "down" for v in checks.values())
        has_degraded = any(v.status == "degraded" for v in checks.values())
        if has_down:
            status = "not_ready"
        elif has_degraded:
            status = "degraded"
        else:
            status = "ready"
        return JSONResponse(
            status_code=200 if not has_down else 503,
            content={
                "status": status,
                "agent": runtime.agent_id,
                "checks": {k: v.to_dict() for k, v in checks.items()},
            },
        )

    @app.get("/health/startup", tags=["health"])
    async def startup_probe():
        if runtime.is_started:
            return {"status": "started", "agent": runtime.agent_id}
        return JSONResponse(
            status_code=503,
            content={"status": "starting", "agent": runtime.agent_id},
        )

    @app.get("/status", tags=["health"], dependencies=[Depends(verify_internal_key)])
    async def status_endpoint(request: Request):
        from shared.app.plugins.status_plugin import AgentStatusPlugin, build_status

        # Find the status plugin's Redis client
        redis = None
        for p in runtime._plugins:
            if isinstance(p, AgentStatusPlugin) and p._redis:
                redis = p._redis
                break
        status = await build_status(runtime, redis, agent_id=runtime.agent_id)
        return JSONResponse(content=status)

    @app.post("/agent/request", tags=["agent"], dependencies=[Depends(verify_internal_key)])
    async def agent_request(request: Request):
        """Generic internal request boundary for deployed agent services."""
        payload = await request.json()
        trace_id = request.headers.get("X-Trace-ID")
        if isinstance(payload, dict) and trace_id and not payload.get("trace_id"):
            payload = {**payload, "trace_id": trace_id}
        result = await runtime.agent.handle_request(payload)
        return JSONResponse(content=result)

    # ── Prometheus (must register before app starts — instrument() adds middleware) ──
    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator(
            excluded_handlers=[
                "/health",
                "/health/ready",
                "/health/startup",
                "/health/ready/detail",
                "/metrics",
            ],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    except ImportError:
        logger.info("prometheus_not_available")

    # ── Routers ──
    if control_plane_enabled:
        from shared.control_plane.api import create_control_plane_router

        app.include_router(
            create_control_plane_router(),
            dependencies=[Depends(verify_internal_key)],
        )

    for item in routers or []:
        if isinstance(item, tuple):
            router, deps = item
            app.include_router(router, dependencies=deps)
        else:
            app.include_router(item)

    return app
