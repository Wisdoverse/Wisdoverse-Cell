"""
Skill System Models - Core data structures for the skill system.

Defines permissions, matching results, execution context, and error handling.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, Field

from shared.messaging.inbound.models import AgentResponse, UnifiedCard, UnifiedMessage
from shared.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class Permission(str, Enum):
    """Skill permissions for resource access control.

    Skills declare required permissions; executor injects resources accordingly.
    """

    DB_READ = "db:read"
    DB_WRITE = "db:write"
    GATEWAY_REPLY = "gateway:reply"
    GATEWAY_SEND = "gateway:send"  # Send to any chat
    EVENT_PUBLISH = "event:publish"
    REDIS_READ = "redis:read"
    REDIS_WRITE = "redis:write"


class SkillMatch(BaseModel):
    """Result of skill matching.

    Produced by SkillMatcher when a skill matches the input message.
    """

    skill: Any = Field(..., description="The matched BaseSkill instance")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Match confidence score"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Extracted parameters from the match"
    )
    match_type: Literal["command", "pattern", "llm"] = Field(
        ..., description="How the skill was matched"
    )

    model_config = {"arbitrary_types_allowed": True}


class SkillContext:
    """Skill execution context with permission-based resource injection.

    Resources (db, redis, gateway, event_bus) are injected by the executor
    based on the skill's declared permissions.
    """

    def __init__(
        self,
        message: UnifiedMessage,
        user: User,
        parameters: dict[str, Any],
        db: Optional[AsyncSession] = None,
        redis: Optional[Any] = None,
        gateway: Optional[Any] = None,  # UnifiedGateway
        event_bus: Optional[Any] = None,
    ) -> None:
        self.message = message
        self.user = user
        self.parameters = parameters
        self.db = db
        self.redis = redis
        self.gateway = gateway
        self.event_bus = event_bus

    async def reply_text(self, text: str) -> Optional[str]:
        """Reply with text to the original message's chat.

        Returns the message ID if successful, None otherwise.
        """
        if self.gateway is None:
            return None

        return await self.gateway.send_text(
            platform=self.message.platform,
            chat_id=self.message.chat_id,
            text=text,
        )

    async def reply_card(self, card: UnifiedCard) -> Optional[str]:
        """Reply with a card to the original message's chat.

        Returns the message ID if successful, None otherwise.
        """
        if self.gateway is None:
            return None

        return await self.gateway.send_card(
            platform=self.message.platform,
            chat_id=self.message.chat_id,
            card=card,
        )


class SkillResult(BaseModel):
    """Result of skill execution.

    Contains success status, optional response, error message, and follow-up prompt.
    """

    success: bool = Field(..., description="Whether the skill executed successfully")
    response: Optional[AgentResponse] = Field(
        default=None, description="Response to send (text or card)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    follow_up: Optional[str] = Field(
        default=None, description="Follow-up prompt or hint for the user"
    )


class SkillError(Exception):
    """User-visible business error from skill execution.

    Raise this for expected errors that should be shown to the user.
    For unexpected system errors, let them propagate normally.
    """

    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__(message)
        self.message = message
        self.recoverable = recoverable

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"SkillError(message={self.message!r}, recoverable={self.recoverable})"
