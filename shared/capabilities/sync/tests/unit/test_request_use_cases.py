from unittest.mock import AsyncMock

import pytest

from shared.capabilities.sync.core.request_use_cases import SyncRequestUseCase
from shared.core import UNKNOWN_ACTION_ERROR_CODE


def _runner() -> AsyncMock:
    runner = AsyncMock()
    runner.trigger_sync = AsyncMock(return_value={"status": "full"})
    runner.trigger_openproject_sync = AsyncMock(return_value={"status": "openproject"})
    runner.trigger_feishu_bitable_sync = AsyncMock(
        return_value={"status": "feishu_bitable"}
    )
    return runner


@pytest.mark.asyncio
async def test_sync_now_action_triggers_full_sync() -> None:
    runner = _runner()

    result = await SyncRequestUseCase(sync_runner=runner, agent_id="sync-module").handle(
        {"action": "sync_now"}
    )

    assert result == {"status": "full"}
    runner.trigger_sync.assert_awaited_once_with(triggered_by="manual")


@pytest.mark.asyncio
async def test_sync_openproject_action_triggers_openproject_boundary() -> None:
    runner = _runner()

    result = await SyncRequestUseCase(sync_runner=runner, agent_id="sync-module").handle(
        {"action": "sync_openproject"}
    )

    assert result == {"status": "openproject"}
    runner.trigger_openproject_sync.assert_awaited_once_with(triggered_by="manual")


@pytest.mark.asyncio
async def test_sync_feishu_bitable_action_triggers_feishu_boundary() -> None:
    runner = _runner()

    result = await SyncRequestUseCase(sync_runner=runner, agent_id="sync-module").handle(
        {"action": "sync_feishu_bitable"}
    )

    assert result == {"status": "feishu_bitable"}
    runner.trigger_feishu_bitable_sync.assert_awaited_once_with(triggered_by="manual")


@pytest.mark.asyncio
async def test_status_action_returns_capability_status() -> None:
    result = await SyncRequestUseCase(
        sync_runner=_runner(),
        agent_id="sync-module",
    ).handle({"action": "status"})

    assert result == {
        "status": "running",
        "agent_id": "sync-module",
        "capabilities": ["openproject_sync", "feishu_bitable_sync"],
    }


@pytest.mark.asyncio
async def test_unknown_action_uses_shared_request_result_contract() -> None:
    result = await SyncRequestUseCase(
        sync_runner=_runner(),
        agent_id="sync-module",
    ).handle({"action": "unknown"})

    assert result == {
        "error": "unknown action",
        "error_code": UNKNOWN_ACTION_ERROR_CODE,
    }
