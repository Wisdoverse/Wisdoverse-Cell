# shared/integrations/wecom/tests/test_handlers.py
"""Tests for WeCom handlers."""
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.integrations.wecom.handlers.bot import WecomBotHandler


class TestWecomBotHandler:
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.send_text_message = AsyncMock(return_value="msg_1")
        client.send_template_card = AsyncMock(return_value="msg_2")
        return client

    @pytest.fixture
    def mock_agent(self):
        agent = AsyncMock()
        agent.ingest_meeting = AsyncMock(return_value=MagicMock(
            requirements_extracted=2,
            questions_generated=1,
            requirements=[]
        ))
        agent.list_pending_requirements = AsyncMock(return_value=([], 0, 0))
        return agent

    @pytest.fixture
    def handler(self, mock_client, mock_agent):
        return WecomBotHandler(mock_client, mock_agent)

    def _make_xml_message(self, content: str, from_user: str = "user1") -> ET.Element:
        xml_str = f"""
        <xml>
            <ToUserName>bot</ToUserName>
            <FromUserName>{from_user}</FromUserName>
            <CreateTime>123456</CreateTime>
            <MsgType>text</MsgType>
            <Content>{content}</Content>
            <MsgId>msg_123</MsgId>
            <AgentID>1000001</AgentID>
        </xml>
        """
        return ET.fromstring(xml_str)

    @pytest.mark.asyncio
    async def test_handle_help_command(self, handler, mock_client):
        root = self._make_xml_message("/help")
        await handler.handle_message(root)
        mock_client.send_template_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_list_command(self, handler, mock_client, mock_agent):
        root = self._make_xml_message("/list")
        await handler.handle_message(root)
        mock_agent.list_pending_requirements.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_text_message(self, handler, mock_client, mock_agent):
        root = self._make_xml_message("这是一个会议记录，包含需求...")
        await handler.handle_message(root)
        mock_agent.ingest_meeting.assert_called_once()
