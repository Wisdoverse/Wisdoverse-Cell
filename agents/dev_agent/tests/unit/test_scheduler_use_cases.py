from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from agents.dev_agent.core.scheduler_use_cases import (
    DevSchedulerUseCase,
    workflow_poll_interval,
)


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    (
        (timedelta(minutes=5), timedelta(seconds=30)),
        (timedelta(minutes=30), timedelta(minutes=2)),
        (timedelta(hours=3), timedelta(minutes=5)),
        (timedelta(hours=6), None),
    ),
)
def test_workflow_poll_interval_policy(elapsed, expected) -> None:
    assert workflow_poll_interval(elapsed) == expected


@pytest.mark.asyncio
async def test_expire_stale_pending_delegates_to_task_repository() -> None:
    tasks = AsyncMock()
    tasks.expire_stale_pending = AsyncMock(return_value=3)

    result = await DevSchedulerUseCase().expire_stale_pending(tasks, hours=12)

    assert result == 3
    tasks.expire_stale_pending.assert_awaited_once_with(hours=12)
