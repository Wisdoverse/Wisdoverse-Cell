"""Verify DeliveryService broadcast pattern."""
import asyncio

import pytest

from shared.messaging.outbound.delivery_service import DeliveryService


@pytest.mark.asyncio
async def test_broadcast_one_failure_does_not_abort_others():
    svc = DeliveryService()
    call_count = 0

    async def mock_send(msg):
        nonlocal call_count
        call_count += 1
        if msg == "fail":
            raise RuntimeError("send failed")
        return {"success": True, "msg": msg}

    results = await svc.broadcast(mock_send, ["a", "fail", "b"])
    assert call_count == 3
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[2]["success"] is True


@pytest.mark.asyncio
async def test_broadcast_respects_concurrency_limit():
    svc = DeliveryService(max_concurrency=5)
    max_concurrent = 0
    current = 0

    async def mock_send(msg):
        nonlocal max_concurrent, current
        current += 1
        max_concurrent = max(max_concurrent, current)
        await asyncio.sleep(0.01)
        current -= 1
        return {"success": True}

    messages = [f"msg_{i}" for i in range(20)]
    await svc.broadcast(mock_send, messages)
    assert max_concurrent <= 5
