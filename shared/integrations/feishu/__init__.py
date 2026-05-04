"""Shared Feishu platform integration primitives.

This package owns reusable Feishu client, router, cards, and platform adapter
code. Capability-specific gateway behavior lives under the owning capability.
"""

from .client import FeishuClient, feishu_client, get_feishu_client
from .errors import (
    FeishuAPIError,
    feishu_error_handler,
    handle_feishu_response,
    retryable_request,
)
from .platform_adapter import FeishuPlatformAdapter
from .router import init_handlers, router
from .webhook import FeishuWebhookClient

__all__ = [
    "FeishuClient",
    "feishu_client",
    "get_feishu_client",
    "router",
    "init_handlers",
    # Platform adapter for unified gateway
    "FeishuPlatformAdapter",
    "FeishuWebhookClient",
    # Error handling
    "FeishuAPIError",
    "feishu_error_handler",
    "handle_feishu_response",
    "retryable_request",
]
