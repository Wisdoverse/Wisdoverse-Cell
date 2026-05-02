"""
BotHandler - 处理 @机器人 消息

支持的指令：
- 直接发送文本 → 提取需求
- /help → 显示帮助
- /list → 列出待确认需求
- /export → 导出 PRD
"""
import json
import re
from typing import Optional

from shared.utils.logger import get_logger

from ..cards.requirement import (
    build_bot_help_card,
    build_prd_preview_card,
    build_requirement_extracted_card,
    build_requirement_list_card,
)

logger = get_logger("feishu.handlers.bot")


class BotHandler:
    """
    Bot 消息处理器

    处理用户 @机器人 发送的消息。
    """

    COMMAND_PATTERN = re.compile(r"^/(\w+)(?:\s+(.*))?$")

    def __init__(self, feishu_client, agent):
        self.client = feishu_client
        self.agent = agent

    async def handle_message(self, data: dict) -> None:
        """
        处理收到的消息

        Args:
            data: 飞书消息事件数据
        """
        message = data.get("message", {})
        message_id = message.get("message_id", "")
        chat_id = message.get("chat_id", "")
        message_type = message.get("message_type", "")

        # Only handle text messages
        if message_type != "text":
            logger.info("skipping_non_text_message", type=message_type)
            return

        # Extract text content
        content = self._extract_text(message)
        if not content:
            return

        logger.info(
            "bot_message_received",
            message_id=message_id,
            chat_id=chat_id,
            content_preview=content[:50]
        )

        # Check if it's a command
        match = self.COMMAND_PATTERN.match(content.strip())
        if match:
            command, args = match.groups()
            await self._handle_command(command, args, chat_id, message_id)
        else:
            # Regular text - extract requirements
            await self._handle_extract(content, chat_id, message_id)

    def _extract_text(self, message: dict) -> Optional[str]:
        """Extract text content from message"""
        content_str = message.get("content", "")
        try:
            content = json.loads(content_str)
            return content.get("text", "")
        except json.JSONDecodeError:
            return content_str

    async def _handle_command(
        self,
        command: str,
        args: Optional[str],
        chat_id: str,
        message_id: str
    ) -> None:
        """Handle bot commands"""
        command = command.lower()

        if command == "help":
            await self._send_help(chat_id, message_id)
        elif command == "list":
            await self._send_list(chat_id, message_id)
        elif command == "export":
            await self._send_export(chat_id, message_id)
        else:
            await self.client.reply_message(
                message_id,
                f"未知命令: /{command}\n输入 /help 查看帮助"
            )

    async def _handle_extract(
        self,
        content: str,
        chat_id: str,
        message_id: str
    ) -> None:
        """Handle text message - extract requirements"""
        try:
            # Call agent to extract requirements
            result = await self.agent.ingest_meeting(
                content=content,
                source="feishu_bot",
            )

            if result.requirements_extracted > 0:
                # Build and send card
                card = build_requirement_extracted_card(
                    requirements=result.requirements if hasattr(result, 'requirements') else [],
                    questions_count=result.questions_generated
                )
                await self.client.send_card(
                    receive_id=chat_id,
                    receive_id_type="chat_id",
                    card=card
                )
            else:
                await self.client.reply_message(
                    message_id,
                    "未从内容中识别出需求。请确保内容包含明确的需求描述。"
                )

            logger.info(
                "bot_extraction_complete",
                requirements=result.requirements_extracted,
                questions=result.questions_generated
            )

        except Exception as e:
            logger.error("bot_extraction_error", error=str(e))
            await self.client.reply_message(
                message_id,
                f"处理失败: {str(e)}"
            )

    async def _send_help(self, chat_id: str, message_id: str) -> None:
        """Send help card"""
        card = build_bot_help_card()
        await self.client.send_card(
            receive_id=chat_id,
            receive_id_type="chat_id",
            card=card
        )

    async def _send_list(self, chat_id: str, message_id: str, page: int = 1) -> None:
        """Send pending requirements list"""
        try:
            # Get pending requirements from agent
            requirements, total, total_pages = await self.agent.list_pending_requirements(
                page=page,
                page_size=5
            )

            # Build and send card
            card = build_requirement_list_card(
                requirements=requirements,
                page=page,
                total_pages=total_pages,
                total_count=total,
                chat_id=chat_id
            )

            await self.client.send_card(
                receive_id=chat_id,
                receive_id_type="chat_id",
                card=card
            )

            logger.info(
                "list_command_sent",
                total=total,
                page=page,
                total_pages=total_pages
            )

        except Exception as e:
            logger.error("list_command_error", error=str(e))
            await self.client.reply_message(
                message_id,
                f"获取需求列表失败: {str(e)}"
            )

    async def _send_export(self, chat_id: str, message_id: str) -> None:
        """Export PRD"""
        try:
            # Import generator here to avoid circular import
            from agents.capabilities.requirements.core.generator import generator

            # Get confirmed requirements
            requirements = await self.agent.get_confirmed_requirements()

            if not requirements:
                await self.client.reply_message(
                    message_id,
                    "📄 暂无已确认需求，无法生成 PRD"
                )
                return

            # Generate PRD
            result = await generator.generate_prd(requirements)

            # Build and send preview card
            card = build_prd_preview_card(
                prd_content=result.content,
                requirements_count=result.requirements_count,
                generated_at=result.generated_at
            )

            await self.client.send_card(
                receive_id=chat_id,
                receive_id_type="chat_id",
                card=card
            )

            logger.info(
                "export_command_sent",
                requirements_count=result.requirements_count
            )

        except Exception as e:
            logger.error("export_command_error", error=str(e))
            await self.client.reply_message(
                message_id,
                f"导出 PRD 失败: {str(e)}"
            )
