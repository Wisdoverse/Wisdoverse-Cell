# shared/integrations/wecom/handlers/bot.py
"""WecomBotHandler - 处理企微 Bot 消息"""
import re
import xml.etree.ElementTree as ET
from typing import Optional

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from ..cards.builder import WecomCardBuilder

logger = get_logger("wecom.handlers.bot")


class WecomBotHandler:
    """企微 Bot 消息处理器"""

    COMMAND_PATTERN = re.compile(r"^/(\w+)(?:\s+(.*))?$")

    def __init__(self, wecom_client, agent):
        self.client = wecom_client
        self.agent = agent

    async def handle_message(self, root: ET.Element) -> None:
        """处理收到的消息"""
        from_user = root.find("FromUserName")
        content_elem = root.find("Content")

        if from_user is None or content_elem is None:
            logger.warning("wecom_invalid_message")
            return

        user_id = from_user.text or ""
        content = content_elem.text or ""

        logger.info(
            "wecom_bot_message_received",
            user_hash=hash_identifier(user_id),
            content_length=len(content),
        )

        match = self.COMMAND_PATTERN.match(content.strip())
        if match:
            command, args = match.groups()
            await self._handle_command(command, args, user_id)
        else:
            await self._handle_extract(content, user_id)

    async def _handle_command(self, command: str, args: Optional[str], user_id: str) -> None:
        """处理指令"""
        if command == "help":
            await self._send_help(user_id)
        elif command == "list":
            await self._send_list(user_id)
        elif command == "export":
            await self._send_export(user_id)
        else:
            await self.client.send_text_message(user_id, f"未知指令: /{command}")

    async def _handle_extract(self, content: str, user_id: str) -> None:
        """处理需求提取"""
        result = await self.agent.ingest_meeting(content=content, user_id=user_id)

        if result.requirements_extracted > 0:
            await self.client.send_text_message(
                user_id,
                f"已提取 {result.requirements_extracted} 个需求，{result.questions_generated} 个问题待确认"
            )
        else:
            await self.client.send_text_message(user_id, "未从内容中提取到需求")

    async def _send_help(self, user_id: str) -> None:
        """发送帮助卡片"""
        card = (
            WecomCardBuilder()
            .set_title("需求管理助手")
            .set_description("直接发送会议内容 -> 自动提取需求\n/list -> 查看待确认需求\n/export -> 导出 PRD")
            .build()
        )
        await self.client.send_template_card(user_id, card)

    async def _send_list(self, user_id: str) -> None:
        """发送待确认需求列表"""
        requirements, total, pages = await self.agent.list_pending_requirements()

        if not requirements:
            await self.client.send_text_message(user_id, "暂无待确认需求")
            return

        card = (
            WecomCardBuilder()
            .set_title(f"待确认需求 ({total})")
            .set_description(f"共 {total} 个需求")
            .build()
        )
        await self.client.send_template_card(user_id, card)

    async def _send_export(self, user_id: str) -> None:
        """导出 PRD"""
        await self.client.send_text_message(user_id, "PRD 导出功能开发中...")
