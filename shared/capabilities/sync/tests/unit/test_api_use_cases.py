"""Tests for Sync API application use cases."""

from unittest.mock import AsyncMock

import pytest

from shared.capabilities.sync.core.api_use_cases import SyncApiUseCase


@pytest.mark.asyncio
async def test_trigger_sync_normalizes_total_processed() -> None:
    agent = AsyncMock()
    agent.trigger_sync.return_value = {
        "status": "completed",
        "processed": 5,
        "errors": [],
    }

    result = await SyncApiUseCase(agent).trigger_sync()

    assert result == {
        "status": "completed",
        "total_processed": 5,
        "errors": [],
        "error": None,
    }
    agent.trigger_sync.assert_awaited_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_trigger_openproject_sync_preserves_total_processed() -> None:
    agent = AsyncMock()
    agent.trigger_openproject_sync.return_value = {
        "status": "success",
        "total_processed": 2,
        "errors": [],
    }

    result = await SyncApiUseCase(agent).trigger_openproject_sync()

    assert result["total_processed"] == 2
    agent.trigger_openproject_sync.assert_awaited_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_trigger_feishu_bitable_sync_preserves_failure_payload() -> None:
    agent = AsyncMock()
    agent.trigger_feishu_bitable_sync.return_value = {
        "status": "failed",
        "processed": 1,
        "errors": ["bad record"],
        "error": "sync failed",
    }

    result = await SyncApiUseCase(agent).trigger_feishu_bitable_sync()

    assert result == {
        "status": "failed",
        "total_processed": 1,
        "errors": ["bad record"],
        "error": "sync failed",
    }
    agent.trigger_feishu_bitable_sync.assert_awaited_once_with(triggered_by="api")


@pytest.mark.asyncio
async def test_get_status_forwards_status_action() -> None:
    agent = AsyncMock()
    agent.handle_request.return_value = {
        "status": "ok",
        "agent_id": "sync-module-test",
        "capabilities": ["openproject", "feishu-bitable"],
    }

    result = await SyncApiUseCase(agent).get_status()

    assert result["agent_id"] == "sync-module-test"
    agent.handle_request.assert_awaited_once_with({"action": "status"})
