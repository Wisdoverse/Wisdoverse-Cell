"""
Session manager.

Responsibilities:
- Manage session lifecycle
- Use a Redis delayed queue to detect timeouts
- Trigger requirement extraction
"""

import time
from typing import Optional

from redis.asyncio import Redis

from agents.requirement_manager.db.database import DatabaseManager
from agents.requirement_manager.db.repository import MessageRepository
from shared.config import settings
from shared.core.ids import IDPrefix, generate_id
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("feishu.services.session_manager")


class SessionManager:
    """Session manager that detects session end and triggers extraction."""

    REDIS_KEY = "feishu:session_timeouts"

    def __init__(self, redis: Redis, db: DatabaseManager, agent=None):
        """
        Initialize SessionManager.

        Args:
            redis: Redis async client
            db: Database manager
            agent: RequirementManagerAgent (optional, set later to avoid circular import)
        """
        self.redis = redis
        self.db = db
        self.agent = agent
        self._active_sessions: dict[str, str] = {}  # chat_id → session_id

    def set_agent(self, agent):
        """Set agent reference (called after initialization)"""
        self.agent = agent

    async def get_or_create_session(self, chat_id: str) -> str:
        """
        Get existing session or create new one.

        Each new message extends the timeout for that chat's session.
        """
        if chat_id not in self._active_sessions:
            session_id = generate_id(IDPrefix.SESSION)
            self._active_sessions[chat_id] = session_id
            logger.info(
                "session_created",
                chat_hash=hash_identifier(chat_id),
                session_id=session_id,
            )

        # Update timeout in Redis
        timeout_at = time.time() + settings.feishu_session_timeout
        await self.redis.zadd(self.REDIS_KEY, {chat_id: timeout_at})

        return self._active_sessions[chat_id]

    async def check_timeouts(self) -> list[str]:
        """
        Check and process timed-out sessions.

        Called periodically by background task.
        Returns list of session_ids that were processed.
        """
        now = time.time()

        # Get all chat_ids that have timed out
        expired = await self.redis.zrangebyscore(
            self.REDIS_KEY,
            min=0,
            max=now
        )

        processed_sessions = []

        for chat_id_bytes in expired:
            chat_id = chat_id_bytes.decode() if isinstance(chat_id_bytes, bytes) else chat_id_bytes

            session_id = self._active_sessions.pop(chat_id, None)
            if session_id:
                logger.info(
                    "session_timed_out",
                    chat_hash=hash_identifier(chat_id),
                    session_id=session_id,
                )
                await self._on_session_ended(session_id)
                processed_sessions.append(session_id)

            # Remove from Redis
            await self.redis.zrem(self.REDIS_KEY, chat_id)

        return processed_sessions

    async def _on_session_ended(self, session_id: str):
        """
        Session ended callback - trigger extraction if enough messages.
        """
        message_count = await self._get_session_message_count(session_id)

        logger.info(
            "session_ended",
            session_id=session_id,
            message_count=message_count,
            min_required=settings.feishu_min_messages_to_extract,
        )

        if message_count >= settings.feishu_min_messages_to_extract:
            logger.info(
                "session_triggering_extraction",
                session_id=session_id,
                message_count=message_count,
            )

            if self.agent:
                try:
                    await self.agent.extract_from_session(session_id)
                except Exception as e:
                    logger.error(
                        "session_extraction_failed",
                        session_id=session_id,
                        error=str(e),
                    )
        else:
            logger.info(
                "session_skipped_insufficient_messages",
                session_id=session_id,
                message_count=message_count,
            )

    async def _get_session_message_count(self, session_id: str) -> int:
        """Count messages in a session"""
        async with self.db.session() as db_session:
            repo = MessageRepository(db_session)
            return await repo.count_by_session(session_id)

    async def force_end_session(self, chat_id: str) -> Optional[str]:
        """
        Force end a session immediately (for testing or manual trigger).

        Returns session_id if session existed, None otherwise.
        """
        session_id = self._active_sessions.pop(chat_id, None)
        if session_id:
            await self.redis.zrem(self.REDIS_KEY, chat_id)
            await self._on_session_ended(session_id)
        return session_id

    async def get_active_sessions(self) -> dict[str, str]:
        """Get current active sessions (for debugging/monitoring)"""
        return dict(self._active_sessions)

    async def cleanup(self):
        """Cleanup on shutdown - end all active sessions"""
        for chat_id in list(self._active_sessions.keys()):
            await self.force_end_session(chat_id)
