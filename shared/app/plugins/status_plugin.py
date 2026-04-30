"""AgentStatusPlugin — exposes structured runtime status via /status endpoint."""
from datetime import UTC, datetime

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.utils.logger import get_logger

logger = get_logger("plugin.agent-status")


class AgentStatusPlugin(RuntimePlugin):
    """Tracks agent uptime and contributes status data."""

    name = "agent-status"

    def __init__(self) -> None:
        self._started_at: datetime | None = None
        self._redis = None

    async def startup(self, runtime) -> None:
        self._started_at = datetime.now(UTC)
        try:
            import redis.asyncio as aioredis

            from shared.config import settings

            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception as e:
            logger.warning("status_plugin_redis_init_failed", error=str(e))

    async def shutdown(self, runtime) -> None:
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    def contribute_status(self) -> dict:
        if self._started_at is None:
            return {"uptime_seconds": 0, "started_at": None}
        elapsed = (datetime.now(UTC) - self._started_at).total_seconds()
        return {
            "uptime_seconds": int(elapsed),
            "started_at": self._started_at.isoformat(),
        }

    async def health_check(self) -> dict[str, HealthCheckResult]:
        return {}


async def build_status(runtime, redis, *, agent_id: str) -> dict:
    """Build a structured status document for the agent.

    Reads loop breaker state from Redis directly and collects
    contribute_status() from all plugins that support it.
    """
    state = "running" if runtime.is_started else "starting"

    # Loop breaker from Redis
    loop_breaker: dict = {}
    if redis is not None:
        try:
            raw = await redis.hgetall(f"loop_breaker:{agent_id}")
            if raw:
                # Handle both bytes and str keys from Redis
                loop_breaker = {
                    (k.decode() if isinstance(k, bytes) else k): (
                        v.decode() if isinstance(v, bytes) else v
                    )
                    for k, v in raw.items()
                }
        except Exception as exc:
            logger.warning(
                "status_loop_breaker_read_failed",
                agent_id=agent_id,
                error=str(exc),
            )

    # Plugin contributions
    plugins: dict = {}
    for plugin in runtime._plugins:
        if not hasattr(plugin, "contribute_status"):
            continue
        try:
            data = plugin.contribute_status()
            if data:
                plugins[plugin.name] = data
        except Exception as exc:
            logger.warning(
                "status_plugin_contribute_failed",
                plugin=plugin.name,
                error=str(exc),
            )

    return {
        "agent_id": agent_id,
        "state": state,
        "loop_breaker": loop_breaker,
        "plugins": plugins,
    }
