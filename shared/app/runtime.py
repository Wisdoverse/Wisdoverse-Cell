"""AgentRuntime — production-grade lifecycle manager for BaseAgent instances.

Handles:
- Plugin-based capability extension (evolution, collaboration, etc.)
- Event loop with exponential backoff
- Health checks (liveness + readiness)
- Graceful startup/shutdown with dependency ordering

Design principles (Google SRE / Meta PE standards):
- Fail-fast on startup, fail-safe on shutdown
- All external connections are best-effort (non-fatal)
- Health check separates liveness (process alive) from readiness (can serve)
- Structured logging with agent_id context
- Open/Closed principle: extend via plugins, not modifying runtime
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

from shared.config import settings
from shared.infra.metrics import EVENT_PROCESSING_ERRORS
from shared.schemas.agent import BaseAgent
from shared.utils.logger import get_logger

logger = get_logger("agent.runtime")

_PLUGIN_STARTUP_TIMEOUT = 30


# ── Health Check Result ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class HealthCheckResult:
    """Typed health check result with criticality."""

    status: Literal["ok", "degraded", "down"]
    detail: str = ""

    @property
    def is_critical(self) -> bool:
        return self.status == "down"

    def __bool__(self) -> bool:
        return self.status != "down"

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "detail": self.detail}


# ── Plugin Interface ────────────────────────────────────────────────────────


class RuntimePlugin:
    """Base class for runtime plugins that extend agent capabilities.

    Plugins can wrap the agent (adding cross-cutting concerns like tracing),
    perform async setup/teardown, and contribute health check info.

    Usage::

        class MyPlugin(RuntimePlugin):
            name = "my-plugin"
            def wrap_agent(self, agent): return MyWrapper(agent)
            async def startup(self, runtime): ...
            async def shutdown(self, runtime): ...
    """

    name: str = "unnamed"

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        """Wrap the agent to add capabilities. Return agent unchanged to skip."""
        return agent

    async def pre_agent_startup(self, runtime: "AgentRuntime") -> None:
        """Called BEFORE agent.startup(). Configure the wrapped agent."""

    async def startup(self, runtime: "AgentRuntime") -> None:
        """Called during runtime startup, after agent wrapping."""

    async def shutdown(self, runtime: "AgentRuntime") -> None:
        """Called during runtime shutdown, before agent.shutdown()."""

    async def health_check(self) -> dict[str, "HealthCheckResult"]:
        """Contribute health check data. Return empty dict to skip."""
        return {}


# ── Built-in Plugins ────────────────────────────────────────────────────────


class EvolutionPlugin(RuntimePlugin):
    """Wraps agent with EvolvedAgent for trace collection + self-optimization."""

    name = "evolution"

    def __init__(self, *, excluded: bool = False):
        self._excluded = excluded
        self._redis_client: Any = None

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        if self._excluded:
            return agent
        try:
            from shared.evolution.config import evolution_settings

            if not evolution_settings.enabled:
                return agent

            from shared.evolution.agent_memory import AgentMemory
            from shared.evolution.canary_router import CanaryRouter
            from shared.evolution.db.database import EvolutionDatabaseManager
            from shared.evolution.evaluator import Evaluator
            from shared.evolution.evolved_agent import EvolvedAgent
            from shared.evolution.prompt_safety_scanner import PromptSafetyScanner
            from shared.evolution.self_reflector import SelfReflector
            from shared.evolution.skill_optimizer import SkillOptimizer
            from shared.infra.llm_gateway import llm_gateway as _llm

            db = EvolutionDatabaseManager()
            evaluator = Evaluator()
            reflector = SelfReflector(llm_gateway=_llm)
            scanner = PromptSafetyScanner()
            memory = AgentMemory(agent_id=agent.agent_id)
            canary = CanaryRouter(db_manager=db)
            optimizer = SkillOptimizer(
                db_manager=db,
                llm_gateway=_llm,
                reflector=reflector,
                scanner=scanner,
                evaluator=evaluator,
                memory=memory,
            )
            wrapped = EvolvedAgent(
                agent,
                kill_switch=None,
                db_manager=db,
                evaluator=evaluator,
                canary_router=canary,
                skill_optimizer=optimizer,
            )
            logger.info("plugin_evolution_enabled", agent_id=agent.agent_id)
            return wrapped
        except ImportError:
            logger.info("plugin_evolution_not_available", agent_id=agent.agent_id)
            return agent
        except Exception as e:
            logger.error(
                "plugin_evolution_init_error",
                agent_id=agent.agent_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return agent

    async def startup(self, runtime: "AgentRuntime") -> None:
        """Wire KillSwitch via Redis (best-effort)."""
        try:
            from shared.evolution.evolved_agent import EvolvedAgent

            if not isinstance(runtime.agent, EvolvedAgent):
                return

            import redis.asyncio as aioredis

            from shared.evolution.kill_switch import KillSwitch

            self._redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
            runtime.agent.set_kill_switch(KillSwitch(self._redis_client))
            logger.info("plugin_kill_switch_connected", agent_id=runtime.agent_id)
        except ImportError:
            logger.info("plugin_kill_switch_not_available", agent_id=runtime.agent_id)
        except Exception as e:
            logger.error(
                "plugin_kill_switch_failed",
                agent_id=runtime.agent_id,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def shutdown(self, runtime: "AgentRuntime") -> None:
        if self._redis_client:
            try:
                await self._redis_client.aclose()
            except Exception as e:
                logger.warning(
                    "plugin_evolution_redis_close_failed", agent_id=runtime.agent_id, error=str(e)
                )

    async def health_check(self) -> dict[str, HealthCheckResult]:
        status = "ok" if self._redis_client is not None else "down"
        detail = "" if self._redis_client is not None else "redis not connected"
        return {"redis": HealthCheckResult(status, detail)}


# ── AgentRuntime ────────────────────────────────────────────────────────────


class AgentRuntime:
    """Manages a BaseAgent's full lifecycle with plugin-based extension.

    Usage::

        runtime = AgentRuntime(MyAgent(...))
        runtime.use(EvolutionPlugin())
        runtime.use(MyCustomPlugin())
        await runtime.startup()
        runtime.start_event_loop()
        # ... app running ...
        await runtime.shutdown()

    Scheduler jobs should call ``runtime.agent`` (not the raw agent)
    to ensure all plugins (tracing, evolution, etc.) are applied::

        async def my_scheduled_job():
            await runtime.agent.handle_request({"action": "do_thing"})
    """

    def __init__(self, agent: BaseAgent):
        self._raw_agent = agent
        self._agent: BaseAgent = agent
        self._plugins: list[RuntimePlugin] = []
        self._listener_task: asyncio.Task[None] | None = None
        self._started = False

    def use(self, plugin: RuntimePlugin) -> "AgentRuntime":
        """Register a plugin. Returns self for chaining.

        Plugins are applied in registration order during startup.
        """
        self._plugins.append(plugin)
        return self

    @property
    def agent(self) -> BaseAgent:
        """The fully wrapped agent instance. Use this in scheduler jobs."""
        return self._agent

    @property
    def agent_id(self) -> str:
        return self._agent.agent_id

    @property
    def is_started(self) -> bool:
        """Whether the runtime has completed startup."""
        return self._started

    def get_plugin(self, name: str) -> RuntimePlugin | None:
        """Get a registered plugin by name. Returns None if not found."""
        for plugin in self._plugins:
            if plugin.name == name:
                return plugin
        return None

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Full startup sequence. Fail-fast: errors here are fatal.

        Four phases:
        1. Plugin wrappings (synchronous, in registration order)
        2. pre_agent_startup() per plugin (async, with timeout)
        3. agent.startup()
        4. plugin.startup() per plugin (async, with timeout)
        """
        start = time.monotonic()
        logger.info("runtime_starting", agent_id=self._raw_agent.agent_id)

        # Phase 1: Apply plugin wrappings (in order)
        agent = self._raw_agent
        for plugin in self._plugins:
            agent = plugin.wrap_agent(agent)
        self._agent = agent

        # Phase 2: pre_agent_startup per plugin (with timeout)
        for plugin in self._plugins:
            try:
                await asyncio.wait_for(
                    plugin.pre_agent_startup(self),
                    timeout=_PLUGIN_STARTUP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Plugin '{plugin.name}' pre_agent_startup timed out "
                    f"after {_PLUGIN_STARTUP_TIMEOUT}s"
                )

        # Phase 3: Agent startup
        await self._agent.startup()

        # Phase 4: Plugin startups (in order, with timeout)
        for plugin in self._plugins:
            try:
                await asyncio.wait_for(
                    plugin.startup(self),
                    timeout=_PLUGIN_STARTUP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Plugin '{plugin.name}' startup timed out after {_PLUGIN_STARTUP_TIMEOUT}s"
                )

        self._started = True
        elapsed_ms = round((time.monotonic() - start) * 1000)
        logger.info(
            "runtime_started",
            agent_id=self.agent_id,
            elapsed_ms=elapsed_ms,
            plugins=[p.name for p in self._plugins],
        )

    async def shutdown(self) -> None:
        """Full shutdown sequence. Fail-safe: log errors, continue cleanup."""
        logger.info("runtime_stopping", agent_id=self.agent_id)

        # 1. Cancel event listener
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("event_loop_exit_error", agent_id=self.agent_id, error=str(e))
            self._listener_task = None

        # 2. Plugin shutdowns (reverse order, with timeout)
        for plugin in reversed(self._plugins):
            try:
                await asyncio.wait_for(plugin.shutdown(self), timeout=10)
            except asyncio.TimeoutError:
                logger.error("plugin_shutdown_timeout", plugin=plugin.name)
            except Exception as e:
                logger.error("plugin_shutdown_error", plugin=plugin.name, error=type(e).__name__)

        # 3. Agent shutdown (fail-safe)
        try:
            await self._agent.shutdown()
        except Exception as e:
            logger.error("agent_shutdown_error", agent_id=self.agent_id, error=str(e))

        self._started = False
        logger.info("runtime_stopped", agent_id=self.agent_id)

    # ── Event Loop ──────────────────────────────────────────────────────────

    def start_event_loop(self) -> None:
        """Start background event listener. No-op if agent has no subscriptions."""
        if not self._agent.subscribed_events:
            return
        self._listener_task = asyncio.create_task(
            self._event_loop(), name=f"event_loop:{self.agent_id}"
        )

    def _get_event_bus(self):
        """Get the agent's injected event bus, or fall back to global."""
        bus = getattr(self._agent, "_event_bus", None)
        if bus is not None:
            return bus
        from shared.infra.event_bus import event_bus
        return event_bus

    async def _event_loop(self) -> None:
        """Subscribe to events with exponential backoff on crash."""
        bus = self._get_event_bus()

        backoff = 1
        max_backoff = 60
        while True:
            try:
                async for event in bus.subscribe(
                    self._agent.subscribed_events, group=self.agent_id
                ):
                    result_events = None
                    try:
                        async with asyncio.timeout(settings.event_handler_timeout_seconds):
                            result_events = await self._agent.handle_event(event)
                    except TimeoutError:
                        EVENT_PROCESSING_ERRORS.labels(
                            agent_id=self.agent_id,
                            event_type=event.event_type,
                        ).inc()
                        logger.error(
                            "event_handler_timeout",
                            agent_id=self.agent_id,
                            event_type=event.event_type,
                            event_id=event.event_id,
                            timeout_seconds=settings.event_handler_timeout_seconds,
                        )
                        if not await self._publish_to_dlq(event, "TimeoutError: handler exceeded deadline"):
                            raise  # No DLQ available (NATS) → re-raise for native redelivery
                    except Exception as handler_err:
                        EVENT_PROCESSING_ERRORS.labels(
                            agent_id=self.agent_id,
                            event_type=event.event_type,
                        ).inc()
                        logger.error(
                            "event_handler_failed",
                            agent_id=self.agent_id,
                            event_type=event.event_type,
                            event_id=event.event_id,
                            error=str(handler_err),
                        )
                        if not await self._publish_to_dlq(event, str(handler_err)):
                            raise  # No DLQ available (NATS) → re-raise for native redelivery
                    # Publish events returned by handle_event
                    if result_events:
                        for out_event in result_events:
                            try:
                                await bus.publish(out_event)
                            except Exception as pub_err:
                                logger.error(
                                    "event_publish_failed",
                                    agent_id=self.agent_id,
                                    event_type=out_event.event_type,
                                    error=str(pub_err),
                                )
                    backoff = 1
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(
                    "event_loop_crashed",
                    agent_id=self.agent_id,
                    error=str(e),
                    restart_in=backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    # ── Dead Letter Queue ───────────────────────────────────────────────────

    async def _publish_to_dlq(self, event, error: str) -> bool:
        """Best-effort publish of a failed event to the dead letter queue.

        Returns True if the DLQ was available and publish succeeded,
        False if the bus has no DLQ support (e.g. NATS — use native redelivery).
        """
        try:
            bus = self._get_event_bus()
            if not hasattr(bus, "publish_dlq"):
                return False
            await bus.publish_dlq(event, error, self.agent_id)
            return True
        except Exception as exc:
            logger.warning("dlq_publish_attempt_failed", error=str(exc))
            return False

    # ── Health ──────────────────────────────────────────────────────────────

    async def health_check(self) -> dict[str, HealthCheckResult]:
        """Readiness check. Aggregates agent + all plugin health concurrently.

        Returns namespaced keys: ``plugin.name.key`` for each plugin check.
        Timeout / exception produce ``plugin.name._timeout`` / ``plugin.name._error``.
        """
        checks: dict[str, HealthCheckResult] = {}
        checks["agent_started"] = HealthCheckResult(
            "ok" if self._started else "down",
            "" if self._started else "runtime not started",
        )

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
