"""Tests for HardenPlugin wiring in create_agent_app()."""


from shared.app.plugins.harden import HardenPlugin
from shared.app.runtime import EvolutionPlugin
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event

# ── Concrete stub agent for testing ─────────────────────────────────────────


class _StubAgent(BaseAgent):
    """Minimal concrete BaseAgent for factory tests."""

    def __init__(self):
        super().__init__(
            agent_id="stub-agent",
            agent_name="Stub Agent",
            subscribed_events=["test.event"],
            published_events=["test.result"],
        )

    async def handle_event(self, event: Event) -> list[Event]:
        return []

    async def handle_request(self, request: dict) -> dict:
        return {"status": "ok"}


# ── Tests ───────────────────────────────────────────────────────────────────


class TestHardenPluginWiring:
    """Verify HardenPlugin is registered in create_agent_app()."""

    def test_harden_plugin_registered_by_default(self):
        """create_agent_app(agent) includes HardenPlugin in runtime._plugins."""
        from shared.app.factory import create_agent_app

        app = create_agent_app(_StubAgent())
        runtime = app.state.runtime
        plugin_types = [type(p) for p in runtime._plugins]
        assert HardenPlugin in plugin_types

    def test_harden_excluded(self):
        """create_agent_app(agent, harden_excluded=True) does NOT include HardenPlugin."""
        from shared.app.factory import create_agent_app

        app = create_agent_app(_StubAgent(), harden_excluded=True)
        runtime = app.state.runtime
        plugin_types = [type(p) for p in runtime._plugins]
        assert HardenPlugin not in plugin_types

    def test_plugin_order(self):
        """runtime._plugins order is [EvolutionPlugin, HardenPlugin, ...user plugins]."""
        from shared.app.factory import create_agent_app
        from shared.app.runtime import RuntimePlugin

        class UserPlugin(RuntimePlugin):
            name = "user-test"

        app = create_agent_app(_StubAgent(), plugins=[UserPlugin()])
        runtime = app.state.runtime
        plugin_types = [type(p) for p in runtime._plugins]
        assert plugin_types == [EvolutionPlugin, HardenPlugin, UserPlugin]
