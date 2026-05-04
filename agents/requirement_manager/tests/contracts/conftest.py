"""
Contract test fixtures.
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path before other imports.
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.requirement_manager.service.agent import RequirementManagerAgent


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies."""
    return {
        "db": MagicMock(),
        "bus": MagicMock(),
        "vectors": MagicMock()
    }


@pytest.fixture
def test_agent(mock_dependencies):
    """Create a test agent."""
    agent = RequirementManagerAgent(
        db=mock_dependencies["db"],
        bus=mock_dependencies["bus"],
        vectors=mock_dependencies["vectors"]
    )

    # Mock async methods.
    mock_dependencies["bus"].publish = AsyncMock(return_value=True)
    mock_dependencies["bus"].connect = AsyncMock()
    mock_dependencies["bus"].disconnect = AsyncMock()

    return agent


@pytest.fixture
def captured_events(mock_dependencies):
    """Capture published events."""
    events = []

    async def capture_publish(event):
        events.append(event)
        return True

    mock_dependencies["bus"].publish = AsyncMock(side_effect=capture_publish)

    return events
