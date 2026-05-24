"""
BotHandler for @bot message events.

Supported commands:
- Plain text: extract requirements
- /help: show help
- /list: list pending requirements
- /export: export PRD
"""
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .acl import FeishuBotMessage
from .cards.requirement import (
    build_bot_help_card,
    build_prd_preview_card,
    build_requirement_extracted_card,
    build_requirement_list_card,
)

logger = get_logger("feishu.handlers.bot")


class BotHandler:
    """
    Feishu bot message handler.

    Handles messages that users send to the bot.
    """

    def __init__(self, feishu_client, agent):
        self.client = feishu_client
        self.agent = agent

    async def handle_message(self, data: dict) -> None:
        """
        Handle an inbound Feishu message event.

        Args:
            data: Feishu message event data.
        """
        message = FeishuBotMessage.from_payload(data)

        if not message.is_text:
            logger.info("skipping_non_text_message", type=message.message_type)
            return

        if not message.has_text:
            return

        logger.info(
            "bot_message_received",
            message_hash=hash_identifier(message.message_id),
            chat_hash=hash_identifier(message.chat_id),
            content_length=len(message.text),
        )

        if message.command:
            await self._handle_command(
                message.command.name,
                message.command.args,
                message.chat_id,
                message.message_id,
            )
        else:
            await self._handle_extract(message, message.message_id)

    async def _handle_command(
        self,
        command: str,
        args: str | None,
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
        message: FeishuBotMessage,
        message_id: str,
    ) -> None:
        """Handle text message - extract requirements"""
        try:
            result = await self.agent.ingest_meeting(**message.ingest_kwargs())

            if result.requirements_extracted > 0:
                # Build and send card
                card = build_requirement_extracted_card(
                    requirements=result.requirements if hasattr(result, 'requirements') else [],
                    questions_count=result.questions_generated
                )
                await self.client.send_card(
                    receive_id=message.chat_id,
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
            from agents.requirement_manager.core.generator import DocumentGenerator
            from shared.control_plane.agent_prompt_config import (
                resolve_agent_system_prompt,
            )
            from shared.infra.llm_gateway import llm_gateway

            # Get confirmed requirements
            requirements = await self.agent.get_confirmed_requirements()

            if not requirements:
                await self.client.reply_message(
                    message_id,
                    "📄 暂无已确认需求，无法生成 PRD"
                )
                return

            # Generate PRD
            generator = DocumentGenerator(
                llm=llm_gateway,
                system_prompt_resolver=resolve_agent_system_prompt,
            )
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
