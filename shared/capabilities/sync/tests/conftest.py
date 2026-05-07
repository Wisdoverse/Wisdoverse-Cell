"""
Shared Test Fixtures - sync_module

Mock fixtures shared across unit and integration tests.
DB fixtures are in unit/conftest.py (mock) and integration/conftest.py (real).
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest


@pytest.fixture
def mock_event_bus():
    """Mock EventBus."""
    bus = MagicMock()
    bus.publish = AsyncMock(return_value=True)
    bus.subscribe = AsyncMock()
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    type(bus).is_connected = PropertyMock(return_value=True)
    return bus


@pytest.fixture
def mock_bitable():
    """Mock Feishu BitableService."""
    bitable = AsyncMock()
    bitable.list_all_records = AsyncMock(return_value=[])
    bitable.create_record = AsyncMock(return_value="rec_mock_001")
    bitable.update_record = AsyncMock()
    return bitable


@pytest.fixture
def mock_op_client():
    """Mock OpenProject client."""
    client = AsyncMock()
    client.get_work_packages = AsyncMock(return_value=[])
    client.update_work_package = AsyncMock()
    return client
