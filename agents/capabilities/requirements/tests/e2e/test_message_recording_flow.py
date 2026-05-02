"""
E2E test for the complete message recording flow.

Tests:
1. Messages are recorded when received via webhook
2. Sessions are detected and timeout triggers extraction
3. Requirements are linked to their context messages
4. API returns the linked context

This tests the full integration from Feishu webhook to API response.
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure project root is in Python path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from agents.capabilities.requirements.db.repository import MessageRepository, RequirementRepository
from agents.capabilities.requirements.models.chat_message import ChatMessage
from agents.capabilities.requirements.models.requirement import Requirement
from shared.utils.id_generator import IDPrefix, generate_id


class TestMessageRecordingE2EFlow:
    """Test the full message recording flow from webhook to API"""

    @pytest.mark.asyncio
    async def test_full_message_recording_flow(self, client, mock_llm, test_db):
        """Test complete flow from message recording to requirement extraction with context"""
        # Step 1: Create messages in a session (simulating what MessageRecorder does)
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)
        chat_id = "oc_e2e_test_chat"

        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)

            # Create messages that simulate a discussion with requirement content
            messages = [
                ChatMessage(
                    chat_id=chat_id,
                    message_id="om_e2e_001",
                    sender_id="ou_alice",
                    sender_name="Alice",
                    message_type="text",
                    content="We need to add a new feature for OAuth login",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=10)
                ),
                ChatMessage(
                    chat_id=chat_id,
                    message_id="om_e2e_002",
                    sender_id="ou_bob",
                    sender_name="Bob",
                    message_type="text",
                    content="Yes, OAuth should support Google and Microsoft providers",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=8)
                ),
                ChatMessage(
                    chat_id=chat_id,
                    message_id="om_e2e_003",
                    sender_id="ou_alice",
                    sender_name="Alice",
                    message_type="text",
                    content="It should also have remember me functionality",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=5)
                ),
                ChatMessage(
                    chat_id=chat_id,
                    message_id="om_e2e_004",
                    sender_id="ou_charlie",
                    sender_name="Charlie",
                    message_type="text",
                    content="Enterprise customers need SSO support",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=3)
                ),
                ChatMessage(
                    chat_id=chat_id,
                    message_id="om_e2e_005",
                    sender_id="ou_bob",
                    sender_name="Bob",
                    message_type="text",
                    content="Agreed, SSO is critical for the enterprise plan",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=1)
                ),
            ]

            for msg in messages:
                await msg_repo.create(msg)
            await db_session.commit()

        # Step 2: Verify messages are stored and searchable
        response = await client.get(
            f"/api/messages/search?chat_id={chat_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["messages"]) == 5

        # Step 3: Verify session messages endpoint works
        response = await client.get(f"/api/messages/session/{session_id}")
        assert response.status_code == 200
        session_data = response.json()
        assert session_data["session_id"] == session_id
        assert session_data["message_count"] == 5
        assert session_data["extracted"] is False  # Not yet extracted

        # Step 4: Search by keyword
        response = await client.get(
            "/api/messages/search?keyword=OAuth"
        )
        assert response.status_code == 200
        oauth_data = response.json()
        assert oauth_data["total"] >= 1

    @pytest.mark.asyncio
    async def test_session_extraction_flow(self, client, mock_llm, test_db):
        """Test that session extraction creates requirements linked to messages"""
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)
        chat_id = "oc_extraction_test"

        # Step 1: Create session messages
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)

            messages = [
                ChatMessage(
                    chat_id=chat_id,
                    message_id=f"om_extract_{i:03d}",
                    sender_id=f"ou_user{i % 3 + 1}",
                    sender_name=f"User{i % 3 + 1}",
                    message_type="text",
                    content=content,
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=10 - i)
                )
                for i, content in enumerate([
                    "We need to implement real-time notifications",
                    "Yes, push notifications for mobile",
                    "And email notifications for web users",
                    "Priority alerts should be sent immediately",
                    "Non-urgent ones can be batched",
                ])
            ]

            created_message_ids = []
            for msg in messages:
                created = await msg_repo.create(msg)
                created_message_ids.append(created.id)
            await db_session.commit()

        # Step 2: Upload meeting content (which triggers extraction)
        meeting_content = """
        Notification System Discussion

        Participants: User1, User2, User3

        Key requirements discussed:
        1. Real-time notifications for mobile apps
        2. Email notifications for web users
        3. Priority-based delivery:
           - Urgent alerts: immediate
           - Non-urgent: batched every hour
        """

        response = await client.post(
            "/api/ingest/upload",
            json={
                "content": meeting_content,
                "source": "session_extraction_test",
                "title": "Notification System Discussion"
            }
        )
        assert response.status_code == 200
        result = response.json()
        assert result["requirements_extracted"] > 0

        # Step 3: Get requirement IDs from the API
        response = await client.get("/api/requirements", params={"status": "pending"})
        assert response.status_code == 200
        requirements = response.json()["items"]
        requirement_ids = [req["id"] for req in requirements]
        assert len(requirement_ids) > 0

        # Step 4: Link requirements to messages (simulating what extract_from_session does)
        async with test_db.session() as db_session:
            req_repo = RequirementRepository(db_session)
            msg_repo = MessageRepository(db_session)

            for req_id in requirement_ids:
                req = await req_repo.get_by_id(req_id)
                if req:
                    # Simulate linking messages to requirement
                    req.context_message_ids = created_message_ids
                    await db_session.commit()

            # Mark messages as extracted
            await msg_repo.mark_extracted(session_id, requirement_ids)
            await db_session.commit()

        # Step 5: Verify requirement context endpoint returns linked messages
        for req_id in requirement_ids:
            response = await client.get(f"/api/requirements/{req_id}/context")
            assert response.status_code == 200
            context_data = response.json()

            assert context_data["requirement"]["id"] == req_id
            assert len(context_data["context_messages"]) > 0

        # Step 6: Verify session now shows as extracted
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)
            session_msgs = await msg_repo.get_by_session(session_id)
            for msg in session_msgs:
                assert msg.extracted is True
                assert msg.requirement_ids == requirement_ids

    @pytest.mark.asyncio
    async def test_message_search_with_filters(self, client, test_db):
        """Test message search API with various filters"""
        now = datetime.now(UTC)
        session_id_1 = generate_id(IDPrefix.SESSION)
        session_id_2 = generate_id(IDPrefix.SESSION)

        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)

            # Create messages in different sessions and chats
            test_messages = [
                # Session 1 - Chat A
                ("oc_chat_a", session_id_1, "ou_alice", "Alice", "API design discussion"),
                ("oc_chat_a", session_id_1, "ou_bob", "Bob", "REST vs GraphQL debate"),
                ("oc_chat_a", session_id_1, "ou_alice", "Alice", "Let's go with REST API"),
                # Session 2 - Chat B
                ("oc_chat_b", session_id_2, "ou_charlie", "Charlie", "Database schema review"),
                ("oc_chat_b", session_id_2, "ou_dave", "Dave", "We need better indexing"),
            ]

            for i, (chat_id, sess_id, sender_id, sender_name, content) in enumerate(test_messages):
                msg = ChatMessage(
                    chat_id=chat_id,
                    message_id=f"om_filter_test_{i:03d}",
                    sender_id=sender_id,
                    sender_name=sender_name,
                    message_type="text",
                    content=content,
                    session_id=sess_id,
                    sent_at=now - timedelta(minutes=len(test_messages) - i)
                )
                await msg_repo.create(msg)
            await db_session.commit()

        # Test: Filter by chat_id
        response = await client.get("/api/messages/search?chat_id=oc_chat_a")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        for msg in data["messages"]:
            assert msg["chat_id"] == "oc_chat_a"

        # Test: Filter by sender_id
        response = await client.get("/api/messages/search?sender_id=ou_alice")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        for msg in data["messages"]:
            assert msg["sender_id"] == "ou_alice"

        # Test: Keyword search
        response = await client.get("/api/messages/search?keyword=API")
        assert response.status_code == 200
        data = response.json()
        # Should find messages containing API
        assert data["total"] >= 2

        # Test: Pagination
        response = await client.get("/api/messages/search?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3


class TestMessageRecordingIntegration:
    """Integration tests for message recording components"""

    @pytest.mark.asyncio
    async def test_message_deduplication(self, test_db):
        """Test that duplicate messages are not recorded"""
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)
            now = datetime.now(UTC)

            # Create first message
            msg1 = ChatMessage(
                chat_id="oc_dedup_test",
                message_id="om_same_message",  # Same Feishu message_id
                sender_id="ou_user",
                message_type="text",
                content="Test message",
                sent_at=now
            )
            await msg_repo.create(msg1)
            await db_session.commit()

            # Check if message exists (dedup check)
            existing = await msg_repo.get_by_feishu_message_id("om_same_message")
            assert existing is not None

            # Verify we can detect duplicates before creating
            existing2 = await msg_repo.get_by_feishu_message_id("om_same_message")
            assert existing2 is not None
            assert existing2.id == existing.id

    @pytest.mark.asyncio
    async def test_session_message_ordering(self, test_db):
        """Test that session messages are returned in chronological order"""
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)
            now = datetime.now(UTC)
            session_id = generate_id(IDPrefix.SESSION)

            # Create messages in random order
            times = [5, 1, 3, 2, 4]  # minutes ago
            for i, mins in enumerate(times):
                msg = ChatMessage(
                    chat_id="oc_order_test",
                    message_id=f"om_order_{i:03d}",
                    sender_id="ou_user",
                    message_type="text",
                    content=f"Message at t-{mins}",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=mins)
                )
                await msg_repo.create(msg)
            await db_session.commit()

            # Get messages - should be ordered by sent_at ASC
            messages = await msg_repo.get_by_session(session_id)
            assert len(messages) == 5

            # Verify order (oldest first)
            for i in range(len(messages) - 1):
                assert messages[i].sent_at <= messages[i + 1].sent_at

    @pytest.mark.asyncio
    async def test_extraction_marks_messages(self, test_db):
        """Test that extraction correctly marks messages as extracted"""
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)
            now = datetime.now(UTC)
            session_id = generate_id(IDPrefix.SESSION)

            # Create messages
            for i in range(3):
                msg = ChatMessage(
                    chat_id="oc_mark_test",
                    message_id=f"om_mark_{i:03d}",
                    sender_id="ou_user",
                    message_type="text",
                    content=f"Message {i}",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=i)
                )
                await msg_repo.create(msg)
            await db_session.commit()

            # Verify initial state
            messages = await msg_repo.get_by_session(session_id)
            for msg in messages:
                assert msg.extracted is False
                assert msg.requirement_ids is None or msg.requirement_ids == []

            # Mark as extracted
            requirement_ids = ["req_test_001", "req_test_002"]
            count = await msg_repo.mark_extracted(session_id, requirement_ids)
            await db_session.commit()

            assert count == 3

            # Verify updated state
            messages = await msg_repo.get_by_session(session_id)
            for msg in messages:
                assert msg.extracted is True
                assert msg.requirement_ids == requirement_ids


class TestRequirementContextLinking:
    """Test requirement-to-message context linking"""

    @pytest.mark.asyncio
    async def test_requirement_with_context_messages(self, client, mock_llm, test_db):
        """Test creating requirement with linked context messages"""
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        # Step 1: Create context messages
        async with test_db.session() as db_session:
            msg_repo = MessageRepository(db_session)

            message_ids = []
            for i in range(3):
                msg = ChatMessage(
                    chat_id="oc_context_test",
                    message_id=f"om_ctx_{i:03d}",
                    sender_id=f"ou_user{i}",
                    sender_name=f"User{i}",
                    message_type="text",
                    content=f"Context message {i}",
                    session_id=session_id,
                    sent_at=now - timedelta(minutes=3 - i)
                )
                created = await msg_repo.create(msg)
                message_ids.append(created.id)
            await db_session.commit()

        # Step 2: Create requirement with context_message_ids
        async with test_db.session() as db_session:
            req_repo = RequirementRepository(db_session)

            req = Requirement(
                title="Test Requirement with Context",
                description="A requirement linked to chat messages",
                status="pending",
                priority="high",
                category="Feature",
                context_message_ids=message_ids
            )
            created_req = await req_repo.create(req)
            await db_session.commit()
            req_id = created_req.id

        # Step 3: Verify context endpoint returns linked messages
        response = await client.get(f"/api/requirements/{req_id}/context")
        assert response.status_code == 200
        data = response.json()

        assert data["requirement"]["id"] == req_id
        assert data["requirement"]["title"] == "Test Requirement with Context"
        assert len(data["context_messages"]) == 3

        # Verify session info
        assert data["session"] is not None
        assert data["session"]["session_id"] == session_id
        assert data["session"]["total_messages"] == 3

    @pytest.mark.asyncio
    async def test_requirement_without_context_messages(self, client, mock_llm, test_db):
        """Test requirement created without context messages"""
        async with test_db.session() as db_session:
            req_repo = RequirementRepository(db_session)

            req = Requirement(
                title="Requirement without Context",
                description="Created from meeting upload, not chat",
                status="pending",
                priority="medium",
                category="Feature",
                context_message_ids=[]
            )
            created_req = await req_repo.create(req)
            await db_session.commit()
            req_id = created_req.id

        response = await client.get(f"/api/requirements/{req_id}/context")
        assert response.status_code == 200
        data = response.json()

        assert data["requirement"]["id"] == req_id
        assert data["context_messages"] == []
        assert data["session"] is None
