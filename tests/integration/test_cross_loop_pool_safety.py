"""Sentinel test for `shared.testing.dispose_module_engines`.

Two consecutive `asyncio.run(...)` calls share the same Python process but
use distinct event loops. Without the helper, the second call against a
module-level engine pool would raise `RuntimeError: Event loop is closed`
because asyncpg connections from the first loop are still cached.

This test is the single load-bearing regression case for the four autouse
``_isolate_module_pools`` fixtures wired across the runtime conftests. If
``dispose_module_engines`` regresses (or someone deletes the fixtures
without a replacement), this test fails — which is exactly the signal we
want, because otherwise the cross-loop bug returns silently and surfaces
later as a confusing failure in an unrelated test.

Marked `requires_infra` so the public unit-test gate does not depend on
Postgres.
"""

from __future__ import annotations

import asyncio
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from shared.testing import dispose_module_engines

pytestmark = [pytest.mark.requires_infra]


def _test_database_url() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5433")
    db = os.environ.get("POSTGRES_DB", "wisdoverse-cell_test")
    user = os.environ.get("POSTGRES_USER", "test")
    password = os.environ.get("POSTGRES_PASSWORD", "test")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def test_dispose_module_engines_recovers_pool_across_event_loops() -> None:
    """Touch a pool in loop A, dispose via the helper, touch in loop B.

    Without the helper, loop B's pool checkout drives the now-dead loop A
    and raises ``RuntimeError: Event loop is closed``. With it, loop B
    starts with a fresh pool and the query succeeds.

    This is the load-bearing sentinel for the four autouse
    ``_isolate_module_pools`` fixtures wired across the runtime conftests.
    If ``dispose_module_engines`` regresses, or the fixtures are deleted
    without a replacement, this test fails.
    """
    url = _test_database_url()

    # Build the singleton engine at module scope so both loops share it.
    engine = create_async_engine(url)

    async def query() -> int:
        async with engine.begin() as conn:
            return (await conn.execute(sa.text("SELECT 1"))).scalar_one()

    async def _dispose() -> None:
        async with dispose_module_engines():
            pass

    try:
        assert asyncio.run(query()) == 1
        asyncio.run(_dispose())
        # Loop B reuses the same engine — succeeds only because the helper
        # disposed the pool between loops.
        assert asyncio.run(query()) == 1
    finally:
        asyncio.run(engine.dispose())
