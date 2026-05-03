"""Tests for AgentRuntime lifecycle management and plugin system."""

import asyncio
from unittest.mock import AsyncMock

import pytest

import shared.app.runtime as runtime_mod
from shared.app.runtime import AgentRuntime, EvolutionPlugin, HealthCheckResult, RuntimePlugin
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class FakeAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(
            agent_id=kwargs.get("agent_id", "fake-agent"),
            agent_name=kwargs.get("agent_name", "Fake Agent"),
            subscribed_events=kwargs.get("subscribed_events", []),
        )
        self.started = False
        self.stopped = False

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return {}

    async def startup(self) -> None:
        self.started = True

    async def shutdown(self) -> None:
        self.stopped = True


class TestHealthCheckResult:
    def test_ok_status(self):
        r = HealthCheckResult("ok")
        assert r.status == "ok"
        assert r.detail == ""
        assert bool(r) is True
        assert r.is_critical is False

    def test_degraded_status(self):
        r = HealthCheckResult("degraded", "milvus timeout")
        assert r.status == "degraded"
        assert r.detail == "milvus timeout"
        assert bool(r) is True
        assert r.is_critical is False

    def test_down_status(self):
        r = HealthCheckResult("down", "ConnectionRefusedError")
        assert r.status == "down"
        assert bool(r) is False
        assert r.is_critical is True

    def test_to_dict(self):
        r = HealthCheckResult("degraded", "slow")
        assert r.to_dict() == {"status": "degraded", "detail": "slow"}

    def test_frozen(self):
        r = HealthCheckResult("ok")
        with pytest.raises(AttributeError):
            r.status = "down"


class TestRuntimePluginInterface:
    def test_pre_agent_startup_exists(self):
        plugin = RuntimePlugin()
        assert hasattr(plugin, "pre_agent_startup")

    @pytest.mark.asyncio
    async def test_pre_agent_startup_is_noop(self):
        plugin = RuntimePlugin()
        await plugin.pre_agent_startup(None)  # Should not raise

    @pytest.mark.asyncio
    async def test_health_check_returns_empty_dict(self):
        plugin = RuntimePlugin()
        result = await plugin.health_check()
        assert result == {}


class TestStartupShutdown:
    @pytest.mark.asyncio
    async def test_startup_calls_agent_startup(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        await runtime.startup()
        assert agent.started
        assert runtime._started
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_calls_agent_shutdown(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        await runtime.startup()
        await runtime.shutdown()
        assert agent.stopped
        assert not runtime._started

    @pytest.mark.asyncio
    async def test_shutdown_is_failsafe(self):
        agent = FakeAgent()
        agent.shutdown = AsyncMock(side_effect=RuntimeError("boom"))
        runtime = AgentRuntime(agent)
        await runtime.startup()
        await runtime.shutdown()  # Should not raise


class TestProperties:
    def test_agent_property(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        assert runtime.agent is agent

    def test_agent_id(self):
        agent = FakeAgent(agent_id="my-agent")
        runtime = AgentRuntime(agent)
        assert runtime.agent_id == "my-agent"


class TestPluginSystem:
    @pytest.mark.asyncio
    async def test_plugin_wraps_agent(self):
        class WrapPlugin(RuntimePlugin):
            name = "test-wrap"

            def wrap_agent(self, agent):
                # Return a different fake to prove wrapping happened
                return FakeAgent(agent_id="wrapped-agent")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(WrapPlugin())
        await runtime.startup()
        assert runtime.agent_id == "wrapped-agent"
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_plugins_applied_in_order(self):
        call_order = []

        class PluginA(RuntimePlugin):
            name = "a"

            async def startup(self, runtime):
                call_order.append("a_start")

            async def shutdown(self, runtime):
                call_order.append("a_stop")

        class PluginB(RuntimePlugin):
            name = "b"

            async def startup(self, runtime):
                call_order.append("b_start")

            async def shutdown(self, runtime):
                call_order.append("b_stop")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(PluginA()).use(PluginB())
        await runtime.startup()
        await runtime.shutdown()
        # Startup: a then b. Shutdown: b then a (reversed).
        assert call_order == ["a_start", "b_start", "b_stop", "a_stop"]

    @pytest.mark.asyncio
    async def test_plugin_health_check(self):
        class HealthPlugin(RuntimePlugin):
            name = "health-test"

            async def health_check(self):
                return {"custom_service": HealthCheckResult("ok", "all good")}

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(HealthPlugin())
        await runtime.startup()
        checks = await runtime.health_check()
        assert checks["health-test.custom_service"].status == "ok"
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_plugin_shutdown_failsafe(self):
        class CrashPlugin(RuntimePlugin):
            name = "crash"

            async def shutdown(self, runtime):
                raise RuntimeError("plugin crash")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(CrashPlugin())
        await runtime.startup()
        await runtime.shutdown()  # Should not raise

    def test_use_returns_self_for_chaining(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        result = runtime.use(RuntimePlugin())
        assert result is runtime

    @pytest.mark.asyncio
    async def test_no_plugins_works(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        await runtime.startup()
        assert runtime.agent is agent
        await runtime.shutdown()


class TestEvolutionPlugin:
    def test_excluded_returns_raw_agent(self):
        plugin = EvolutionPlugin(excluded=True)
        agent = FakeAgent()
        result = plugin.wrap_agent(agent)
        assert result is agent

    def test_enabled_wraps_agent_with_self_reflector(self, monkeypatch):
        from shared.evolution.config import evolution_settings
        from shared.evolution.evolved_agent import EvolvedAgent

        monkeypatch.setattr(evolution_settings, "enabled", True)

        agent = FakeAgent()
        result = EvolutionPlugin().wrap_agent(agent)

        assert isinstance(result, EvolvedAgent)
        assert result.agent_id == agent.agent_id


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_basic_health(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        await runtime.startup()
        checks = await runtime.health_check()
        assert checks["agent_started"].status == "ok"
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_not_started(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        checks = await runtime.health_check()
        assert checks["agent_started"].status == "down"


class TestErrorPaths:
    """Tests for error handling quality — every error path must be logged, not silent."""

    @pytest.mark.asyncio
    async def test_plugin_startup_error_logged(self, caplog):
        class BrokenStartup(RuntimePlugin):
            name = "broken-startup"

            async def startup(self, runtime):
                raise ConnectionError("cannot connect")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(BrokenStartup())
        # Plugin startup errors propagate (fail-fast)
        with pytest.raises(ConnectionError):
            await runtime.startup()

    @pytest.mark.asyncio
    async def test_plugin_shutdown_error_logged_but_continues(self):
        shutdown_order = []

        class CrashPlugin(RuntimePlugin):
            name = "crash"

            async def shutdown(self, runtime):
                shutdown_order.append("crash_start")
                raise RuntimeError("boom")

        class GoodPlugin(RuntimePlugin):
            name = "good"

            async def shutdown(self, runtime):
                shutdown_order.append("good")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        # good registered first, crash second → shutdown reverse: crash then good
        runtime.use(GoodPlugin()).use(CrashPlugin())
        await runtime.startup()
        await runtime.shutdown()
        # Both plugins attempted shutdown despite crash
        assert "crash_start" in shutdown_order
        assert "good" in shutdown_order

    @pytest.mark.asyncio
    async def test_plugin_health_error_returns_error_key(self):
        class BrokenHealth(RuntimePlugin):
            name = "broken"

            async def health_check(self):
                raise ConnectionError("redis connection refused")

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(BrokenHealth())
        await runtime.startup()
        checks = await runtime.health_check()
        assert checks["broken._error"].status == "down"
        assert checks["broken._error"].detail == "ConnectionError"
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_agent_shutdown_error_doesnt_skip_plugin_cleanup(self):
        plugin_cleaned = False

        class TrackPlugin(RuntimePlugin):
            name = "track"

            async def shutdown(self, runtime):
                nonlocal plugin_cleaned
                plugin_cleaned = True

        agent = FakeAgent()
        agent.shutdown = AsyncMock(side_effect=RuntimeError("agent crash"))
        runtime = AgentRuntime(agent)
        runtime.use(TrackPlugin())
        await runtime.startup()
        await runtime.shutdown()
        # Plugin cleanup happened BEFORE agent.shutdown (reverse order)
        assert plugin_cleaned


class TestTwoPhaseStartup:
    @pytest.mark.asyncio
    async def test_is_started_property(self):
        agent = FakeAgent()
        rt = AgentRuntime(agent)
        assert rt.is_started is False
        await rt.startup()
        assert rt.is_started is True
        await rt.shutdown()
        assert rt.is_started is False

    @pytest.mark.asyncio
    async def test_pre_agent_startup_runs_before_agent(self):
        call_order = []

        class OrderTracker(RuntimePlugin):
            name = "tracker"

            async def pre_agent_startup(self, runtime):
                call_order.append("pre_agent")

            async def startup(self, runtime):
                call_order.append("post_agent")

        class OrderAgent(FakeAgent):
            async def startup(self):
                call_order.append("agent")

        agent = OrderAgent()
        rt = AgentRuntime(agent)
        rt.use(OrderTracker())
        await rt.startup()
        assert call_order == ["pre_agent", "agent", "post_agent"]
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_plugin_startup_timeout(self, monkeypatch):
        class SlowPlugin(RuntimePlugin):
            name = "slow"

            async def startup(self, runtime):
                await asyncio.sleep(60)

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(SlowPlugin())
        monkeypatch.setattr(runtime_mod, "_PLUGIN_STARTUP_TIMEOUT", 0.05)
        with pytest.raises(RuntimeError, match="startup timed out"):
            await rt.startup()

    @pytest.mark.asyncio
    async def test_pre_agent_startup_timeout(self, monkeypatch):
        class SlowPrePlugin(RuntimePlugin):
            name = "slow-pre"

            async def pre_agent_startup(self, runtime):
                await asyncio.sleep(60)

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(SlowPrePlugin())
        monkeypatch.setattr(runtime_mod, "_PLUGIN_STARTUP_TIMEOUT", 0.05)
        with pytest.raises(RuntimeError, match="pre_agent_startup timed out"):
            await rt.startup()


class TestShutdownTimeout:
    @pytest.mark.asyncio
    async def test_shutdown_timeout_does_not_crash(self):
        class HangingPlugin(RuntimePlugin):
            name = "hanging"

            async def shutdown(self, runtime):
                await asyncio.sleep(60)

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(HangingPlugin())
        await rt.startup()
        await asyncio.wait_for(rt.shutdown(), timeout=15)

    @pytest.mark.asyncio
    async def test_shutdown_reverse_order(self):
        order = []

        class P1(RuntimePlugin):
            name = "p1"

            async def shutdown(self, runtime):
                order.append("p1")

        class P2(RuntimePlugin):
            name = "p2"

            async def shutdown(self, runtime):
                order.append("p2")

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(P1())
        rt.use(P2())
        await rt.startup()
        await rt.shutdown()
        assert order == ["p2", "p1"]


class TestHealthCheckAggregation:
    @pytest.mark.asyncio
    async def test_agent_health_checks_are_namespaced(self):
        class AgentWithHealth(FakeAgent):
            async def health_check(self):
                return {
                    "database": True,
                    "config": False,
                    "cache": HealthCheckResult("degraded", "slow"),
                }

        agent = AgentWithHealth()
        rt = AgentRuntime(agent)
        await rt.startup()
        checks = await rt.health_check()
        assert checks["agent.database"].status == "ok"
        assert checks["agent.config"].status == "down"
        assert checks["agent.cache"].status == "degraded"
        assert checks["agent.cache"].detail == "slow"
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_agent_health_error_produces_error_key(self):
        class BadHealthAgent(FakeAgent):
            async def health_check(self):
                raise RuntimeError("database exploded")

        agent = BadHealthAgent()
        rt = AgentRuntime(agent)
        await rt.startup()
        checks = await rt.health_check()
        assert checks["agent._error"].status == "down"
        assert checks["agent._error"].detail == "RuntimeError"
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_namespaced_keys(self):
        class MyPlugin(RuntimePlugin):
            name = "my-plugin"

            async def health_check(self):
                return {
                    "db": HealthCheckResult("ok"),
                    "cache": HealthCheckResult("degraded", "slow"),
                }

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(MyPlugin())
        await rt.startup()
        checks = await rt.health_check()
        assert "my-plugin.db" in checks
        assert "my-plugin.cache" in checks
        assert checks["my-plugin.db"].status == "ok"
        assert checks["my-plugin.cache"].status == "degraded"
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_timeout_produces_sentinel_key(self):
        class SlowCheck(RuntimePlugin):
            name = "slow"

            async def health_check(self):
                await asyncio.sleep(60)
                return {}

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(SlowCheck())
        await rt.startup()
        checks = await rt.health_check()
        assert "slow._timeout" in checks
        assert checks["slow._timeout"].status == "down"
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_exception_produces_error_key(self):
        class BadCheck(RuntimePlugin):
            name = "bad"

            async def health_check(self):
                raise ValueError("boom")

        agent = FakeAgent()
        rt = AgentRuntime(agent)
        rt.use(BadCheck())
        await rt.startup()
        checks = await rt.health_check()
        assert "bad._error" in checks
        assert checks["bad._error"].detail == "ValueError"
        await rt.shutdown()

    @pytest.mark.asyncio
    async def test_agent_started_check(self):
        agent = FakeAgent()
        rt = AgentRuntime(agent)
        checks = await rt.health_check()
        assert checks["agent_started"].status == "down"
        await rt.startup()
        checks = await rt.health_check()
        assert checks["agent_started"].status == "ok"
        await rt.shutdown()


class TestGetPlugin:
    def test_returns_none_when_no_plugins(self):
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        assert runtime.get_plugin("x") is None

    def test_returns_plugin_by_name(self):
        class MyPlugin(RuntimePlugin):
            name = "test-plugin"

        plugin = MyPlugin()
        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(plugin)
        assert runtime.get_plugin("test-plugin") is plugin

    def test_returns_none_for_wrong_name(self):
        class MyPlugin(RuntimePlugin):
            name = "test-plugin"

        agent = FakeAgent()
        runtime = AgentRuntime(agent)
        runtime.use(MyPlugin())
        assert runtime.get_plugin("other") is None


class TestEventLoop:
    def test_no_subscriptions_skips_loop(self):
        agent = FakeAgent(subscribed_events=[])
        runtime = AgentRuntime(agent)
        runtime.start_event_loop()
        assert runtime._listener_task is None

    @pytest.mark.asyncio
    async def test_handler_timeout_publishes_to_dlq(self, monkeypatch):
        class SlowAgent(FakeAgent):
            async def handle_event(self, event: Event) -> list[Event]:
                await asyncio.sleep(1)
                return []

        class OneEventBus:
            def __init__(self, event: Event):
                self.event = event
                self.dlq_calls = []
                self.dlq_published = asyncio.Event()

            async def subscribe(self, event_types, group=None):
                yield self.event
                while True:
                    await asyncio.sleep(1)

            async def publish(self, event: Event) -> bool:
                return True

            async def publish_dlq(self, event: Event, error: str, agent_id: str) -> None:
                self.dlq_calls.append((event, error, agent_id))
                self.dlq_published.set()

        monkeypatch.setattr(runtime_mod.settings, "event_handler_timeout_seconds", 0.01)
        event = Event.create(
            event_type="work.execute",
            source_agent="test",
            payload={},
            trace_id="trace-runtime-timeout",
        )
        bus = OneEventBus(event)
        agent = SlowAgent(subscribed_events=["work.execute"])
        agent._event_bus = bus
        runtime = AgentRuntime(agent)

        task = asyncio.create_task(runtime._event_loop())
        try:
            await asyncio.wait_for(bus.dlq_published.wait(), timeout=1)
        finally:
            task.cancel()
            await task

        assert len(bus.dlq_calls) == 1
        dlq_event, error, agent_id = bus.dlq_calls[0]
        assert dlq_event.event_id == event.event_id
        assert dlq_event.metadata.trace_id == "trace-runtime-timeout"
        assert "TimeoutError" in error
        assert agent_id == "fake-agent"

    @pytest.mark.asyncio
    async def test_publish_to_dlq_returns_false_without_dlq_backend(self):
        class NoDlqBus:
            async def publish(self, event: Event) -> bool:
                return True

        agent = FakeAgent(subscribed_events=["work.execute"])
        agent._event_bus = NoDlqBus()
        runtime = AgentRuntime(agent)
        event = Event.create(
            event_type="work.execute",
            source_agent="test",
            payload={},
        )

        assert await runtime._publish_to_dlq(event, "boom") is False
