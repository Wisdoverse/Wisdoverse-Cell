"""OpenClaw adapter contract compliance tests."""
from unittest.mock import AsyncMock

import pytest

from shared.integrations.openclaw.platform_adapter import OpenClawPlatformAdapter

from .adapter_contract import PlatformAdapterContract


@pytest.fixture
def adapter():
    client = AsyncMock()
    client.send_request = AsyncMock(return_value={
        "message_id": "msg_oc_001",
        "success": True,
    })
    return OpenClawPlatformAdapter(client=client)


@pytest.fixture
def valid_message_event():
    return {
        "message_id": "msg_oc_001",
        "chat_id": "oc_chat_001",
        "chat_type": "group",
        "message_type": "text",
        "content": "hello from openclaw",
        "sender": {"id": "oc_user_001", "name": "OCUser"},
        "timestamp": 1706169600,
    }


@pytest.fixture
def valid_action_event():
    return {
        "action_id": "test_action",
        "message_id": "msg_oc_001",
        "operator": {"id": "oc_user_001"},
        "value": {"key": "val"},
    }


@pytest.fixture
def test_chat_id():
    return "oc_chat_001"


class TestOpenClawContract(PlatformAdapterContract):
    """OpenClaw adapter must pass all contract tests."""
    pass
