"""Tests for Sync scheduler application use cases."""

from unittest.mock import AsyncMock

import pytest

from shared.capabilities.sync.core.scheduler_use_cases import SyncSchedulerUseCase


@pytest.mark.asyncio
async def test_run_scheduled_sync_uses_scheduler_trigger_source() -> None:
    agent = AsyncMock()
    agent.trigger_sync.return_value = {"status": "success"}

    result = await SyncSchedulerUseCase(agent).run_scheduled_sync()

    assert result == {"status": "success"}
    agent.trigger_sync.assert_awaited_once_with(triggered_by="scheduler")
