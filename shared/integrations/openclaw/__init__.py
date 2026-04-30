"""
OpenClaw - OpenClaw Gateway 集成服务

通过 WebSocket JSON-RPC 连接 OpenClaw Gateway，
使 Wisdoverse Cell 成为 OpenClaw 的通道插件。

使用方式:
    from shared.integrations.openclaw import OpenClawClient, OpenClawPlatformAdapter

    client = OpenClawClient(
        gateway_url="ws://127.0.0.1:18789",
        device_id="projectcell",
        auth_token="secret",
    )
    adapter = OpenClawPlatformAdapter(client)
    gateway.register_adapter(adapter)
"""

from .adapter import OpenClawChannelAdapter
from .client import OpenClawClient
from .platform_adapter import OpenClawPlatformAdapter

__all__ = [
    "OpenClawChannelAdapter",
    "OpenClawClient",
    "OpenClawPlatformAdapter",
]
