"""
契约测试 Fixtures
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中（必须在其他导入之前）
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.capabilities.requirements.service.agent import RequirementManagerAgent


@pytest.fixture
def mock_dependencies():
    """创建 mock 依赖"""
    return {
        "db": MagicMock(),
        "bus": MagicMock(),
        "vectors": MagicMock()
    }


@pytest.fixture
def test_agent(mock_dependencies):
    """创建测试用 Agent"""
    agent = RequirementManagerAgent(
        db=mock_dependencies["db"],
        bus=mock_dependencies["bus"],
        vectors=mock_dependencies["vectors"]
    )

    # Mock 异步方法
    mock_dependencies["bus"].publish = AsyncMock(return_value=True)
    mock_dependencies["bus"].connect = AsyncMock()
    mock_dependencies["bus"].disconnect = AsyncMock()

    return agent


@pytest.fixture
def captured_events(mock_dependencies):
    """捕获发布的事件"""
    events = []

    async def capture_publish(event):
        events.append(event)
        return True

    mock_dependencies["bus"].publish = AsyncMock(side_effect=capture_publish)

    return events
