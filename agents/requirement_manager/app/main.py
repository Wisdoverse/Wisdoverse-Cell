"""Requirement manager agent FastAPI entry point via create_agent_app."""
from fastapi import Depends

from shared.app import AgentRuntime, create_agent_app
from shared.app.plugins.infra_health import InfraHealthPlugin
from shared.app.plugins.vector_store import VectorCollection, VectorStorePlugin
from shared.config import settings
from shared.integrations.feishu.client import get_feishu_client
from shared.integrations.feishu.router import router as feishu_router
from shared.integrations.wecom.router import router as wecom_router
from shared.middleware.internal_auth import verify_internal_key

from ..api import (
    admin_router,
    export_router,
    feedback_router,
    ingest_router,
    messages_router,
    requirements_router,
)
from ..db.vector_store import vector_store
from ..service import agent
from .plugins import (
    ChannelRegistryPlugin,
    FeishuGatewayPlugin,
    GrpcPlugin,
    SessionTimeoutPlugin,
)
from .routes import api_info_router, api_v1_redirect_router

agent.configure_messenger(get_feishu_client())


async def _on_startup(runtime: AgentRuntime) -> None:
    plugin = runtime.get_plugin("vector-store")
    if plugin is not None:
        vector_store.bind_plugin(plugin)


async def _on_shutdown(runtime: AgentRuntime) -> None:
    vector_store.unbind_plugin()


app = create_agent_app(
    agent,
    title="Requirement Manager Agent",
    description="Extracts, tracks, and manages requirements from source conversations and meeting records.",
    include_api_key_middleware=True,
    on_startup=_on_startup,
    on_shutdown=_on_shutdown,
    routers=[
        ingest_router,
        requirements_router,
        feedback_router,
        export_router,
        (admin_router, [Depends(verify_internal_key)]),
        messages_router,
        feishu_router,
        wecom_router,
        api_info_router,
        api_v1_redirect_router,
    ],
    plugins=[
        InfraHealthPlugin(
            milvus_uri=settings.milvus_uri,
            check_milvus=True,
            check_nats=settings.event_bus_backend == "nats",
            check_postgres_replica=bool(settings.database_read_url),
        ),
        VectorStorePlugin(
            collections={
                "requirements": VectorCollection(
                    description="Requirement semantic index",
                ),
            },
            required=False,
        ),
        GrpcPlugin(),
        ChannelRegistryPlugin(),
        FeishuGatewayPlugin(),
        SessionTimeoutPlugin(),
    ],
    control_plane_enabled=settings.control_plane_enabled,
    control_plane_company_id=settings.control_plane_company_id,
)
