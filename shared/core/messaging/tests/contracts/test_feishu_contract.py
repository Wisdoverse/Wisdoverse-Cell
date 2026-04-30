"""Feishu adapter contract compliance tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.integrations.feishu.platform_adapter import FeishuPlatformAdapter

from .adapter_contract import PlatformAdapterContract


@pytest.fixture
def adapter():
    client = MagicMock()
    client.send_card = AsyncMock(return_value="msg_card_001")
    client.update_card = AsyncMock(return_value=True)
    client.get_user_info = AsyncMock(return_value={
        "name": "TestUser",
        "email": "test@example.com",
        "open_id": "ou_test_user",
    })
    return FeishuPlatformAdapter(client=client)


@pytest.fixture
def valid_message_event():
    return {
        "message": {
            "message_id": "msg_test_001",
            "chat_id": "oc_test_chat",
            "chat_type": "group",
            "message_type": "text",
            "content": '{"text": "hello"}',
            "create_time": "1706169600000",
        },
        "sender": {
            "sender_id": {"open_id": "ou_sender_001"},
            "sender_type": "user",
        },
    }


@pytest.fixture
def valid_action_event():
    return {
        "action": {"tag": "button", "value": {"action": "test"}},
        "operator": {"open_id": "ou_operator_001"},
    }


@pytest.fixture
def test_chat_id():
    return "oc_test_chat"


class TestFeishuContract(PlatformAdapterContract):
    """Feishu adapter must pass all contract tests."""
