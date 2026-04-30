"""InfraHealthPlugin — readiness probes for infrastructure dependencies."""
import ipaddress
from urllib.parse import urlparse

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.config import settings
from shared.infra.metrics import EVENT_QUEUE_LENGTH
from shared.utils.logger import get_logger

logger = get_logger("plugin.infra-health")


class InfraHealthPlugin(RuntimePlugin):
    """Readiness probes for infrastructure dependencies."""

    name = "infra-health"

    def __init__(
        self,
        *,
        db_manager=None,
        event_bus=None,
        milvus_uri: str = "",
        check_postgres: bool = True,
        check_redis: bool = True,
        check_milvus: bool = False,
        check_nats: bool = False,
        check_postgres_replica: bool = False,
    ):
        self._db_manager = db_manager
        self._event_bus = event_bus
        self._milvus_uri = milvus_uri
        self._milvus_health_url: str | None = None
        self._redis_client = None
        self._httpx_client = None
        self._checks = {
            "postgres": check_postgres,
            "redis": check_redis,
            "milvus": check_milvus,
            "nats": check_nats,
            "postgres_replica": check_postgres_replica,
        }

    async def startup(self, runtime) -> None:
        if self._db_manager is None:
            self._db_manager = getattr(runtime.agent, "_db_manager", None)
        if self._event_bus is None:
            self._event_bus = getattr(runtime.agent, "_event_bus", None)

        if self._checks["postgres"] and self._db_manager is None:
            raise RuntimeError(
                "InfraHealthPlugin: check_postgres=True but db_manager is None"
            )
        if self._checks["nats"] and self._event_bus is None:
            raise RuntimeError(
                "InfraHealthPlugin: check_nats=True but event_bus is None"
            )

        if self._checks["redis"]:
            import redis.asyncio as aioredis

            self._redis_client = aioredis.from_url(
                settings.redis_url, socket_connect_timeout=2, decode_responses=True
            )

        if self._checks["milvus"]:
            self._milvus_health_url = self._validate_milvus_url(
                self._milvus_uri or settings.milvus_uri
            )
            import httpx

            self._httpx_client = httpx.AsyncClient(
                timeout=2, follow_redirects=False
            )

    async def shutdown(self, runtime) -> None:
        if self._redis_client:
            await self._redis_client.aclose()
        if self._httpx_client:
            await self._httpx_client.aclose()

    @staticmethod
    def _validate_milvus_url(uri: str) -> str:
        parsed = urlparse(uri)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"InfraHealthPlugin: invalid milvus scheme: {parsed.scheme}"
            )

        hostname = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        if ip is not None:
            if ip.is_link_local:
                raise ValueError(
                    f"InfraHealthPlugin: link-local address blocked: {hostname}"
                )
            if ip.is_private and not (
                ip.is_loopback and parsed.port in (19530, 9091)
            ):
                raise ValueError(
                    f"InfraHealthPlugin: private address blocked: {hostname}"
                )

        health_port = 9091
        return f"{parsed.scheme}://{hostname}:{health_port}"

    async def health_check(self) -> dict[str, HealthCheckResult]:
        results: dict[str, HealthCheckResult] = {}

        if self._checks["postgres"] and self._db_manager:
            try:
                from sqlalchemy import text

                async with self._db_manager.session() as session:
                    await session.execute(text("SELECT 1"))
                results["postgres"] = HealthCheckResult("ok")
            except Exception as exc:
                results["postgres"] = HealthCheckResult("down", type(exc).__name__)

        if self._checks["redis"] and self._redis_client:
            try:
                await self._redis_client.ping()
                results["redis"] = HealthCheckResult("ok")
            except Exception as exc:
                results["redis"] = HealthCheckResult("down", type(exc).__name__)

        # Update event queue length gauge for Prometheus
        if self._event_bus and hasattr(self._event_bus, "get_all_queue_lengths"):
            try:
                lengths = await self._event_bus.get_all_queue_lengths()
                total = sum(lengths.values())
                EVENT_QUEUE_LENGTH.set(total)
            except Exception:
                pass  # Best-effort — don't fail health check

        if self._checks["milvus"] and self._httpx_client:
            try:
                resp = await self._httpx_client.get(
                    f"{self._milvus_health_url}/healthz"
                )
                resp.raise_for_status()
                results["milvus"] = HealthCheckResult("ok")
            except Exception as exc:
                results["milvus"] = HealthCheckResult(
                    "degraded", type(exc).__name__
                )

        if self._checks["nats"]:
            try:
                if (
                    hasattr(self._event_bus, "is_connected")
                    and self._event_bus.is_connected
                ):
                    results["nats"] = HealthCheckResult("ok")
                else:
                    results["nats"] = HealthCheckResult("down", "disconnected")
            except Exception as exc:
                results["nats"] = HealthCheckResult("down", type(exc).__name__)

        if self._checks["postgres_replica"] and self._db_manager:
            if not getattr(self._db_manager, "read_engine", None):
                results["postgres_replica"] = HealthCheckResult(
                    "degraded", "no read engine configured"
                )
            else:
                try:
                    from sqlalchemy import text

                    async with self._db_manager.read_session_ctx() as rsession:
                        result = await rsession.execute(
                            text("SELECT pg_is_in_recovery()")
                        )
                        if result.scalar():
                            results["postgres_replica"] = HealthCheckResult("ok")
                        else:
                            results["postgres_replica"] = HealthCheckResult(
                                "degraded", "not in recovery mode"
                            )
                except Exception as exc:
                    results["postgres_replica"] = HealthCheckResult(
                        "degraded", type(exc).__name__
                    )

        if self._db_manager and hasattr(self._db_manager, "pool_status"):
            try:
                pool = self._db_manager.pool_status()
                results["db_pool"] = HealthCheckResult("ok", str(pool))
            except Exception:
                pass

        return results
