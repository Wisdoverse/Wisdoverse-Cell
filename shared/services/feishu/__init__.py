"""Deprecated: use shared.integrations.feishu"""
from shared.integrations.feishu import (
    FeishuAPIError,
    FeishuClient,
    FeishuPlatformAdapter,
    feishu_client,
    feishu_error_handler,
    get_feishu_client,
    handle_feishu_response,
    init_handlers,
    retryable_request,
    router,
)

__all__ = [
    "FeishuClient",
    "feishu_client",
    "get_feishu_client",
    "router",
    "FeishuPlatformAdapter",
    "FeishuAPIError",
    "feishu_error_handler",
    "handle_feishu_response",
    "retryable_request",
    "init_handlers",
]
