"""
Skill Executor - Manages context, permissions, and error handling for skill execution.

The executor builds execution context based on skill permissions, executes the skill,
handles errors, and sends responses through the gateway.
"""
import logging
from typing import Any, Callable, Optional

from shared.infra.skill.base import BaseSkill
from shared.infra.skill.models import (
    Permission,
    SkillContext,
    SkillError,
    SkillResult,
)
from shared.messaging.inbound.models import AgentResponse, UnifiedMessage
from shared.models.user import User

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Skill executor - manages context, permissions, and error handling.

    Builds execution context with permission-based resource injection,
    executes skills, and handles responses and errors.
    """

    def __init__(
        self,
        gateway: Any,  # UnifiedGateway, use Any to avoid circular import
        db_session_factory: Optional[Callable[[], Any]] = None,  # Returns AsyncSession
        redis: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize the skill executor.

        Args:
            gateway: UnifiedGateway instance for sending responses.
            db_session_factory: Factory function that returns an AsyncSession.
            redis: Redis client instance.
            event_bus: EventBus instance for publishing events.
        """
        self.gateway = gateway
        self.db_session_factory = db_session_factory
        self.redis = redis
        self.event_bus = event_bus

    async def execute(
        self,
        skill: BaseSkill,
        message: UnifiedMessage,
        user: User,
        parameters: dict[str, Any],
    ) -> SkillResult:
        """Execute a skill with the given context.

        Args:
            skill: The skill to execute.
            message: The incoming message that triggered the skill.
            user: The user who sent the message.
            parameters: Parameters extracted from the message.

        Returns:
            SkillResult indicating success/failure and optional response.
        """
        # 1. Build context with permission-based resource injection
        context = await self._build_context(skill, message, user, parameters)

        try:
            # 2. Execute the skill
            result = await skill.execute(context)

            # 3. If result has a response, send it via gateway
            if result.response:
                await self._send_response(message, result.response)

            # 4. If result has a follow-up, send text via gateway
            if result.follow_up:
                await self.gateway.send_text(
                    platform=message.platform,
                    chat_id=message.chat_id,
                    text=result.follow_up,
                )

            # 7. Return the result
            return result

        except SkillError as e:
            # 5. Handle SkillError: send user-visible message
            logger.warning(
                "Skill %s raised SkillError: %s (recoverable=%s)",
                skill.name,
                e.message,
                e.recoverable,
            )
            await self.gateway.send_text(
                platform=message.platform,
                chat_id=message.chat_id,
                text=f"⚠️ {e.message}",
            )
            return SkillResult(success=False, error=e.message)

        except Exception as e:
            # 6. Handle unexpected exceptions: log and send generic error
            logger.exception("Skill %s failed with unexpected error", skill.name)
            await self.gateway.send_text(
                platform=message.platform,
                chat_id=message.chat_id,
                text="系统繁忙，请稍后重试",
            )
            return SkillResult(success=False, error=str(e))

    async def _build_context(
        self,
        skill: BaseSkill,
        message: UnifiedMessage,
        user: User,
        parameters: dict[str, Any],
    ) -> SkillContext:
        """Build execution context with permission-based resource injection.

        Args:
            skill: The skill being executed.
            message: The incoming message.
            user: The user who sent the message.
            parameters: Extracted parameters.

        Returns:
            SkillContext with appropriate resources injected.
        """
        # Start with base context
        db = None
        redis = None
        event_bus = None

        perms = skill.permissions

        # Inject DB session if DB_READ or DB_WRITE permission
        if Permission.DB_READ in perms or Permission.DB_WRITE in perms:
            if self.db_session_factory is not None:
                db = self.db_session_factory()

        # Inject Redis if REDIS_READ or REDIS_WRITE permission
        if Permission.REDIS_READ in perms or Permission.REDIS_WRITE in perms:
            redis = self.redis

        # Inject event bus if EVENT_PUBLISH permission
        if Permission.EVENT_PUBLISH in perms:
            event_bus = self.event_bus

        # Always set gateway for reply methods (GATEWAY_REPLY is the default permission)
        # The context's reply_text/reply_card methods need the gateway
        context_gateway = self.gateway

        return SkillContext(
            message=message,
            user=user,
            parameters=parameters,
            db=db,
            redis=redis,
            gateway=context_gateway,
            event_bus=event_bus,
        )

    async def _send_response(
        self,
        message: UnifiedMessage,
        response: AgentResponse,
    ) -> Optional[str]:
        """Send a response through the gateway.

        Args:
            message: The original message (for platform and chat_id).
            response: The response to send.

        Returns:
            Message ID if sent successfully, None otherwise.
        """
        if response.card:
            # Send card response
            return await self.gateway.send_card(
                platform=message.platform,
                chat_id=message.chat_id,
                card=response.card,
            )
        elif response.text:
            # Send text response
            return await self.gateway.send_text(
                platform=message.platform,
                chat_id=message.chat_id,
                text=response.text,
            )

        return None
