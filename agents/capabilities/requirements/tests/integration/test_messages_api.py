"""
Integration tests for Messages API endpoints

Tests:
- GET /api/messages/search - Search messages with filters and pagination
- GET /api/messages/session/{session_id} - Get session messages
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure project root is in Python path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from httpx import ASGITransport, AsyncClient

from agents.capabilities.requirements.models.chat_message import ChatMessage
from shared.utils.id_generator import IDPrefix, generate_id


class TestSearchMessagesAPI:
    """Test GET /api/messages/search endpoint"""

    @pytest.fixture
    def mock_messages(self):
        """Create mock ChatMessage objects for testing"""
        now = datetime.now(UTC)

        messages = []
        for i, (chat_id, sender_id, sender_name, content, hours_ago) in enumerate([
            ("oc_api_chat", "ou_alice", "Alice", "We need OAuth login feature for enterprise", 5),
            ("oc_api_chat", "ou_bob", "Bob", "Dashboard analytics should show real-time data", 4),
            ("oc_api_chat", "ou_alice", "Alice", "OAuth must support Google and Microsoft", 3),
            ("oc_other_api_chat", "ou_charlie", "Charlie", "API rate limiting needs improvement", 2),
            ("oc_api_chat", "ou_bob", "Bob", "Mobile app needs offline mode", 1),
        ]):
            msg = MagicMock(spec=ChatMessage)
            msg.id = f"msg_test_{i:03d}"
            msg.chat_id = chat_id
            msg.message_id = f"om_api_{i:03d}"
            msg.sender_id = sender_id
            msg.sender_name = sender_name
            msg.message_type = "text"
            msg.content = content
            msg.session_id = None
            msg.extracted = False
            msg.requirement_ids = None
            msg.sent_at = now - timedelta(hours=hours_ago)
            msg.created_at = now - timedelta(hours=hours_ago)
            messages.append(msg)

        return messages

    @pytest.mark.asyncio
    async def test_search_no_filters(self, mock_messages):
        """Verify search returns all messages when no filters applied"""
        from agents.capabilities.requirements.app.main import app

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(mock_messages, 5))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/search")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["messages"]) == 5
        assert data["page"] == 1
        assert data["page_size"] == 20

    @pytest.mark.asyncio
    async def test_search_with_keyword(self, mock_messages):
        """Verify search with keyword uses full-text search"""
        from agents.capabilities.requirements.app.main import app

        # Filter messages containing OAuth
        oauth_messages = [m for m in mock_messages if "OAuth" in m.content]

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(oauth_messages, 2))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/search?keyword=OAuth")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["messages"]) == 2

        # Verify repository was called with keyword
        mock_repo.search.assert_called_once()
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["keyword"] == "OAuth"

    @pytest.mark.asyncio
    async def test_search_with_chat_id_filter(self, mock_messages):
        """Verify search filters by chat_id"""
        from agents.capabilities.requirements.app.main import app

        # Filter messages by chat_id
        filtered_messages = [m for m in mock_messages if m.chat_id == "oc_api_chat"]

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(filtered_messages, 4))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/search?chat_id=oc_api_chat")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4

        # Verify repository was called with chat_id filter
        mock_repo.search.assert_called_once()
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["chat_id"] == "oc_api_chat"

    @pytest.mark.asyncio
    async def test_search_pagination(self, mock_messages):
        """Verify search pagination works correctly"""
        from agents.capabilities.requirements.app.main import app

        # First page - 2 messages
        page1_messages = mock_messages[:2]

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(page1_messages, 5))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response1 = await client.get("/api/v1/messages/search?page=1&page_size=2")

        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["total"] == 5
        assert len(data1["messages"]) == 2
        assert data1["page"] == 1
        assert data1["page_size"] == 2
        assert data1["total_pages"] == 3

        # Verify pagination params passed to repository
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["page"] == 1
        assert call_kwargs["page_size"] == 2

    @pytest.mark.asyncio
    async def test_search_with_time_range(self, mock_messages):
        """Verify search filters by time range"""
        from agents.capabilities.requirements.app.main import app

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(mock_messages[:2], 2))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/v1/messages/search"
                    "?start_time=2026-01-20T00:00:00Z"
                    "&end_time=2026-01-26T23:59:59Z"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Verify time parameters passed to repository
        mock_repo.search.assert_called_once()
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["start_time"] is not None
        assert call_kwargs["end_time"] is not None

    @pytest.mark.asyncio
    async def test_search_with_sender_id(self, mock_messages):
        """Verify search filters by sender_id"""
        from agents.capabilities.requirements.app.main import app

        # Filter messages by sender_id
        alice_messages = [m for m in mock_messages if m.sender_id == "ou_alice"]

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=(alice_messages, 2))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/search?sender_id=ou_alice")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Verify sender_id passed to repository
        call_kwargs = mock_repo.search.call_args.kwargs
        assert call_kwargs["sender_id"] == "ou_alice"


class TestGetSessionMessagesAPI:
    """Test GET /api/messages/session/{session_id} endpoint"""

    @pytest.fixture
    def mock_session_messages(self):
        """Create mock session messages"""
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        messages = []
        for i in range(3):
            msg = MagicMock(spec=ChatMessage)
            msg.id = f"msg_ses_{i:03d}"
            msg.chat_id = "oc_session_api_chat"
            msg.message_id = f"om_ses_api_{i:03d}"
            msg.sender_id = f"ou_user{i % 2 + 1:03d}"
            msg.sender_name = f"User {i % 2 + 1}"
            msg.message_type = "text"
            msg.content = f"Message {i + 1} in session"
            msg.session_id = session_id
            msg.extracted = True
            msg.requirement_ids = ["req_001", "req_002"]
            msg.sent_at = now - timedelta(minutes=10 - i * 5)
            msg.created_at = now - timedelta(minutes=10 - i * 5)
            messages.append(msg)

        return session_id, messages

    @pytest.mark.asyncio
    async def test_get_session_messages(self, mock_session_messages):
        """Verify get session messages returns all messages with metadata"""
        from agents.capabilities.requirements.app.main import app

        session_id, messages = mock_session_messages

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_by_session = AsyncMock(return_value=messages)
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/messages/session/{session_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == session_id
        assert data["chat_id"] == "oc_session_api_chat"
        assert data["message_count"] == 3
        assert len(data["messages"]) == 3

        # Verify metadata
        assert data["extracted"] is True
        assert set(data["requirement_ids"]) == {"req_001", "req_002"}
        assert data["started_at"] is not None
        assert data["ended_at"] is not None

        # Verify repository was called with session_id
        mock_repo.get_by_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_get_session_messages_not_found(self):
        """Verify 404 returned for non-existent session"""
        from agents.capabilities.requirements.app.main import app

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_by_session = AsyncMock(return_value=[])
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/session/ses_nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Session not found or has no messages"

    @pytest.mark.asyncio
    async def test_get_session_messages_not_extracted(self, mock_session_messages):
        """Verify session metadata shows extracted=False when not extracted"""
        from agents.capabilities.requirements.app.main import app

        session_id, messages = mock_session_messages
        # Mark messages as not extracted
        for msg in messages:
            msg.extracted = False
            msg.requirement_ids = None

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.get_by_session = AsyncMock(return_value=messages)
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(f"/api/v1/messages/session/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["extracted"] is False
        assert data["requirement_ids"] == []


class TestMessageResponseFormat:
    """Test message response format"""

    @pytest.mark.asyncio
    async def test_message_dict_format(self):
        """Verify message dict contains all required fields"""
        from agents.capabilities.requirements.app.main import app

        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        # Create a mock message with all fields
        mock_msg = MagicMock(spec=ChatMessage)
        mock_msg.id = "msg_format_001"
        mock_msg.chat_id = "oc_format_test"
        mock_msg.message_id = "om_format_001"
        mock_msg.sender_id = "ou_format_user"
        mock_msg.sender_name = "Format Test User"
        mock_msg.message_type = "text"
        mock_msg.content = "Test message content"
        mock_msg.session_id = session_id
        mock_msg.extracted = False
        mock_msg.requirement_ids = None
        mock_msg.sent_at = now
        mock_msg.created_at = now

        with patch("agents.capabilities.requirements.app.main.agent") as mock_agent, \
             patch("agents.capabilities.requirements.api.messages.MessageRepository") as MockRepo:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            mock_repo = MagicMock()
            mock_repo.search = AsyncMock(return_value=([mock_msg], 1))
            MockRepo.return_value = mock_repo

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/api/v1/messages/search?chat_id=oc_format_test")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 1

        msg = data["messages"][0]

        # Verify all required fields are present
        assert "id" in msg
        assert "chat_id" in msg
        assert "message_id" in msg
        assert "sender_id" in msg
        assert "sender_name" in msg
        assert "message_type" in msg
        assert "content" in msg
        assert "session_id" in msg
        assert "extracted" in msg
        assert "sent_at" in msg
        assert "created_at" in msg

        # Verify field values
        assert msg["id"] == "msg_format_001"
        assert msg["chat_id"] == "oc_format_test"
        assert msg["message_id"] == "om_format_001"
        assert msg["sender_id"] == "ou_format_user"
        assert msg["sender_name"] == "Format Test User"
        assert msg["message_type"] == "text"
        assert msg["content"] == "Test message content"
        assert msg["session_id"] == session_id
        assert msg["extracted"] is False
