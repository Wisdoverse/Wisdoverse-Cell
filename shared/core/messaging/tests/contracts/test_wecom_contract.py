"""Wecom adapter contract compliance tests."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.integrations.wecom.platform_adapter import WecomPlatformAdapter

from .adapter_contract import PlatformAdapterContract


@pytest.fixture
def adapter():
    client = MagicMock()
    client.send_text_message = AsyncMock(return_value="msg_wecom_001")
    client.send_template_card = AsyncMock(return_value="msg_wecom_card_001")
    client.update_template_card = AsyncMock(return_value=True)
    client.get_user_info = AsyncMock(return_value={
        "name": "WecomUser",
        "email": "wecom@example.com",
        "userid": "wecom_user_001",
    })
    return WecomPlatformAdapter(client=client)


@pytest.fixture
def valid_message_event():
    return {
        "MsgType": "text",
        "Content": "hello from wecom",
        "MsgId": "msg_wecom_001",
        "FromUserName": "wecom_user_001",
        "CreateTime": "1706169600",
    }


@pytest.fixture
def valid_action_event():
    return {
        "EventKey": "test_action",
        "ResponseCode": "resp_001",
        "FromUserName": "wecom_user_001",
    }


@pytest.fixture
def test_chat_id():
    return "wecom_user_001"


class TestWecomContract(PlatformAdapterContract):
    """Wecom adapter must pass all contract tests."""
    pass
