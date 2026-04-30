"""
Skill Service - Unified interface for the skill system.

Coordinates the registry, matcher, and executor to provide a single entry point
for handling messages with skills.
"""
import logging
from typing import Optional

from shared.infra.skill.executor import SkillExecutor
from shared.infra.skill.matcher import SkillMatcher
from shared.infra.skill.models import SkillResult
from shared.infra.skill.registry import SkillRegistry
from shared.messaging.inbound.models import UnifiedMessage
from shared.models.user import User

logger = logging.getLogger(__name__)


class SkillService:
    """Skill service - unified interface for skill system.

    Coordinates registry, matcher, and executor to provide a single
    entry point for skill-based message handling.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        matcher: SkillMatcher,
        executor: SkillExecutor,
    ):
        """Initialize the skill service.

        Args:
            registry: The skill registry containing registered skills.
            matcher: The skill matcher for message-to-skill matching.
            executor: The skill executor for running matched skills.
        """
        self.registry = registry
        self.matcher = matcher
        self.executor = executor

    async def try_handle(
        self,
        message: UnifiedMessage,
        user: User,
    ) -> Optional[SkillResult]:
        """Try to handle message with a skill.

        Returns SkillResult if a skill handled the message, None otherwise.
        The gateway should continue to regular message_handler if None is returned.

        Args:
            message: The incoming unified message.
            user: The user who sent the message.

        Returns:
            SkillResult if a skill matched and executed, None if no skill matched.
        """
        # 1. Try to match message to a skill
        match = await self.matcher.match(message.content)
        if not match:
            logger.debug(f"No skill matched for message: {message.content[:50]}...")
            return None

        logger.info(f"Skill matched: {match.skill.name} ({match.match_type}, confidence={match.confidence})")

        # 2. Execute the matched skill
        result = await self.executor.execute(
            skill=match.skill,
            message=message,
            user=user,
            parameters=match.parameters,
        )

        return result
