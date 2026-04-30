"""Verify broadcast pattern uses return_exceptions=True and semaphore."""
import asyncio

import pytest


async def safe_broadcast(send_fn, messages, max_concurrency=10):
    """Reference implementation of safe broadcast pattern (B1 fix).

    This function will be used by DeliveryService.broadcast() in Phase 2.
    """
    sem = asyncio.Semaphore(max_concurrency)

    async def _send_limited(msg):
        async with sem:
            return await send_fn(msg)

    results = await asyncio.gather(
        *[_send_limited(msg) for msg in messages],
        return_exceptions=True,
    )
    return [
        r if not isinstance(r, BaseException) else {"success": False, "error": str(r)}
        for r in results
    ]


@pytest.mark.asyncio
async def test_broadcast_one_failure_does_not_abort_others():
    """If one send fails, other sends must still complete."""
    call_count = 0

    async def mock_send(msg):
        nonlocal call_count
        call_count += 1
        if msg == "fail":
            raise RuntimeError("send failed")
        return {"success": True, "msg": msg}

    results = await safe_broadcast(mock_send, ["a", "fail", "b"])
    assert call_count == 3  # All 3 were attempted
    assert results[0] == {"success": True, "msg": "a"}
    assert results[1]["success"] is False
    assert results[2] == {"success": True, "msg": "b"}


@pytest.mark.asyncio
async def test_broadcast_respects_concurrency_limit():
    """Semaphore must limit concurrent sends."""
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
    await safe_broadcast(mock_send, messages, max_concurrency=5)
    assert max_concurrent <= 5
