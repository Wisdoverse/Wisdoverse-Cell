"""Verify PII fields are excluded from model_dump() serialization."""
from datetime import UTC, datetime

from shared.messaging.inbound.models import Platform, UnifiedMessage


def test_raw_data_excluded_from_model_dump():
    msg = UnifiedMessage(
        platform=Platform.FEISHU,
        message_id="test_123",
        chat_id="chat_456",
        sender_id="user_789",
        timestamp=datetime.now(UTC),
        raw_data={"verification_token": "SECRET", "phone": "+1234567890"},
    )
    dumped = msg.model_dump()
    assert "raw_data" not in dumped


def test_raw_data_accessible_on_instance():
    msg = UnifiedMessage(
        platform=Platform.FEISHU,
        message_id="test_123",
        chat_id="chat_456",
        sender_id="user_789",
        timestamp=datetime.now(UTC),
        raw_data={"key": "value"},
    )
    assert msg.raw_data == {"key": "value"}
