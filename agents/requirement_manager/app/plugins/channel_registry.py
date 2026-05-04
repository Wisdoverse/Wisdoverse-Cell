"""ChannelRegistryPlugin — registers messaging channels."""

import asyncio

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("plugin.channel-registry")


class ChannelRegistryPlugin(RuntimePlugin):
    name = "channel-registry"

    def __init__(self):
        self._openclaw_client = None
        self._openclaw_task = None
        self._expected_channels = 0

    async def startup(self, runtime) -> None:
        if settings.feishu_enabled:
            self._expected_channels += 1
            from shared.core.channels import ChannelRegistry
            from shared.integrations.feishu.adapter import FeishuChannelAdapter
            from shared.integrations.feishu.client import get_feishu_client

            feishu_adapter = FeishuChannelAdapter(client=get_feishu_client())
            ChannelRegistry.register(feishu_adapter)

        if settings.wecom_enabled:
            self._expected_channels += 1
            from shared.core.channels import ChannelRegistry
            from shared.integrations.wecom.adapter import WecomChannelAdapter
            from shared.integrations.wecom.client import get_wecom_client

            wecom_adapter = WecomChannelAdapter(client=get_wecom_client())
            ChannelRegistry.register(wecom_adapter)

        if settings.openclaw_enabled:
            self._expected_channels += 1
            from shared.core.channels import ChannelRegistry
            from shared.integrations.openclaw.adapter import OpenClawChannelAdapter
            from shared.integrations.openclaw.client import OpenClawClient

            self._openclaw_client = OpenClawClient(
                gateway_url=settings.openclaw_gateway_url,
                device_id=settings.openclaw_device_id,
                auth_token=settings.openclaw_gateway_token.get_secret_value(),
            )
            openclaw_adapter = OpenClawChannelAdapter(client=self._openclaw_client)
            ChannelRegistry.register(openclaw_adapter)
            self._openclaw_task = asyncio.create_task(self._openclaw_client.connect())

    async def shutdown(self, runtime) -> None:
        if self._openclaw_client:
            await self._openclaw_client.disconnect()
        if self._openclaw_task and not self._openclaw_task.done():
            self._openclaw_task.cancel()
            try:
                await asyncio.wait_for(self._openclaw_task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if self._expected_channels == 0:
            return {}
        from shared.core.channels import ChannelRegistry

        registered = (
            len(ChannelRegistry.list_channels())
            if hasattr(ChannelRegistry, "list_channels")
            else 0
        )
        if registered >= self._expected_channels:
            return {"channels": HealthCheckResult("ok", f"{registered} registered")}
        return {
            "channels": HealthCheckResult(
                "degraded", f"{registered}/{self._expected_channels} registered"
            )
        }
