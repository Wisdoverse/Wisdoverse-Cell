"""
MessageRecorder - 群聊消息被动记录器

负责：
- 白名单检查：只记录配置的群聊
- 智能过滤：跳过表情、系统消息、短消息
- 去重：message_id 唯一性检查
- 用户名缓存：减少 API 调用
- 入库存储
"""

import json
from datetime import UTC, datetime
from typing import Optional

from agents.capabilities.requirements.db.database import DatabaseManager
from agents.capabilities.requirements.db.repository import MessageRepository
from agents.capabilities.requirements.models.chat_message import ChatMessage
from shared.config import settings
from shared.utils.id_generator import IDPrefix, generate_id
from shared.utils.logger import get_logger

logger = get_logger("feishu.handlers.message")


class MessageRecorder:
    """消息记录器 - 过滤、去重、入库"""

    SKIP_MESSAGE_TYPES = {"sticker", "system", "share_card", "share_user"}
    MIN_TEXT_LENGTH = 3  # Skip "好", "OK", "+1"

    def __init__(self, feishu_client, db: DatabaseManager, session_manager=None):
        self.client = feishu_client
        self.db = db
        self.session_manager = session_manager
        self._user_cache: dict[str, str] = {}

    def set_session_manager(self, session_manager):
        """Set session manager (to avoid circular imports)"""
        self.session_manager = session_manager

    async def record(self, event_data: dict) -> Optional[ChatMessage]:
        """
        Record a message from Feishu event data.

        Args:
            event_data: The event data from im.message.receive_v1

        Returns:
            ChatMessage if recorded, None if filtered/skipped
        """
        message = event_data.get("message", {})
        chat_id = message.get("chat_id", "")
        message_id = message.get("message_id", "")
        message_type = message.get("message_type", "")

        # 1. Whitelist check
        if not self._is_monitored_chat(chat_id):
            logger.debug("message_skipped_not_monitored", chat_id=chat_id)
            return None

        # 2. Message type filter
        if not self._should_record(message):
            logger.debug("message_skipped_filtered", message_type=message_type)
            return None

        # 3. Dedup check
        if await self._exists(message_id):
            logger.debug("message_skipped_duplicate", message_id=message_id)
            return None

        # 4. Extract content
        content = self._extract_content(message)

        # 5. Get sender info
        sender = event_data.get("sender", {})
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        sender_name = await self._get_sender_name(sender_id)

        # 6. Get/create session
        session_id = None
        if self.session_manager:
            session_id = await self.session_manager.get_or_create_session(chat_id)

        # 7. Parse sent time
        create_time = message.get("create_time", "")
        sent_at = self._parse_timestamp(create_time)

        # 8. Create and save
        chat_message = ChatMessage(
            id=generate_id(IDPrefix.MESSAGE),
            chat_id=chat_id,
            message_id=message_id,
            sender_id=sender_id,
            sender_name=sender_name,
            message_type=message_type,
            content=content,
            session_id=session_id,
            sent_at=sent_at,
        )

        async with self.db.session() as db_session:
            repo = MessageRepository(db_session)
            await repo.create(chat_message)
            await db_session.commit()

        logger.info(
            "message_recorded",
            message_id=message_id,
            chat_id=chat_id,
            session_id=session_id,
            message_type=message_type,
        )

        return chat_message

    def _is_monitored_chat(self, chat_id: str) -> bool:
        """Check if chat is in whitelist"""
        monitored = settings.feishu_monitored_chat_ids
        return chat_id in monitored

    def _should_record(self, message: dict) -> bool:
        """Filter logic for message types and short messages"""
        msg_type = message.get("message_type", "")

        # Skip unwanted message types
        if msg_type in self.SKIP_MESSAGE_TYPES:
            return False

        # For text messages, check minimum length
        if msg_type == "text":
            content = self._extract_text_content(message)
            if len(content) <= self.MIN_TEXT_LENGTH:
                return False

        return True

    def _extract_content(self, message: dict) -> str:
        """Extract content based on message_type"""
        msg_type = message.get("message_type", "")
        content_str = message.get("content", "{}")

        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            return content_str

        if msg_type == "text":
            return content.get("text", "")

        elif msg_type == "post":
            # Extract plain text from rich text (post)
            return self._extract_post_text(content)

        elif msg_type == "image":
            # Store image reference
            image_key = content.get("image_key", "")
            return f"[图片: {image_key}]"

        elif msg_type == "file":
            # Store file reference
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "")
            return f"[文件: {file_name} ({file_key})]"

        elif msg_type == "audio":
            return "[语音消息]"

        elif msg_type == "video":
            return "[视频消息]"

        else:
            return f"[{msg_type}]"

    def _extract_text_content(self, message: dict) -> str:
        """Extract text from text message for length check"""
        content_str = message.get("content", "{}")
        try:
            content = json.loads(content_str)
            return content.get("text", "")
        except json.JSONDecodeError:
            return content_str

    def _extract_post_text(self, content: dict) -> str:
        """Extract plain text from post (富文本) content"""
        texts = []

        # Post content structure: {"title": "...", "content": [[{tag, text}, ...]]}
        title = content.get("title", "")
        if title:
            texts.append(title)

        paragraphs = content.get("content", [])
        for paragraph in paragraphs:
            for element in paragraph:
                tag = element.get("tag", "")
                if tag == "text":
                    texts.append(element.get("text", ""))
                elif tag == "a":
                    texts.append(element.get("text", ""))
                elif tag == "at":
                    texts.append(f"@{element.get('user_name', '')}")

        return " ".join(texts)

    async def _exists(self, feishu_message_id: str) -> bool:
        """Check if message already exists"""
        async with self.db.session() as db_session:
            repo = MessageRepository(db_session)
            existing = await repo.get_by_feishu_message_id(feishu_message_id)
            return existing is not None

    async def _get_sender_name(self, open_id: str) -> str:
        """Get sender name with caching"""
        if not open_id:
            return "Unknown"

        if open_id in self._user_cache:
            return self._user_cache[open_id]

        try:
            user_info = await self.client.get_user_info(open_id)
            name = user_info.get("name", "Unknown")
            self._user_cache[open_id] = name
            return name
        except Exception as e:
            logger.warning("get_sender_name_failed", open_id=open_id, error=str(e))
            return "Unknown"

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse Feishu timestamp (milliseconds since epoch)"""
        if not timestamp_str:
            return datetime.now(UTC)

        try:
            timestamp_ms = int(timestamp_str)
            return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        except (ValueError, TypeError):
            return datetime.now(UTC)
