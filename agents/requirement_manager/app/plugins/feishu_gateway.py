"""FeishuGatewayPlugin — initializes Feishu gateway."""

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.config import settings
from shared.utils.logger import get_logger

logger = get_logger("plugin.feishu-gateway")


class FeishuGatewayPlugin(RuntimePlugin):
    name = "feishu-gateway"

    def __init__(self, *, pm_client_factory=None):
        self._pm_client_factory = pm_client_factory
        self._redis_client = None
        self._initialized = False

    async def startup(self, runtime) -> None:
        if not settings.feishu_enabled:
            return
        if settings.feishu_message_recording_enabled:
            from redis.asyncio import Redis as AsyncRedis

            self._redis_client = AsyncRedis.from_url(
                settings.redis_url, decode_responses=False
            )

        factory = self._pm_client_factory
        if factory is None:
            from shared.infra.agent_client import PMAgentClient

            factory = PMAgentClient

        from agents.requirement_manager.integrations.feishu import (
            init_feishu_gateway,
        )

        db_manager = getattr(runtime.agent, "_db_manager", None)
        result = await init_feishu_gateway(
            agent=runtime.agent,
            db=db_manager,
            redis=self._redis_client,
            pm_client=factory(),
        )
        if not result:
            raise RuntimeError("FeishuGatewayPlugin: init_feishu_gateway failed")
        self._initialized = True

    async def shutdown(self, runtime) -> None:
        if self._redis_client:
            await self._redis_client.aclose()

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not settings.feishu_enabled:
            return {}
        return {
            "gateway": HealthCheckResult(
                "ok" if self._initialized else "down", ""
            )
        }
