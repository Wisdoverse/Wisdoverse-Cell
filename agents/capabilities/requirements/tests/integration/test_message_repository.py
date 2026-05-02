"""
Integration tests for MessageRepository

Tests:
- Create and get_by_id
- Get by Feishu message_id (dedup)
- Search with keyword (full-text search)
- Search with filters (chat_id, sender_id, time range)
- Get by session
- Count by session
- Mark extracted
"""
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Ensure project root is in Python path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
import pytest_asyncio

from agents.capabilities.requirements.db.repository import MessageRepository
from agents.capabilities.requirements.models.chat_message import ChatMessage
from shared.utils.id_generator import IDPrefix, generate_id


class TestMessageRepositoryCreate:
    """Test MessageRepository create operations"""

    @pytest.mark.asyncio
    async def test_create_and_get_by_id(self, db_session):
        """Verify message can be created and retrieved by ID"""
        repo = MessageRepository(db_session)

        now = datetime.now(UTC)
        message = ChatMessage(
            chat_id="oc_chat001",
            message_id="om_msg001",
            sender_id="ou_user001",
            sender_name="Test User",
            message_type="text",
            content="This is a test message for requirement discussion",
            sent_at=now
        )

        created = await repo.create(message)
        await db_session.commit()

        assert created.id is not None
        assert created.id.startswith(f"{IDPrefix.MESSAGE}_")

        # Retrieve by ID
        retrieved = await repo.get_by_id(created.id)

        assert retrieved is not None
        assert retrieved.chat_id == "oc_chat001"
        assert retrieved.message_id == "om_msg001"
        assert retrieved.sender_id == "ou_user001"
        assert retrieved.sender_name == "Test User"
        assert retrieved.message_type == "text"
        assert retrieved.content == "This is a test message for requirement discussion"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session):
        """Verify get_by_id returns None for non-existent ID"""
        repo = MessageRepository(db_session)

        result = await repo.get_by_id("msg_nonexistent")

        assert result is None


class TestMessageRepositoryDedup:
    """Test MessageRepository deduplication"""

    @pytest.mark.asyncio
    async def test_get_by_feishu_message_id(self, db_session):
        """Verify message can be retrieved by Feishu message_id for dedup"""
        repo = MessageRepository(db_session)

        message = ChatMessage(
            chat_id="oc_chat001",
            message_id="om_feishu_unique_123",
            sender_id="ou_user001",
            message_type="text",
            content="Test content",
            sent_at=datetime.now(UTC)
        )

        await repo.create(message)
        await db_session.commit()

        # Retrieve by Feishu message_id
        retrieved = await repo.get_by_feishu_message_id("om_feishu_unique_123")

        assert retrieved is not None
        assert retrieved.message_id == "om_feishu_unique_123"

    @pytest.mark.asyncio
    async def test_get_by_feishu_message_id_not_found(self, db_session):
        """Verify get_by_feishu_message_id returns None for non-existent message_id"""
        repo = MessageRepository(db_session)

        result = await repo.get_by_feishu_message_id("om_nonexistent")

        assert result is None


class TestMessageRepositorySearch:
    """Test MessageRepository search operations"""

    @pytest_asyncio.fixture
    async def search_test_messages(self, db_session):
        """Create test messages for search tests"""
        repo = MessageRepository(db_session)
        now = datetime.now(UTC)

        messages = [
            ChatMessage(
                chat_id="oc_search_chat",
                message_id="om_search_001",
                sender_id="ou_alice",
                sender_name="Alice",
                message_type="text",
                content="We need a user login feature with OAuth support",
                sent_at=now - timedelta(hours=5)
            ),
            ChatMessage(
                chat_id="oc_search_chat",
                message_id="om_search_002",
                sender_id="ou_bob",
                sender_name="Bob",
                message_type="text",
                content="The dashboard should display analytics data",
                sent_at=now - timedelta(hours=4)
            ),
            ChatMessage(
                chat_id="oc_search_chat",
                message_id="om_search_003",
                sender_id="ou_alice",
                sender_name="Alice",
                message_type="text",
                content="OAuth integration is critical for enterprise customers",
                sent_at=now - timedelta(hours=3)
            ),
            ChatMessage(
                chat_id="oc_other_chat",
                message_id="om_search_004",
                sender_id="ou_charlie",
                sender_name="Charlie",
                message_type="text",
                content="The API needs better rate limiting",
                sent_at=now - timedelta(hours=2)
            ),
            ChatMessage(
                chat_id="oc_search_chat",
                message_id="om_search_005",
                sender_id="ou_bob",
                sender_name="Bob",
                message_type="text",
                content="API documentation must be updated",
                sent_at=now - timedelta(hours=1)
            ),
        ]

        for msg in messages:
            await repo.create(msg)
        await db_session.commit()

        return messages

    @pytest.mark.asyncio
    async def test_search_with_keyword(self, db_session, search_test_messages):
        """Verify keyword search uses PostgreSQL full-text search"""
        repo = MessageRepository(db_session)

        # Search for "OAuth"
        results, total = await repo.search(keyword="OAuth")

        assert total == 2
        assert len(results) == 2
        # Results should be ordered by sent_at desc
        assert "OAuth" in results[0].content or "OAuth" in results[1].content

    @pytest.mark.asyncio
    async def test_search_with_chat_id_filter(self, db_session, search_test_messages):
        """Verify search can filter by chat_id"""
        repo = MessageRepository(db_session)

        results, total = await repo.search(chat_id="oc_search_chat")

        assert total == 4
        assert len(results) == 4
        for msg in results:
            assert msg.chat_id == "oc_search_chat"

    @pytest.mark.asyncio
    async def test_search_with_sender_id_filter(self, db_session, search_test_messages):
        """Verify search can filter by sender_id"""
        repo = MessageRepository(db_session)

        results, total = await repo.search(sender_id="ou_alice")

        assert total == 2
        assert len(results) == 2
        for msg in results:
            assert msg.sender_id == "ou_alice"

    @pytest.mark.asyncio
    async def test_search_with_time_range(self, db_session, search_test_messages):
        """Verify search can filter by time range"""
        repo = MessageRepository(db_session)
        now = datetime.now(UTC)

        # Search for messages in the last 2.5 hours (should get 3 messages)
        # Messages are at: -5h, -4h, -3h, -2h, -1h
        # So -2.5h to now should get: -2h and -1h = 2 messages
        results, total = await repo.search(
            start_time=now - timedelta(hours=2, minutes=30),
            end_time=now
        )

        assert total == 2
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_with_combined_filters(self, db_session, search_test_messages):
        """Verify search can combine multiple filters"""
        repo = MessageRepository(db_session)

        # Search for API in oc_search_chat
        results, total = await repo.search(
            keyword="API",
            chat_id="oc_search_chat"
        )

        assert total == 1
        assert len(results) == 1
        assert results[0].chat_id == "oc_search_chat"
        assert "API" in results[0].content

    @pytest.mark.asyncio
    async def test_search_pagination(self, db_session, search_test_messages):
        """Verify search pagination works correctly"""
        repo = MessageRepository(db_session)

        # Get first page
        page1_results, total = await repo.search(
            chat_id="oc_search_chat",
            page=1,
            page_size=2
        )

        assert total == 4
        assert len(page1_results) == 2

        # Get second page
        page2_results, _ = await repo.search(
            chat_id="oc_search_chat",
            page=2,
            page_size=2
        )

        assert len(page2_results) == 2

        # Verify no overlap
        page1_ids = {msg.id for msg in page1_results}
        page2_ids = {msg.id for msg in page2_results}
        assert page1_ids.isdisjoint(page2_ids)

    @pytest.mark.asyncio
    async def test_search_no_results(self, db_session, search_test_messages):
        """Verify search returns empty list when no matches"""
        repo = MessageRepository(db_session)

        results, total = await repo.search(keyword="nonexistent_keyword_xyz")

        assert total == 0
        assert len(results) == 0


class TestMessageRepositorySession:
    """Test MessageRepository session operations"""

    @pytest_asyncio.fixture
    async def session_test_messages(self, db_session):
        """Create test messages for session tests"""
        repo = MessageRepository(db_session)
        now = datetime.now(UTC)

        session_id = generate_id(IDPrefix.SESSION)

        messages = [
            ChatMessage(
                chat_id="oc_session_chat",
                message_id="om_session_001",
                sender_id="ou_user001",
                message_type="text",
                content="First message in session",
                session_id=session_id,
                sent_at=now - timedelta(minutes=10)
            ),
            ChatMessage(
                chat_id="oc_session_chat",
                message_id="om_session_002",
                sender_id="ou_user002",
                message_type="text",
                content="Second message in session",
                session_id=session_id,
                sent_at=now - timedelta(minutes=5)
            ),
            ChatMessage(
                chat_id="oc_session_chat",
                message_id="om_session_003",
                sender_id="ou_user001",
                message_type="text",
                content="Third message in session",
                session_id=session_id,
                sent_at=now
            ),
            # Message in different session
            ChatMessage(
                chat_id="oc_other_chat",
                message_id="om_other_001",
                sender_id="ou_user003",
                message_type="text",
                content="Message in other session",
                session_id="ses_other",
                sent_at=now
            ),
        ]

        for msg in messages:
            await repo.create(msg)
        await db_session.commit()

        return session_id, messages

    @pytest.mark.asyncio
    async def test_get_by_session(self, db_session, session_test_messages):
        """Verify get_by_session returns all messages in session ordered by sent_at"""
        repo = MessageRepository(db_session)
        session_id, _ = session_test_messages

        results = await repo.get_by_session(session_id)

        assert len(results) == 3
        # Should be ordered by sent_at ASC
        assert results[0].message_id == "om_session_001"
        assert results[1].message_id == "om_session_002"
        assert results[2].message_id == "om_session_003"

    @pytest.mark.asyncio
    async def test_get_by_session_empty(self, db_session):
        """Verify get_by_session returns empty list for non-existent session"""
        repo = MessageRepository(db_session)

        results = await repo.get_by_session("ses_nonexistent")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_count_by_session(self, db_session, session_test_messages):
        """Verify count_by_session returns correct count"""
        repo = MessageRepository(db_session)
        session_id, _ = session_test_messages

        count = await repo.count_by_session(session_id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_count_by_session_empty(self, db_session):
        """Verify count_by_session returns 0 for non-existent session"""
        repo = MessageRepository(db_session)

        count = await repo.count_by_session("ses_nonexistent")

        assert count == 0


class TestMessageRepositoryExtraction:
    """Test MessageRepository extraction operations"""

    @pytest.mark.asyncio
    async def test_mark_extracted(self, db_session):
        """Verify mark_extracted updates all session messages"""
        repo = MessageRepository(db_session)
        now = datetime.now(UTC)
        session_id = generate_id(IDPrefix.SESSION)

        # Create messages in session
        messages = [
            ChatMessage(
                chat_id="oc_extract_chat",
                message_id="om_extract_001",
                sender_id="ou_user001",
                message_type="text",
                content="Message 1",
                session_id=session_id,
                sent_at=now - timedelta(minutes=5)
            ),
            ChatMessage(
                chat_id="oc_extract_chat",
                message_id="om_extract_002",
                sender_id="ou_user002",
                message_type="text",
                content="Message 2",
                session_id=session_id,
                sent_at=now
            ),
        ]

        for msg in messages:
            await repo.create(msg)
        await db_session.commit()

        # Mark as extracted
        requirement_ids = ["req_001", "req_002"]
        updated_count = await repo.mark_extracted(session_id, requirement_ids)
        await db_session.commit()

        assert updated_count == 2

        # Verify messages are updated
        session_messages = await repo.get_by_session(session_id)

        for msg in session_messages:
            assert msg.extracted is True
            assert msg.requirement_ids == requirement_ids

    @pytest.mark.asyncio
    async def test_mark_extracted_no_messages(self, db_session):
        """Verify mark_extracted handles non-existent session gracefully"""
        repo = MessageRepository(db_session)

        updated_count = await repo.mark_extracted("ses_nonexistent", ["req_001"])

        assert updated_count == 0
