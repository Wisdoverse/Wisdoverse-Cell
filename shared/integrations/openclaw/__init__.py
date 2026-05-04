"""
OpenClaw Gateway integration service.

Connects to OpenClaw Gateway over WebSocket JSON-RPC so Wisdoverse Cell can
act as an OpenClaw channel plugin.

Usage:
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
