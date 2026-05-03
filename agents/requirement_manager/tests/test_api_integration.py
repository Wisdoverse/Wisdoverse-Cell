"""
Integration tests for API endpoints

测试 API 路由与 Agent 的集成：
- HTTP 请求正确委托给 Agent
- 响应格式正确
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from agents.requirement_manager.service.agent import IngestResult


@pytest.fixture
def mock_agent():
    """创建 mock Agent"""
    mock_agent_instance = MagicMock()

    # 配置 ingest mock
    mock_agent_instance.ingest_meeting = AsyncMock(return_value=IngestResult(
        meeting_id="mtg_test123",
        requirements_extracted=2,
        questions_generated=1,
        requirement_ids=["req_1", "req_2"]
    ))

    # 配置 feedback mock
    mock_agent_instance.confirm_requirement = AsyncMock()
    mock_agent_instance.reject_requirement = AsyncMock()

    # Patch get_agent to return our mock
    with patch("agents.requirement_manager.api.ingest.get_agent", return_value=mock_agent_instance), \
         patch("agents.requirement_manager.api.feedback.get_agent", return_value=mock_agent_instance):

        yield {
            "ingest": mock_agent_instance,
            "feedback": mock_agent_instance
        }


@pytest.fixture
def mock_db_session():
    """创建 mock 数据库会话"""
    with patch("agents.requirement_manager.api.ingest.get_db") as mock_get_db, \
         patch("agents.requirement_manager.api.feedback.get_db") as mock_get_db_feedback:

        mock_session = MagicMock()

        async def get_session():
            yield mock_session

        mock_get_db.return_value = get_session()
        mock_get_db_feedback.return_value = get_session()

        yield mock_session


class TestIngestAPI:
    """测试导入 API"""

    @pytest.mark.asyncio
    async def test_upload_delegates_to_agent(self, mock_agent, mock_db_session):
        """验证 upload 端点委托给 Agent"""
        from agents.requirement_manager.app.main import app

        # Mock lifespan to skip agent startup
        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                await client.post(
                    "/api/v1/ingest/upload",
                    json={
                        "content": "会议内容：讨论了新功能需求",
                        "source": "upload",
                        "title": "测试会议"
                    }
                )

        # 验证调用了 agent
        mock_agent["ingest"].ingest_meeting.assert_called_once()

        # 验证参数
        call_args = mock_agent["ingest"].ingest_meeting.call_args
        assert call_args.kwargs["content"] == "会议内容：讨论了新功能需求"
        assert call_args.kwargs["source"] == "upload"
        assert call_args.kwargs["title"] == "测试会议"


class TestFeedbackAPI:
    """测试反馈 API"""

    @pytest.mark.asyncio
    async def test_confirm_delegates_to_agent(self, mock_agent, mock_db_session):
        """验证 confirm 端点委托给 Agent"""
        # 创建 mock requirement（需要所有 RequirementOut 字段）
        from datetime import datetime

        from agents.requirement_manager.app.main import app
        mock_requirement = MagicMock()
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.description = "描述"
        mock_requirement.status = "CONFIRMED"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"
        mock_requirement.source_quote = None
        mock_requirement.source_meeting_ids = []
        mock_requirement.confirmed_by = "测试用户"
        mock_requirement.confirmed_at = datetime.now()
        mock_requirement.open_questions = []
        mock_requirement.created_at = datetime.now()
        mock_requirement.updated_at = datetime.now()

        mock_agent["feedback"].confirm_requirement = AsyncMock(return_value=mock_requirement)

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                await client.put(
                    "/api/v1/requirements/req_123/confirm",
                    json={"confirmed_by": "测试用户"}
                )

        # 验证调用了 agent
        mock_agent["feedback"].confirm_requirement.assert_called_once()

        # 验证参数
        call_args = mock_agent["feedback"].confirm_requirement.call_args
        assert call_args.kwargs["requirement_id"] == "req_123"
        assert call_args.kwargs["confirmed_by"] == "测试用户"

    @pytest.mark.asyncio
    async def test_reject_delegates_to_agent(self, mock_agent, mock_db_session):
        """验证 reject 端点委托给 Agent"""
        # 创建 mock requirement（需要所有 RequirementOut 字段）
        from datetime import datetime

        from agents.requirement_manager.app.main import app
        mock_requirement = MagicMock()
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.description = "描述"
        mock_requirement.status = "REJECTED"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"
        mock_requirement.source_quote = None
        mock_requirement.source_meeting_ids = []
        mock_requirement.confirmed_by = None
        mock_requirement.confirmed_at = None
        mock_requirement.open_questions = []
        mock_requirement.created_at = datetime.now()
        mock_requirement.updated_at = datetime.now()

        mock_agent["feedback"].reject_requirement = AsyncMock(return_value=mock_requirement)

        with patch("agents.requirement_manager.app.main.agent") as mock_main_agent:
            mock_main_agent.startup = AsyncMock()
            mock_main_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                await client.put(
                    "/api/v1/requirements/req_123/reject",
                    json={
                        "reason": "不符合产品方向",
                        "rejected_by": "产品经理"
                    }
                )

        # 验证调用了 agent
        mock_agent["feedback"].reject_requirement.assert_called_once()

        # 验证参数
        call_args = mock_agent["feedback"].reject_requirement.call_args
        assert call_args.kwargs["requirement_id"] == "req_123"
        assert call_args.kwargs["reason"] == "不符合产品方向"
        assert call_args.kwargs["rejected_by"] == "产品经理"


class TestAgentEventPublishing:
    """测试 Agent 事件发布"""

    @pytest.mark.asyncio
    async def test_confirm_publishes_event(self):
        """验证确认需求时发布事件"""
        from agents.requirement_manager.models import Requirement
        from agents.requirement_manager.service.agent import RequirementManagerAgent
        from shared.schemas.event import EventTypes

        # 创建带 mock 依赖的 Agent
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(return_value=True)
        mock_bus.connect = AsyncMock()
        mock_bus.disconnect = AsyncMock()

        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=mock_bus,
            vectors=MagicMock()
        )

        # Mock repository
        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"

        mock_session = MagicMock()

        with patch("agents.requirement_manager.service.agent.RequirementRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.confirm = AsyncMock(return_value=mock_requirement)
            MockRepo.return_value = mock_repo_instance

            await test_agent.confirm_requirement(
                requirement_id="req_123",
                confirmed_by="测试用户",
                session=mock_session
            )

        # 验证事件发布
        mock_bus.publish.assert_called_once()
        published_event = mock_bus.publish.call_args[0][0]

        assert published_event.event_type == EventTypes.REQUIREMENT_CONFIRMED
        assert published_event.source_agent == "requirement-manager"
        assert published_event.payload["requirement_id"] == "req_123"
        assert published_event.payload["confirmed_by"] == "测试用户"

    @pytest.mark.asyncio
    async def test_event_publish_failure_does_not_block(self):
        """验证事件发布失败不阻塞主流程"""
        from agents.requirement_manager.models import Requirement
        from agents.requirement_manager.service.agent import RequirementManagerAgent

        # 创建 mock 事件总线，模拟发布失败
        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock(side_effect=Exception("Redis connection failed"))
        mock_bus.connect = AsyncMock()
        mock_bus.disconnect = AsyncMock()

        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=mock_bus,
            vectors=MagicMock()
        )

        mock_requirement = MagicMock(spec=Requirement)
        mock_requirement.id = "req_123"
        mock_requirement.title = "测试需求"
        mock_requirement.priority = "HIGH"
        mock_requirement.category = "功能"

        mock_session = MagicMock()

        with patch("agents.requirement_manager.service.agent.RequirementRepository") as MockRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.confirm = AsyncMock(return_value=mock_requirement)
            MockRepo.return_value = mock_repo_instance

            # 应该不抛出异常
            result = await test_agent.confirm_requirement(
                requirement_id="req_123",
                confirmed_by="测试用户",
                session=mock_session
            )

        # 验证主流程完成
        assert result == mock_requirement
