"""
Unit tests for RequirementManagerAgent

测试 Agent 核心功能：
- 继承 BaseAgent
- 事件创建
- 事件处理分发
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.integrations.feishu.cards import (
    requirement as _req_cards_mod,
)
from agents.requirement_manager.service.agent import (
    IngestResult,
    RequirementManagerAgent,
    agent,
)
from agents.requirement_manager.service.event_handlers import dispatch_event
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes


class TestRequirementManagerAgentClass:
    """测试 Agent 类定义"""

    def test_inherits_from_base_agent(self):
        """验证继承自 BaseAgent"""
        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, RequirementManagerAgent)

    def test_agent_id(self):
        """验证 agent_id 符合规范（kebab-case）"""
        assert agent.agent_id == "requirement-manager"
        assert "-" in agent.agent_id  # kebab-case
        assert "_" not in agent.agent_id  # not snake_case

    def test_agent_name(self):
        """验证 agent_name"""
        assert agent.agent_name == "Requirement Manager"

    def test_published_events(self):
        """验证发布的事件类型"""
        assert EventTypes.REQUIREMENT_EXTRACTED in agent.published_events
        assert EventTypes.REQUIREMENT_CONFIRMED in agent.published_events
        assert EventTypes.REQUIREMENT_REJECTED in agent.published_events

    def test_subscribed_events_for_cross_agent_integration(self):
        """验证订阅事件用于跨 Agent 集成"""
        expected_events = [
            'project.created',
            'project.updated',
            'sprint.started',
            'sprint.completed',
            'meeting.uploaded',
            'coordinator.dispatch',
        ]
        assert agent.subscribed_events == expected_events


class TestEventCreation:
    """测试事件创建"""

    def test_create_event_sets_source_agent(self):
        """验证 create_event 自动设置 source_agent"""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={"requirement_id": "req_123"}
        )

        assert event.source_agent == "requirement-manager"
        assert event.event_type == EventTypes.REQUIREMENT_CONFIRMED
        assert event.payload["requirement_id"] == "req_123"

    def test_create_event_generates_event_id(self):
        """验证 create_event 生成 event_id"""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_EXTRACTED,
            payload={}
        )

        assert event.event_id is not None
        assert event.event_id.startswith("evt_")

    def test_create_event_with_trace_id(self):
        """验证 create_event 支持 trace_id"""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={},
            trace_id="trace_abc123"
        )

        assert event.metadata.trace_id == "trace_abc123"


class TestEventDispatch:
    """测试事件分发"""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_event_returns_empty(self):
        """验证未知事件类型返回空列表"""
        event = Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={}
        )

        result = await dispatch_event(agent, event)

        assert result == []

    @pytest.mark.asyncio
    async def test_dispatch_logs_unhandled_event(self):
        """验证未处理的事件会记录日志"""
        event = Event.create(
            event_type="unhandled.event.type",
            source_agent="test",
            payload={}
        )

        with patch("agents.requirement_manager.service.event_handlers.logger") as mock_logger:
            await dispatch_event(agent, event)
            mock_logger.warning.assert_called_once()


class TestAgentLifecycle:
    """测试 Agent 生命周期"""

    @pytest.mark.asyncio
    async def test_startup_initializes_resources(self):
        """验证 startup 初始化资源（vector store lifecycle managed by plugin）"""
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock()
        )
        test_agent._db_manager.create_tables = AsyncMock()
        test_agent._event_bus.connect = AsyncMock()
        test_agent._vector_store.initialize = AsyncMock()
        test_agent._vector_store.close = AsyncMock()

        await test_agent.startup()

        test_agent._db_manager.create_tables.assert_called_once()
        test_agent._event_bus.connect.assert_called_once()
        # Vector store lifecycle is now managed by VectorStorePlugin,
        # so initialize() is no longer called during agent startup.
        test_agent._vector_store.initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_cleans_up_resources(self):
        """验证 shutdown 清理资源（vector store lifecycle managed by plugin）"""
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock()
        )
        test_agent._db_manager.close = AsyncMock()
        test_agent._event_bus.disconnect = AsyncMock()
        test_agent._vector_store.close = AsyncMock()

        await test_agent.shutdown()

        test_agent._db_manager.close.assert_called_once()
        test_agent._event_bus.disconnect.assert_called_once()
        # Vector store lifecycle is now managed by VectorStorePlugin,
        # so close() is no longer called during agent shutdown.
        test_agent._vector_store.close.assert_not_called()


class TestIngestResult:
    """测试 IngestResult 数据类"""

    def test_ingest_result_fields(self):
        """验证 IngestResult 字段"""
        result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=3,
            questions_generated=2,
            requirement_ids=["req_1", "req_2", "req_3"]
        )

        assert result.meeting_id == "mtg_123"
        assert result.requirements_extracted == 3
        assert result.questions_generated == 2
        assert len(result.requirement_ids) == 3


class TestAgentDependencyInjection:
    """测试依赖注入"""

    def test_agent_accepts_custom_dependencies(self):
        """验证 Agent 支持自定义依赖"""
        mock_db = MagicMock()
        mock_bus = MagicMock()
        mock_vectors = MagicMock()

        test_agent = RequirementManagerAgent(
            db=mock_db,
            bus=mock_bus,
            vectors=mock_vectors
        )

        assert test_agent._db_manager is mock_db
        assert test_agent._event_bus is mock_bus
        assert test_agent._vector_store is mock_vectors

    def test_agent_uses_defaults_when_no_injection(self):
        """验证 Agent 使用默认依赖"""
        from agents.requirement_manager.db.database import db_manager
        from agents.requirement_manager.db.vector_store import vector_store
        from shared.infra.event_bus import event_bus as default_event_bus

        test_agent = RequirementManagerAgent()

        assert test_agent._db_manager is db_manager
        assert test_agent._event_bus is default_event_bus
        assert test_agent._vector_store is vector_store


class TestHandleRequest:
    """Test the standard internal request boundary."""

    @pytest.mark.asyncio
    async def test_standard_describe_action(self):
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
        )

        result = await test_agent.handle_request({"action": "describe"})

        assert result["agent_id"] == "requirement-manager"
        assert result["agent_name"] == "Requirement Manager"

    @pytest.mark.asyncio
    async def test_ingest_action_calls_ingest_meeting(self):
        from contextlib import asynccontextmanager

        mock_db = MagicMock()
        mock_session = MagicMock()

        @asynccontextmanager
        async def session():
            yield mock_session

        mock_db.session = session
        test_agent = RequirementManagerAgent(
            db=mock_db,
            bus=MagicMock(),
            vectors=MagicMock(),
        )
        ingest_result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=2,
            questions_generated=1,
            requirement_ids=["req_1", "req_2"],
        )

        with patch.object(
            test_agent,
            "ingest_meeting",
            new_callable=AsyncMock,
        ) as mock_ingest:
            mock_ingest.return_value = ingest_result

            result = await test_agent.handle_request(
                {
                    "action": "ingest",
                    "content": "We need a login flow.",
                    "source": "control_plane",
                    "title": "Planning",
                    "meeting_date": "2026-05-03T10:30:00Z",
                    "participants": ["Alice", "Bob"],
                    "context": "Sprint planning",
                    "source_id": "meeting_123",
                }
            )

        assert result == {
            "status": "ok",
            "meeting_id": "mtg_123",
            "requirements_extracted": 2,
            "questions_generated": 1,
            "requirement_ids": ["req_1", "req_2"],
        }
        mock_ingest.assert_awaited_once()
        kwargs = mock_ingest.await_args.kwargs
        assert kwargs["content"] == "We need a login flow."
        assert kwargs["source"] == "control_plane"
        assert kwargs["session"] is mock_session
        assert kwargs["title"] == "Planning"
        assert kwargs["meeting_date"].isoformat() == "2026-05-03T10:30:00+00:00"
        assert kwargs["participants"] == ["Alice", "Bob"]
        assert kwargs["context"] == "Sprint planning"
        assert kwargs["source_id"] == "meeting_123"

    @pytest.mark.asyncio
    async def test_ingest_action_requires_content(self):
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
        )

        result = await test_agent.handle_request({"action": "ingest"})

        assert result == {"status": "error", "error": "content_required"}

    @pytest.mark.asyncio
    async def test_ingest_action_rejects_invalid_meeting_date(self):
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
        )

        result = await test_agent.handle_request(
            {
                "action": "ingest",
                "content": "A real note",
                "meeting_date": "not-a-date",
            }
        )

        assert result == {
            "status": "error",
            "error": "meeting_date_must_be_iso_datetime",
        }


class TestFormatMessagesForExtraction:
    """测试消息格式化方法"""

    def test_format_single_message(self):
        """验证单条消息格式化"""
        from datetime import UTC, datetime

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.sender_name = "张三"
        mock_msg.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg.content = "这是一条测试消息"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg])

        assert "[10:30] 张三: 这是一条测试消息" == result

    def test_format_multiple_messages(self):
        """验证多条消息格式化"""
        from datetime import UTC, datetime

        mock_msg1 = MagicMock()
        mock_msg1.sender_name = "张三"
        mock_msg1.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg1.content = "第一条消息"

        mock_msg2 = MagicMock()
        mock_msg2.sender_name = "李四"
        mock_msg2.sent_at = datetime(2026, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_msg2.content = "第二条消息"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg1, mock_msg2])

        lines = result.split("\n")
        assert len(lines) == 2
        assert "[10:30] 张三: 第一条消息" == lines[0]
        assert "[10:31] 李四: 第二条消息" == lines[1]

    def test_format_skips_empty_content(self):
        """验证跳过空内容消息"""
        from datetime import UTC, datetime

        mock_msg1 = MagicMock()
        mock_msg1.sender_name = "张三"
        mock_msg1.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg1.content = "有内容"

        mock_msg2 = MagicMock()
        mock_msg2.sender_name = "李四"
        mock_msg2.sent_at = datetime(2026, 1, 15, 10, 31, 0, tzinfo=UTC)
        mock_msg2.content = "   "  # Empty whitespace

        mock_msg3 = MagicMock()
        mock_msg3.sender_name = "王五"
        mock_msg3.sent_at = datetime(2026, 1, 15, 10, 32, 0, tzinfo=UTC)
        mock_msg3.content = ""  # Empty string

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg1, mock_msg2, mock_msg3])

        # Only first message should be included
        assert result == "[10:30] 张三: 有内容"

    def test_format_handles_none_sender_name(self):
        """验证处理空发送者姓名"""
        from datetime import UTC, datetime

        mock_msg = MagicMock()
        mock_msg.sender_name = None
        mock_msg.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg.content = "消息内容"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg])

        assert "[10:30] Unknown: 消息内容" == result

    def test_format_handles_none_sent_at(self):
        """验证处理空发送时间"""
        mock_msg = MagicMock()
        mock_msg.sender_name = "张三"
        mock_msg.sent_at = None
        mock_msg.content = "消息内容"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg])

        assert "[??:??] 张三: 消息内容" == result


class TestExtractFromSession:
    """测试会话提取方法"""

    @pytest.mark.asyncio
    async def test_extract_from_session_no_messages(self):
        """验证无消息时返回 None"""
        from contextlib import asynccontextmanager

        mock_db = MagicMock()

        # Create async context manager for session
        @asynccontextmanager
        async def mock_session():
            mock_db_session = MagicMock()
            yield mock_db_session

        mock_db.session = mock_session

        test_agent = RequirementManagerAgent(db=mock_db)

        # Mock MessageRepository
        with patch("agents.requirement_manager.service.agent.MessageRepository") as MockMsgRepo:
            mock_repo_instance = MagicMock()
            mock_repo_instance.get_by_session = AsyncMock(return_value=[])
            MockMsgRepo.return_value = mock_repo_instance

            result = await test_agent.extract_from_session("ses_test123")

            assert result is None
            mock_repo_instance.get_by_session.assert_called_once_with("ses_test123")

    @pytest.mark.asyncio
    async def test_extract_from_session_with_messages(self):
        """验证有消息时触发提取"""
        from contextlib import asynccontextmanager
        from datetime import UTC, datetime

        mock_db = MagicMock()
        mock_db_session = MagicMock()
        mock_db_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_session():
            yield mock_db_session

        mock_db.session = mock_session

        test_agent = RequirementManagerAgent(db=mock_db)

        # Create mock messages
        mock_msg = MagicMock()
        mock_msg.id = "msg_123"
        mock_msg.chat_id = "chat_456"
        mock_msg.sender_name = "张三"
        mock_msg.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg.content = "我们需要一个登录功能"

        mock_result = IngestResult(
            meeting_id="mtg_789",
            requirements_extracted=1,
            questions_generated=0,
            requirement_ids=["req_001"]
        )

        with (
            patch("agents.requirement_manager.service.agent.MessageRepository") as MockMsgRepo,
            patch("agents.requirement_manager.service.agent.RequirementRepository") as MockReqRepo,
            patch.object(test_agent, "ingest_meeting", new_callable=AsyncMock) as mock_ingest,
            patch.object(
                test_agent, "_send_session_extraction_card", new_callable=AsyncMock
            ) as mock_send_card,
        ):

            mock_msg_repo = MagicMock()
            mock_msg_repo.get_by_session = AsyncMock(return_value=[mock_msg])
            mock_msg_repo.mark_extracted = AsyncMock()
            MockMsgRepo.return_value = mock_msg_repo

            mock_req_repo = MagicMock()
            mock_req_repo.get_by_id = AsyncMock(return_value=None)
            MockReqRepo.return_value = mock_req_repo

            mock_ingest.return_value = mock_result

            result = await test_agent.extract_from_session("ses_test123")

            assert result is not None
            assert result.requirements_extracted == 1
            mock_ingest.assert_called_once()
            mock_msg_repo.mark_extracted.assert_called_once_with("ses_test123", ["req_001"])
            mock_send_card.assert_called_once_with("chat_456", mock_result, "ses_test123")

    @pytest.mark.asyncio
    async def test_extract_from_session_no_requirements_extracted(self):
        """验证无需求提取时不发送卡片"""
        from contextlib import asynccontextmanager
        from datetime import UTC, datetime

        mock_db = MagicMock()

        @asynccontextmanager
        async def mock_session():
            mock_db_session = MagicMock()
            yield mock_db_session

        mock_db.session = mock_session

        test_agent = RequirementManagerAgent(db=mock_db)

        # Create mock message
        mock_msg = MagicMock()
        mock_msg.id = "msg_123"
        mock_msg.chat_id = "chat_456"
        mock_msg.sender_name = "张三"
        mock_msg.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg.content = "今天天气不错"  # No requirement content

        mock_result = IngestResult(
            meeting_id="mtg_789",
            requirements_extracted=0,
            questions_generated=0,
            requirement_ids=[]
        )

        with (
            patch("agents.requirement_manager.service.agent.MessageRepository") as MockMsgRepo,
            patch("agents.requirement_manager.service.agent.RequirementRepository"),
            patch.object(test_agent, "ingest_meeting", new_callable=AsyncMock) as mock_ingest,
            patch.object(
                test_agent, "_send_session_extraction_card", new_callable=AsyncMock
            ) as mock_send_card,
        ):

            mock_msg_repo = MagicMock()
            mock_msg_repo.get_by_session = AsyncMock(return_value=[mock_msg])
            MockMsgRepo.return_value = mock_msg_repo

            mock_ingest.return_value = mock_result

            result = await test_agent.extract_from_session("ses_test123")

            assert result is not None
            assert result.requirements_extracted == 0
            # Card should not be sent when no requirements extracted
            mock_send_card.assert_not_called()


class TestSendSessionExtractionCard:
    """测试会话提取卡片发送"""

    @pytest.mark.asyncio
    async def test_send_card_success(self):
        """验证成功发送卡片"""
        mock_client = MagicMock()
        mock_client.send_card = AsyncMock()
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
            messenger=mock_client,
        )

        mock_result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=2,
            questions_generated=1,
            requirement_ids=["req_1", "req_2"]
        )

        with patch.object(_req_cards_mod, "build_requirement_extracted_card") as mock_build:
            mock_build.return_value = {"card": "data"}

            await test_agent._send_session_extraction_card("chat_456", mock_result, "ses_abc123")

            mock_build.assert_called_once()
            mock_client.send_card.assert_called_once_with(
                receive_id="chat_456",
                receive_id_type="chat_id",
                card={"card": "data"}
            )

    @pytest.mark.asyncio
    async def test_send_card_handles_error(self):
        """验证卡片发送失败时不抛出异常"""
        mock_client = MagicMock()
        mock_client.send_card = AsyncMock(side_effect=Exception("Connection error"))
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
            messenger=mock_client,
        )

        mock_result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=1,
            questions_generated=0,
            requirement_ids=["req_1"]
        )

        # Should not raise
        await test_agent._send_session_extraction_card("chat_456", mock_result, "ses_abc123")
