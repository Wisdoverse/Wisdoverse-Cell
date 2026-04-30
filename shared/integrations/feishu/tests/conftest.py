"""Shared fixtures for feishu test suite.

Centralizes mocks, factories, and helpers used across all test files.
"""
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

# ──────────────────────────────────────────────
# Mock Infrastructure
# ──────────────────────────────────────────────


@pytest.fixture
def mock_feishu_client():
    """AsyncMock feishu client with all API methods."""
    client = MagicMock()
    client.send_card = AsyncMock(return_value="msg_card_001")
    client.reply_message = AsyncMock(return_value="msg_reply_001")
    client.update_card = AsyncMock(return_value=True)
    client.send_message = AsyncMock(return_value="msg_send_001")
    client.get_user_info = AsyncMock(return_value={
        "name": "TestUser",
        "email": "test@example.com",
        "open_id": "ou_test_user",
    })
    client.get_access_token = AsyncMock(return_value="t-test_token")
    client.verify_signature = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_feishu_sdk():
    """MagicMock lark_oapi SDK covering auth/im/contact."""
    sdk = MagicMock()

    # auth.v3
    token_resp = MagicMock()
    token_resp.success.return_value = True
    token_resp.tenant_access_token = "t-test_token"
    sdk.auth.v3.tenant_access_token.ainternal = AsyncMock(return_value=token_resp)

    # im.v1.message
    msg_resp = MagicMock()
    msg_resp.success.return_value = True
    msg_resp.data.message_id = "msg_sdk_001"
    sdk.im.v1.message.acreate = AsyncMock(return_value=msg_resp)
    sdk.im.v1.message.apatch = AsyncMock(return_value=msg_resp)
    sdk.im.v1.message.areply = AsyncMock(return_value=msg_resp)

    # contact.v3.user
    user_resp = MagicMock()
    user_resp.success.return_value = True
    user_resp.data.user.name = "SDK User"
    user_resp.data.user.email = "sdk@example.com"
    sdk.contact.v3.user.aget = AsyncMock(return_value=user_resp)

    return sdk


@dataclass
class MockIngestResult:
    """Mimics agent ingest_meeting return value."""

    meeting_id: str = "mtg_test_001"
    requirements_extracted: int = 2
    questions_generated: int = 1
    requirement_ids: list = field(default_factory=lambda: ["req_1", "req_2"])
    requirements: list = field(default_factory=lambda: [
        {"id": "req_1", "title": "Requirement 1", "description": "Desc 1", "priority": "HIGH", "category": "Feature"},
        {"id": "req_2", "title": "Requirement 2", "description": "Desc 2", "priority": "MEDIUM", "category": "Perf"},
    ])


@dataclass
class MockPRDResult:
    """Mimics PRD generation result."""

    content: str = "# PRD\n\n## Requirements\n\n1. Req one"
    requirements_count: int = 3
    generated_at: object = None

    def __post_init__(self):
        if self.generated_at is None:
            from datetime import UTC, datetime
            self.generated_at = datetime.now(UTC)


@pytest.fixture
def mock_requirement_agent():
    """MagicMock agent with confirm/reject/ingest/extract/list/batch methods."""
    agent = MagicMock()

    # Single requirement mock
    _req = MagicMock()
    _req.id = "req_123"
    _req.title = "Test Requirement"
    _req.description = "Test description"
    _req.priority = "HIGH"
    _req.category = "Feature"
    _req.status = "pending"
    _req.source_quote = "original quote"
    _req.source_meeting_ids = []

    agent.confirm_requirement = AsyncMock(return_value=_req)
    agent.reject_requirement = AsyncMock(return_value=_req)
    agent.get_requirement = AsyncMock(return_value=_req)
    agent.ingest_meeting = AsyncMock(return_value=MockIngestResult())
    agent.extract_from_session = AsyncMock()

    agent.list_pending_requirements = AsyncMock(return_value=(
        [{"id": "req_1", "title": "Req 1", "description": "Desc", "priority": "HIGH", "category": "Feature"}],
        1,
        1,
    ))
    agent.get_confirmed_requirements = AsyncMock(return_value=[
        {"id": "req_1", "title": "Req 1"},
        {"id": "req_2", "title": "Req 2"},
    ])
    agent.batch_confirm_requirements = AsyncMock(return_value=(3, 0))
    agent.batch_reject_requirements = AsyncMock(return_value=(2, 1))
    agent.get_meeting = AsyncMock(return_value=None)

    return agent


class MockRedis:
    """In-memory Redis mock supporting sorted set operations."""

    def __init__(self):
        self._data: dict[str, dict] = {}

    async def zadd(self, key: str, mapping: dict) -> int:
        if key not in self._data:
            self._data[key] = {}
        added = 0
        for member, score in mapping.items():
            if member not in self._data[key]:
                added += 1
            self._data[key][member] = score
        return added

    async def zrangebyscore(self, key: str, min: float, max: float) -> list:
        if key not in self._data:
            return []
        return [
            member.encode() if isinstance(member, str) else member
            for member, score in self._data[key].items()
            if min <= score <= max
        ]

    async def zrem(self, key: str, *members) -> int:
        if key not in self._data:
            return 0
        removed = 0
        for member in members:
            if member in self._data[key]:
                del self._data[key][member]
                removed += 1
        return removed

    def get_score(self, key: str, member: str) -> float | None:
        if key not in self._data:
            return None
        return self._data[key].get(member)


@pytest.fixture
def mock_redis():
    """In-memory Redis mock instance."""
    return MockRedis()


@pytest.fixture
def mock_db_session():
    """MagicMock database session with async context manager."""
    db = MagicMock()
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db.session.return_value = ctx
    db._session = session  # expose for assertions
    return db


@pytest.fixture
def mock_message_repo():
    """MagicMock message repository."""
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_feishu_message_id = AsyncMock(return_value=None)
    repo.count_by_session = AsyncMock(return_value=10)
    return repo


# ──────────────────────────────────────────────
# Data Factories
# ──────────────────────────────────────────────


def make_feishu_event(
    *,
    msg_type: str = "text",
    content: str = '{"text": "hello world test message"}',
    chat_id: str = "oc_test_chat",
    message_id: str = "msg_test_001",
    sender_open_id: str = "ou_sender_001",
    sender_type: str = "user",
    chat_type: str = "group",
    create_time: str = "1706169600000",
) -> dict:
    """Build a feishu im.message.receive_v1 event payload."""
    return {
        "message": {
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "message_type": msg_type,
            "content": content,
            "create_time": create_time,
        },
        "sender": {
            "sender_id": {"open_id": sender_open_id},
            "sender_type": sender_type,
        },
    }


def make_card_action(
    *,
    action_type: str = "confirm_requirement",
    req_id: str = "req_123",
    operator_open_id: str = "ou_operator_001",
    extra: dict | None = None,
) -> dict:
    """Build a feishu card action callback payload."""
    value = {"action": action_type, "req_id": req_id}
    if extra:
        value.update(extra)
    return {
        "action": {
            "tag": "button",
            "value": value,
        },
        "operator": {"open_id": operator_open_id},
    }
