"""Shared test fixtures for dev_agent tests."""
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from agents.dev_agent.models.schemas import RiskLevel, SanitizedTask, TaskInput


@pytest_asyncio.fixture(autouse=True)
async def _dispose_module_engines_between_tests() -> AsyncGenerator[None, None]:
    """Dispose every reachable AsyncEngine after each test to prevent
    pytest-asyncio function-scoped loop bleed through module-level
    DatabaseManager singletons."""
    yield

    import gc

    from sqlalchemy.ext.asyncio import AsyncEngine

    for obj in gc.get_objects():
        if not isinstance(obj, AsyncEngine):
            continue
        try:
            await obj.dispose()
        except Exception:
            pass


@pytest.fixture
def sample_task_input():
    return TaskInput(
        title="Add login feature",
        description="Implement user authentication with JWT",
        estimated_hours=8,
        wp_id=123,
        related_files=["services/gateways/user_interaction/service/agent.py"],
    )


@pytest.fixture
def sample_sanitized_task():
    return SanitizedTask(
        title="Add login feature",
        description="Implement user authentication with JWT",
        estimated_hours=8,
        wp_id=123,
        related_files=["services/gateways/user_interaction/service/agent.py"],
        risk_level=RiskLevel.MEDIUM,
    )


@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_forge_client():
    client = AsyncMock()
    client.create_workflow = AsyncMock(return_value="wf-123")
    client.run_workflow = AsyncMock()
    client.get_status = AsyncMock(
        return_value={"ok": True, "workflow": {"status": "completed"}, "nodes": []}
    )
    client.close = AsyncMock()
    return client
