# shared/services/wecom/__init__.py
"""WeCom integration service."""
from .adapter import WecomChannelAdapter
from .client import WecomClient, get_wecom_client, wecom_client
from .config import WecomConfig, get_wecom_config
from .platform_adapter import WecomPlatformAdapter
from .router import init_handlers, router

__all__ = [
    "WecomChannelAdapter",
    "WecomClient",
    "WecomConfig",
    "get_wecom_client",
    "get_wecom_config",
    "init_handlers",
    # Platform adapter for unified gateway
    "WecomPlatformAdapter",
    "router",
    "wecom_client",
]
