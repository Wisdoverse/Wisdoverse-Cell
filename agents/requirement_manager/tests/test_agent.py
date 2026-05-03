"""
Unit tests for RequirementManagerAgent

Tests core Agent behavior:
- BaseAgent inheritance
- Event creation
- Event dispatch
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the project root is on the Python path.
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.service.agent import (
    IngestResult,
    RequirementManagerAgent,
    agent,
)
from agents.requirement_manager.service.event_handlers import dispatch_event
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes


class _HealthyDbManager:
    @asynccontextmanager
    async def session(self):
        yield AsyncMock()


class TestRequirementManagerAgentClass:
    """RequirementManagerAgent class definition tests."""

    def test_inherits_from_base_agent(self):
        """Agent inherits from BaseAgent."""
        assert isinstance(agent, BaseAgent)
        assert isinstance(agent, RequirementManagerAgent)

    def test_agent_id(self):
        """agent_id follows kebab-case."""
        assert agent.agent_id == "requirement-manager"
        assert "-" in agent.agent_id  # kebab-case
        assert "_" not in agent.agent_id  # not snake_case

    def test_agent_name(self):
        """agent_name is set."""
        assert agent.agent_name == "Requirement Manager"

    def test_published_events(self):
        """Published event types are declared."""
        assert EventTypes.REQUIREMENT_EXTRACTED in agent.published_events
        assert EventTypes.REQUIREMENT_CONFIRMED in agent.published_events
        assert EventTypes.REQUIREMENT_REJECTED in agent.published_events

    def test_subscribed_events_for_cross_agent_integration(self):
        """Subscribed events support cross-Agent integration."""
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
    """Event creation tests."""

    def test_create_event_sets_source_agent(self):
        """create_event sets source_agent automatically."""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={"requirement_id": "req_123"}
        )

        assert event.source_agent == "requirement-manager"
        assert event.event_type == EventTypes.REQUIREMENT_CONFIRMED
        assert event.payload["requirement_id"] == "req_123"

    def test_create_event_generates_event_id(self):
        """create_event generates an event_id."""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_EXTRACTED,
            payload={}
        )

        assert event.event_id is not None
        assert event.event_id.startswith("evt_")

    def test_create_event_with_trace_id(self):
        """create_event supports trace_id."""
        event = agent.create_event(
            event_type=EventTypes.REQUIREMENT_CONFIRMED,
            payload={},
            trace_id="trace_abc123"
        )

        assert event.metadata.trace_id == "trace_abc123"


class TestEventDispatch:
    """Event dispatch tests."""

    @pytest.mark.asyncio
    async def test_dispatch_unknown_event_returns_empty(self):
        """Unknown event types return an empty list."""
        event = Event.create(
            event_type="unknown.event",
            source_agent="test",
            payload={}
        )

        result = await dispatch_event(agent, event)

        assert result == []

    @pytest.mark.asyncio
    async def test_dispatch_logs_unhandled_event(self):
        """Unhandled events are logged."""
        event = Event.create(
            event_type="unhandled.event.type",
            source_agent="test",
            payload={}
        )

        with patch("agents.requirement_manager.service.event_handlers.logger") as mock_logger:
            await dispatch_event(agent, event)
            mock_logger.warning.assert_called_once()


class TestAgentLifecycle:
    """Agent lifecycle tests."""

    @pytest.mark.asyncio
    async def test_startup_initializes_resources(self):
        """startup initializes resources managed directly by the Agent."""
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
        """shutdown cleans up resources managed directly by the Agent."""
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

    @pytest.mark.asyncio
    async def test_health_check_reports_runtime_dependencies(self):
        bus = MagicMock()
        bus.is_connected = True
        test_agent = RequirementManagerAgent(
            db=_HealthyDbManager(),
            bus=bus,
            vectors=MagicMock(),
            messenger=object(),
            card_renderer=object(),
        )

        result = await test_agent.health_check()

        assert result == {
            "database": True,
            "event_bus": True,
            "messenger": True,
            "card_renderer": True,
        }


class TestIngestResult:
    """IngestResult dataclass tests."""

    def test_ingest_result_fields(self):
        """IngestResult exposes expected fields."""
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
    """Dependency injection tests."""

    def test_agent_accepts_custom_dependencies(self):
        """Agent accepts custom dependencies."""
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
        """Agent uses default dependencies when none are injected."""
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
    """Message formatting tests."""

    def test_format_single_message(self):
        """Format one message."""
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
        """Format multiple messages."""
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
        """Skip messages with empty content."""
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
        """Handle a missing sender name."""
        from datetime import UTC, datetime

        mock_msg = MagicMock()
        mock_msg.sender_name = None
        mock_msg.sent_at = datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_msg.content = "消息内容"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg])

        assert "[10:30] Unknown: 消息内容" == result

    def test_format_handles_none_sent_at(self):
        """Handle a missing sent_at value."""
        mock_msg = MagicMock()
        mock_msg.sender_name = "张三"
        mock_msg.sent_at = None
        mock_msg.content = "消息内容"

        test_agent = RequirementManagerAgent()
        result = test_agent._format_messages_for_extraction([mock_msg])

        assert "[??:??] 张三: 消息内容" == result


class TestExtractFromSession:
    """Session extraction tests."""

    @pytest.mark.asyncio
    async def test_extract_from_session_no_messages(self):
        """Return None when the session has no messages."""
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
        """Trigger extraction when the session has messages."""
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
        """Do not send a card when no requirements are extracted."""
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
    """Session extraction card sending tests."""

    @pytest.mark.asyncio
    async def test_send_card_success(self):
        """Send a card successfully."""
        mock_client = MagicMock()
        mock_client.send_card = AsyncMock()
        mock_renderer = MagicMock()
        mock_renderer.extraction_result_card.return_value = {"card": "data"}
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
            messenger=mock_client,
            card_renderer=mock_renderer,
        )

        mock_result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=2,
            questions_generated=1,
            requirement_ids=["req_1", "req_2"]
        )

        await test_agent._send_session_extraction_card(
            "chat_456",
            mock_result,
            "ses_abc123",
        )

        mock_renderer.extraction_result_card.assert_called_once()
        mock_client.send_card.assert_called_once_with(
            receive_id="chat_456",
            receive_id_type="chat_id",
            card={"card": "data"}
        )

    @pytest.mark.asyncio
    async def test_send_card_handles_error(self):
        """Card sending errors do not raise."""
        mock_client = MagicMock()
        mock_client.send_card = AsyncMock(side_effect=Exception("Connection error"))
        mock_renderer = MagicMock()
        mock_renderer.extraction_result_card.return_value = {"card": "data"}
        test_agent = RequirementManagerAgent(
            db=MagicMock(),
            bus=MagicMock(),
            vectors=MagicMock(),
            messenger=mock_client,
            card_renderer=mock_renderer,
        )

        mock_result = IngestResult(
            meeting_id="mtg_123",
            requirements_extracted=1,
            questions_generated=0,
            requirement_ids=["req_1"]
        )

        # Should not raise
        await test_agent._send_session_extraction_card("chat_456", mock_result, "ses_abc123")
