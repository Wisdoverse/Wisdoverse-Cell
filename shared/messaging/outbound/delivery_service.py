"""DeliveryService -- single outbound exit point (B1/B5 fix).

Uses return_exceptions=True + asyncio.Semaphore for safe broadcast.
"""
import asyncio
from typing import Any, Awaitable, Callable

from shared.utils.logger import get_logger

logger = get_logger("delivery_service")


class DeliveryService:
    """Unified outbound message delivery with safe broadcast."""

    CONSUMER_GROUP = "default"

    def __init__(self, max_concurrency: int = 10) -> None:
        self._max_concurrency = max_concurrency

    async def broadcast(
        self,
        send_fn: Callable[[Any], Awaitable[dict]],
        messages: list[Any],
    ) -> list[dict]:
        """Send messages with failure isolation and concurrency limiting."""
        sem = asyncio.Semaphore(self._max_concurrency)

        async def _send_limited(msg: Any) -> dict:
            async with sem:
                return await send_fn(msg)

        results = await asyncio.gather(
            *[_send_limited(msg) for msg in messages],
            return_exceptions=True,
        )
        return [
            r if not isinstance(r, BaseException)
            else {"success": False, "error": str(r)}
            for r in results
        ]
