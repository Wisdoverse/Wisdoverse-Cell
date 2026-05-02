"""SessionTimeoutPlugin — background session timeout checker."""

import asyncio

from shared.app.runtime import HealthCheckResult, RuntimePlugin
from shared.config import settings
from shared.integrations.feishu import get_session_manager
from shared.utils.logger import get_logger

logger = get_logger("plugin.session-timeout")


class SessionTimeoutPlugin(RuntimePlugin):
    name = "session-timeout"

    def __init__(self, *, interval: int = 10):
        self._interval = interval
        self._task = None
        self._session_manager = None

    async def startup(self, runtime) -> None:
        if not settings.feishu_message_recording_enabled:
            return
        self._session_manager = get_session_manager()
        self._task = asyncio.create_task(self._checker_loop())

    async def shutdown(self, runtime) -> None:
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def _checker_loop(self):
        while True:
            try:
                if self._session_manager:
                    await self._session_manager.check_timeouts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("session_timeout_check_error", error=type(e).__name__)
            await asyncio.sleep(self._interval)

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not settings.feishu_message_recording_enabled:
            return {}
        if self._task is None:
            return {"checker": HealthCheckResult("down", "task not created")}
        if self._task.done():
            exc = self._task.exception() if not self._task.cancelled() else None
            detail = type(exc).__name__ if exc else "task exited"
            return {"checker": HealthCheckResult("degraded", detail)}
        return {"checker": HealthCheckResult("ok")}
