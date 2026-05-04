"""Channel gateway FastAPI entry point via create_agent_app."""

from shared.app import RuntimePlugin, create_agent_app
from shared.config import settings
from shared.messaging.outbound.adapters._stable.openclaw import OpenClawAdapter
from shared.messaging.outbound.api.admin import router as admin_router
from shared.messaging.outbound.api.health import router as health_router
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.utils.logger import get_logger

from ..service.agent import get_agent

logger = get_logger(__name__)


class ChannelAdapterPlugin(RuntimePlugin):
    """Register channel adapters before the gateway connects them."""

    name = "channel-adapters"

    async def pre_agent_startup(self, runtime) -> None:
        registry = getattr(runtime.agent, "_adapter_registry", AdapterRegistry.default())
        if settings.openclaw_enabled and not registry.has(OpenClawAdapter.channel_id):
            registry.register(OpenClawAdapter())
            logger.info("openclaw_adapter_registered")


agent = get_agent()

app = create_agent_app(
    agent,
    title="Channel Gateway Agent",
    description="Multi-platform messaging channel gateway.",
    routers=[health_router, admin_router],
    plugins=[ChannelAdapterPlugin()],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
