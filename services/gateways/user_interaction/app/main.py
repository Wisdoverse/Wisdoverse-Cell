"""User interaction gateway FastAPI entry point."""

from fastapi import Depends

from shared.app import create_agent_app
from shared.config import settings
from shared.middleware.internal_auth import verify_internal_key
from shared.utils.logger import get_logger

from ..adapters.feishu_cards import FeishuToolCardRenderer
from ..api.bitable import router as bitable_router
from ..api.daily_progress import router as daily_progress_router
from ..api.webhook import router as webhook_router
from ..core.card_ports import configure_tool_card_renderer
from ..service.agent import agent as _raw_agent

logger = get_logger("user_interaction_gateway.app")
configure_tool_card_renderer(FeishuToolCardRenderer())

app = create_agent_app(
    _raw_agent,
    title="User Interaction Gateway",
    description="Inbound Feishu webhook and compatibility HTTP gateway for chat-agent.",
    routers=[
        webhook_router,  # No auth (webhook endpoint)
        (bitable_router, [Depends(verify_internal_key)]),
        (daily_progress_router, [Depends(verify_internal_key)]),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
    evolution_enabled=False,
)
