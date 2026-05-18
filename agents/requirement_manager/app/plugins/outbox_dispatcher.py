"""RequirementOutboxDispatcherPlugin — background Requirement outbox retry loop."""

import asyncio

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.utils.logger import get_logger

logger = get_logger("plugin.requirement-outbox-dispatcher")


class RequirementOutboxDispatcherPlugin(RuntimePlugin):
    """Periodically retry pending Requirement integration events."""

    name = "requirement-outbox-dispatcher"

    def __init__(self, *, interval: int = 30, batch_size: int = 100):
        self._interval = interval
        self._batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._last_result: dict[str, int] | None = None
        self._last_error: str | None = None

    async def startup(self, runtime) -> None:
        self._task = asyncio.create_task(
            self._dispatcher_loop(runtime),
            name="requirement_outbox_dispatcher",
        )

    async def shutdown(self, runtime) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    async def _dispatcher_loop(self, runtime) -> None:
        while True:
            try:
                await self._dispatch_once(runtime)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._last_error = type(exc).__name__
                logger.error(
                    "requirement_outbox_dispatch_error",
                    error=type(exc).__name__,
                )
            await asyncio.sleep(self._interval)

    async def _dispatch_once(self, runtime) -> None:
        dispatcher = getattr(runtime.agent, "publish_pending_requirement_events", None)
        if dispatcher is None:
            self._last_error = "dispatcher_not_available"
            logger.warning("requirement_outbox_dispatcher_missing")
            return

        result = await dispatcher(limit=self._batch_size)
        self._last_result = result
        self._last_error = None

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if self._task is None:
            return {"dispatcher": HealthCheckResult("down", "task not created")}
        if self._task.done():
            exc = self._task.exception() if not self._task.cancelled() else None
            detail = type(exc).__name__ if exc else "task exited"
            return {"dispatcher": HealthCheckResult("degraded", detail)}
        if self._last_error:
            return {"dispatcher": HealthCheckResult("degraded", self._last_error)}
        detail = ""
        if self._last_result is not None:
            detail = (
                f"last total={self._last_result['total']} "
                f"published={self._last_result['published']} "
                f"failed={self._last_result['failed']}"
            )
        return {"dispatcher": HealthCheckResult("ok", detail)}
