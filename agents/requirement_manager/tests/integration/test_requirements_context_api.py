"""
Integration tests for GET /api/requirements/{requirement_id}/context endpoint

Tests:
- Get context for requirement with messages
- Get context for requirement without messages
- 404 for non-existent requirement
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

from agents.requirement_manager.core.requirement_context_queries import (
    RequirementContextQueryService,
)
from agents.requirement_manager.models.chat_message import ChatMessage
from agents.requirement_manager.models.requirement import Requirement
from shared.core.ids import IDPrefix, generate_id


async def _get_with_context_repositories(
    app,
    requirement_repository,
    message_repository,
    path: str,
):
    from agents.requirement_manager.api.dependencies import (
        get_requirement_context_query_service,
    )

    app.dependency_overrides[get_requirement_context_query_service] = (
        lambda: RequirementContextQueryService(
            requirement_repository=requirement_repository,
            message_repository=message_repository,
        )
    )
    try:
        with patch("agents.requirement_manager.app.main.agent") as mock_agent:
            mock_agent.startup = AsyncMock()
            mock_agent.shutdown = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                return await client.get(path)
    finally:
        app.dependency_overrides.pop(get_requirement_context_query_service, None)


class TestGetRequirementContextAPI:
    """Test GET /api/requirements/{requirement_id}/context endpoint"""

    @pytest.fixture
    def mock_requirement_with_messages(self):
        """Create a mock requirement with context message IDs"""
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        requirement = MagicMock(spec=Requirement)
        requirement.id = "req_test_001"
        requirement.title = "Add OAuth login feature"
        requirement.description = "Implement OAuth 2.0 login with Google and Microsoft"
        requirement.status = "pending"
        requirement.priority = "high"
        requirement.category = "Feature"
        requirement.source_quote = "We need OAuth support for enterprise customers"
        requirement.confirmed_by = None
        requirement.confirmed_at = None
        requirement.created_at = now
        requirement.context_message_ids = ["msg_001", "msg_002", "msg_003"]
        requirement.open_questions = []

        messages = []
        for i, (sender, content, minutes_ago) in enumerate([
            ("Alice", "We need OAuth login feature for enterprise", 10),
            ("Bob", "Yes, we should support Google and Microsoft", 8),
            ("Alice", "That's the priority for Q1", 5),
        ]):
            msg = MagicMock(spec=ChatMessage)
            msg.id = f"msg_{i + 1:03d}"
            msg.sender_name = sender
            msg.content = content
            msg.message_type = "text"
            msg.sent_at = now - timedelta(minutes=minutes_ago)
            msg.session_id = session_id
            messages.append(msg)

        return requirement, messages, session_id

    @pytest.fixture
    def mock_requirement_without_messages(self):
        """Create a mock requirement without context message IDs"""
        now = datetime.now(UTC)

        requirement = MagicMock(spec=Requirement)
        requirement.id = "req_test_002"
        requirement.title = "Performance optimization"
        requirement.description = "Optimize database queries"
        requirement.status = "confirmed"
        requirement.priority = "medium"
        requirement.category = "Performance"
        requirement.source_quote = None
        requirement.confirmed_by = "Product Manager"
        requirement.confirmed_at = now - timedelta(days=1)
        requirement.created_at = now - timedelta(days=2)
        requirement.context_message_ids = []
        requirement.open_questions = []

        return requirement

    @pytest.mark.asyncio
    async def test_get_context_with_messages(self, mock_requirement_with_messages):
        """Verify context endpoint returns requirement with messages and session info"""
        from agents.requirement_manager.app.main import app

        requirement, messages, session_id = mock_requirement_with_messages
        all_session_messages = messages.copy()

        mock_req_repo = MagicMock()
        mock_req_repo.get_by_id = AsyncMock(return_value=requirement)

        mock_msg_repo = MagicMock()

        async def get_msg_by_id(msg_id):
            for msg in messages:
                if msg.id == msg_id:
                    return msg
            return None

        mock_msg_repo.get_by_id = AsyncMock(side_effect=get_msg_by_id)
        mock_msg_repo.get_by_session = AsyncMock(return_value=all_session_messages)

        response = await _get_with_context_repositories(
            app,
            mock_req_repo,
            mock_msg_repo,
            f"/api/v1/requirements/{requirement.id}/context",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["requirement"]["id"] == "req_test_001"
        assert data["requirement"]["title"] == "Add OAuth login feature"
        assert data["requirement"]["status"] == "pending"
        assert data["requirement"]["priority"] == "high"
        assert data["requirement"]["category"] == "Feature"

        assert len(data["context_messages"]) == 3
        assert data["context_messages"][0]["sender_name"] == "Alice"
        assert (
            data["context_messages"][0]["content"]
            == "We need OAuth login feature for enterprise"
        )
        assert data["context_messages"][1]["sender_name"] == "Bob"
        assert data["context_messages"][2]["sender_name"] == "Alice"

        assert data["session"] is not None
        assert data["session"]["session_id"] == session_id
        assert data["session"]["total_messages"] == 3
        assert data["session"]["started_at"] is not None
        assert data["session"]["ended_at"] is not None

    @pytest.mark.asyncio
    async def test_get_context_without_messages(self, mock_requirement_without_messages):
        """Verify context endpoint returns requirement with empty messages and no session"""
        from agents.requirement_manager.app.main import app

        requirement = mock_requirement_without_messages
        mock_req_repo = MagicMock()
        mock_req_repo.get_by_id = AsyncMock(return_value=requirement)

        mock_msg_repo = MagicMock()
        mock_msg_repo.get_by_id = AsyncMock(return_value=None)

        response = await _get_with_context_repositories(
            app,
            mock_req_repo,
            mock_msg_repo,
            f"/api/v1/requirements/{requirement.id}/context",
        )

        assert response.status_code == 200
        data = response.json()

        assert data["requirement"]["id"] == "req_test_002"
        assert data["requirement"]["title"] == "Performance optimization"
        assert data["requirement"]["status"] == "confirmed"
        assert data["requirement"]["confirmed_by"] == "Product Manager"

        assert data["context_messages"] == []
        assert data["session"] is None

    @pytest.mark.asyncio
    async def test_get_context_requirement_not_found(self):
        """Verify 404 returned for non-existent requirement"""
        from agents.requirement_manager.app.main import app

        mock_req_repo = MagicMock()
        mock_req_repo.get_by_id = AsyncMock(return_value=None)
        mock_msg_repo = MagicMock()

        response = await _get_with_context_repositories(
            app,
            mock_req_repo,
            mock_msg_repo,
            "/api/v1/requirements/req_nonexistent/context",
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Requirement not found"

    @pytest.mark.asyncio
    async def test_get_context_partial_messages(self, mock_requirement_with_messages):
        """Verify context endpoint handles case where some messages are missing"""
        from agents.requirement_manager.app.main import app

        requirement, messages, _session_id = mock_requirement_with_messages
        available_messages = messages[:2]

        mock_req_repo = MagicMock()
        mock_req_repo.get_by_id = AsyncMock(return_value=requirement)

        mock_msg_repo = MagicMock()

        async def get_msg_by_id(msg_id):
            for msg in available_messages:
                if msg.id == msg_id:
                    return msg
            return None

        mock_msg_repo.get_by_id = AsyncMock(side_effect=get_msg_by_id)
        mock_msg_repo.get_by_session = AsyncMock(return_value=available_messages)

        response = await _get_with_context_repositories(
            app,
            mock_req_repo,
            mock_msg_repo,
            f"/api/v1/requirements/{requirement.id}/context",
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["context_messages"]) == 2
        assert data["session"] is not None


class TestRequirementContextResponseFormat:
    """Test response format for requirement context endpoint"""

    @pytest.mark.asyncio
    async def test_context_message_dict_format(self):
        """Verify message dict contains all required fields"""
        from agents.requirement_manager.app.main import app

        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        requirement = MagicMock(spec=Requirement)
        requirement.id = "req_format_001"
        requirement.title = "Format test requirement"
        requirement.description = "Test description"
        requirement.status = "pending"
        requirement.priority = "medium"
        requirement.category = "Feature"
        requirement.source_quote = "Original quote"
        requirement.confirmed_by = None
        requirement.confirmed_at = None
        requirement.created_at = now
        requirement.context_message_ids = ["msg_format_001"]
        requirement.open_questions = []

        mock_msg = MagicMock(spec=ChatMessage)
        mock_msg.id = "msg_format_001"
        mock_msg.sender_name = "Format Test User"
        mock_msg.content = "Test message content"
        mock_msg.message_type = "text"
        mock_msg.sent_at = now
        mock_msg.session_id = session_id

        mock_req_repo = MagicMock()
        mock_req_repo.get_by_id = AsyncMock(return_value=requirement)

        mock_msg_repo = MagicMock()
        mock_msg_repo.get_by_id = AsyncMock(return_value=mock_msg)
        mock_msg_repo.get_by_session = AsyncMock(return_value=[mock_msg])

        response = await _get_with_context_repositories(
            app,
            mock_req_repo,
            mock_msg_repo,
            f"/api/v1/requirements/{requirement.id}/context",
        )

        assert response.status_code == 200
        data = response.json()

        req = data["requirement"]
        assert "id" in req
        assert "title" in req
        assert "description" in req
        assert "status" in req
        assert "priority" in req
        assert "category" in req
        assert "source_quote" in req
        assert "confirmed_by" in req
        assert "confirmed_at" in req
        assert "created_at" in req

        assert len(data["context_messages"]) == 1
        msg = data["context_messages"][0]
        assert "id" in msg
        assert "sender_name" in msg
        assert "content" in msg
        assert "message_type" in msg
        assert "sent_at" in msg
        assert "session_id" in msg

        assert msg["id"] == "msg_format_001"
        assert msg["sender_name"] == "Format Test User"
        assert msg["content"] == "Test message content"
        assert msg["message_type"] == "text"
        assert msg["session_id"] == session_id

        assert data["session"] is not None
        assert "session_id" in data["session"]
        assert "total_messages" in data["session"]
        assert "started_at" in data["session"]
        assert "ended_at" in data["session"]
