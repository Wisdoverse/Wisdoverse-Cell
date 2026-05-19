"""Cross-loop SQLAlchemy pool isolation for pytest-asyncio test suites.

Every Wisdoverse-Cell runtime instantiates module-level `DatabaseManager`
singletons at import time (e.g. ``agents.<runtime>.db.database.db_manager``,
``shared.control_plane.database.control_plane_db_manager``). The asyncpg
connections those pools hand out become bound to whichever event loop first
touched them. pytest-asyncio's function-scoped loop policy gives each test a
fresh loop, so the next test's ``pool_pre_ping`` drives the now-closed loop
of the previous test and raises ``RuntimeError: Event loop is closed``.

`dispose_module_engines` walks ``gc.get_objects()`` for every reachable
``AsyncEngine`` and calls ``engine.dispose()``. Walking via gc avoids
hard-coding the singleton list — new agents or capabilities are covered the
moment their module is imported.

The proper long-term fix is per-runtime DI containers replacing the
module-level singletons; that refactor is tracked separately. Until then,
runtime test conftests should call this from an autouse fixture so each
test starts with a freshly disposed pool.
"""

from __future__ import annotations

import gc
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def dispose_module_engines() -> AsyncIterator[None]:
    """Async context manager: dispose every reachable ``AsyncEngine`` on exit.

    Usage in a conftest::

        @pytest_asyncio.fixture(autouse=True)
        async def _isolate_pools():
            async with dispose_module_engines():
                yield
    """
    try:
        yield
    finally:
        # Local import to avoid loading SQLAlchemy at module-import time —
        # not every test process needs it. Each test pays a single attribute
        # lookup cost.
        from sqlalchemy.ext.asyncio import AsyncEngine

        for obj in gc.get_objects():
            if not isinstance(obj, AsyncEngine):
                continue
            try:
                await obj.dispose()
            except Exception:
                logger.debug("engine_dispose_failed", exc_info=True)
