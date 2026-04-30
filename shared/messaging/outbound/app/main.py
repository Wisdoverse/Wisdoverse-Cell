"""Channel Gateway Agent FastAPI application."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.config import settings
from shared.messaging.outbound.adapters._stable.openclaw import OpenClawAdapter
from shared.messaging.outbound.api.admin import router as admin_router
from shared.messaging.outbound.api.health import router as health_router
from shared.messaging.outbound.core.registry import AdapterRegistry
from shared.messaging.outbound.service.agent import get_agent
from shared.middleware.error_handler import global_exception_handler as _global_exc_handler
from shared.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup
    setup_logging(level="DEBUG" if settings.debug else "INFO")

    # Register OpenClaw adapter if enabled
    if settings.openclaw_enabled:
        AdapterRegistry.default().register(OpenClawAdapter())
        logger.info("openclaw_adapter_registered")

    agent = get_agent()
    await agent.startup()

    logger.info("channel_gateway_app_started")

    yield

    # Shutdown
    await agent.shutdown()
    logger.info("channel_gateway_app_stopped")


app = FastAPI(
    title="Channel Gateway Agent",
    description="Multi-platform messaging channel gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(health_router)
app.include_router(admin_router)


app.add_exception_handler(Exception, _global_exc_handler)
