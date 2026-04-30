"""Deprecated: use shared.integrations.wecom"""
from shared.integrations.wecom import (
    WecomChannelAdapter,
    WecomClient,
    WecomConfig,
    WecomPlatformAdapter,
    get_wecom_client,
    get_wecom_config,
    init_handlers,
    router,
    wecom_client,
)

__all__ = [
    "WecomChannelAdapter",
    "WecomClient",
    "WecomConfig",
    "get_wecom_client",
    "get_wecom_config",
    "init_handlers",
    "WecomPlatformAdapter",
    "router",
    "wecom_client",
]
