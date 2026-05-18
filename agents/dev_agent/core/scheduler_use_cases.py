"""Application use cases for Dev Agent scheduled operations."""
from __future__ import annotations

from datetime import timedelta

from .repositories import DevTaskRepositoryPort


def workflow_poll_interval(elapsed: timedelta) -> timedelta | None:
    """Return the minimum external workflow poll interval for elapsed runtime."""
    if elapsed < timedelta(minutes=10):
        return timedelta(seconds=30)
    if elapsed < timedelta(hours=2):
        return timedelta(minutes=2)
    if elapsed < timedelta(hours=6):
        return timedelta(minutes=5)
    return None


class DevSchedulerUseCase:
    """Application boundary for scheduled Dev Agent maintenance tasks."""

    def poll_interval(self, elapsed: timedelta) -> timedelta | None:
        return workflow_poll_interval(elapsed)

    async def expire_stale_pending(
        self,
        tasks: DevTaskRepositoryPort,
        *,
        hours: int = 24,
    ) -> int:
        return await tasks.expire_stale_pending(hours=hours)
