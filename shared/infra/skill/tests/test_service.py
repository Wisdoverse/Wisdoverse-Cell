# shared/services/skill/tests/test_service.py
"""
Tests for SkillService - unified interface for skill system.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.base import BaseSkill
from shared.infra.skill.executor import SkillExecutor
from shared.infra.skill.matcher import SkillMatcher
from shared.infra.skill.models import (
    SkillContext,
    SkillMatch,
    SkillResult,
)
from shared.infra.skill.registry import SkillRegistry
from shared.infra.skill.service import SkillService
from shared.messaging.inbound.models import (
    AgentResponse,
    Platform,
    UnifiedMessage,
)


class HelpSkill(BaseSkill):
    """Help skill for testing."""

    name = "help"
    description = "Show available skills"
    commands = ["/help"]
    patterns = [r"有什么技能"]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(
            success=True,
            response=AgentResponse(text="Available skills: help"),
        )


class ExportPrdSkill(BaseSkill):
    """PRD export skill for testing."""

    name = "export_prd"
    description = "Export PRD document"
    commands = ["/prd"]
    patterns = []

    async def execute(self, context: SkillContext) -> SkillResult:
        req_id = context.parameters.get("req_id", "unknown")
        return SkillResult(
            success=True,
            response=AgentResponse(text=f"Exported PRD for {req_id}"),
        )


def create_test_message(content: str = "Test message") -> UnifiedMessage:
    """Create a test message."""
    return UnifiedMessage(
        platform=Platform.FEISHU,
        message_id="msg_123",
        chat_id="chat_456",
        sender_id="sender_789",
        content=content,
        timestamp=datetime.now(UTC),
    )


def create_test_user() -> MagicMock:
    """Create a mock user."""
    user = MagicMock()
    user.id = "user_abc"
    user.name = "Test User"
    return user


@pytest.fixture
def mock_gateway() -> AsyncMock:
    """Create a mock gateway."""
    gateway = AsyncMock()
    gateway.send_text.return_value = "msg_sent_1"
    gateway.send_card.return_value = "msg_card_1"
    return gateway


@pytest.fixture
def registry() -> SkillRegistry:
    """Create a registry with test skills."""
    registry = SkillRegistry()
    registry.register(HelpSkill())
    registry.register(ExportPrdSkill())
    return registry


@pytest.fixture
def matcher(registry: SkillRegistry) -> SkillMatcher:
    """Create a matcher with the test registry."""
    return SkillMatcher(registry=registry)


@pytest.fixture
def executor(mock_gateway: AsyncMock) -> SkillExecutor:
    """Create an executor with mock gateway."""
    return SkillExecutor(gateway=mock_gateway)


@pytest.fixture
def service(
    registry: SkillRegistry,
    matcher: SkillMatcher,
    executor: SkillExecutor,
) -> SkillService:
    """Create a skill service with all components."""
    return SkillService(
        registry=registry,
        matcher=matcher,
        executor=executor,
    )


class TestTryHandle:
    """Test try_handle() method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self, service: SkillService):
        """try_handle() returns None when no skill matches."""
        message = create_test_message("random message without match")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_result_when_skill_matches(self, service: SkillService):
        """try_handle() returns result when skill matches."""
        message = create_test_message("/help")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is not None
        assert result.success is True
        assert result.response.text == "Available skills: help"

    @pytest.mark.asyncio
    async def test_handles_pattern_match(self, service: SkillService):
        """try_handle() handles pattern-matched skills."""
        message = create_test_message("有什么技能可以用")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_passes_parameters_from_match(
        self, registry: SkillRegistry, mock_gateway: AsyncMock
    ):
        """try_handle() passes parameters from matcher to executor."""
        # Create a matcher that returns a match with parameters
        mock_matcher = AsyncMock(spec=SkillMatcher)
        skill = ExportPrdSkill()
        mock_matcher.match.return_value = SkillMatch(
            skill=skill,
            confidence=1.0,
            parameters={"req_id": "REQ123"},
            match_type="command",
        )

        executor = SkillExecutor(gateway=mock_gateway)
        service = SkillService(
            registry=registry,
            matcher=mock_matcher,
            executor=executor,
        )

        message = create_test_message("/prd REQ123")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is not None
        assert result.response.text == "Exported PRD for REQ123"


class TestIntegrationFlow:
    """Test full integration flow: match -> execute -> result."""

    @pytest.mark.asyncio
    async def test_command_flow(self, service: SkillService, mock_gateway: AsyncMock):
        """Full flow: command -> match -> execute -> response."""
        message = create_test_message("/help")
        user = create_test_user()

        result = await service.try_handle(message, user)

        # Verify result
        assert result is not None
        assert result.success is True
        assert result.response.text == "Available skills: help"

        # Verify gateway was called to send response
        mock_gateway.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_pattern_flow(self, service: SkillService, mock_gateway: AsyncMock):
        """Full flow: pattern -> match -> execute -> response."""
        message = create_test_message("有什么技能")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_match_flow(self, service: SkillService, mock_gateway: AsyncMock):
        """No match means gateway should not be called."""
        message = create_test_message("unrelated message")
        user = create_test_user()

        result = await service.try_handle(message, user)

        assert result is None
        mock_gateway.send_text.assert_not_called()
        mock_gateway.send_card.assert_not_called()


class TestServiceComponents:
    """Test service components are properly wired."""

    def test_service_has_registry(self, service: SkillService, registry: SkillRegistry):
        """Service has access to registry."""
        assert service.registry is registry

    def test_service_has_matcher(self, service: SkillService, matcher: SkillMatcher):
        """Service has access to matcher."""
        assert service.matcher is matcher

    def test_service_has_executor(self, service: SkillService, executor: SkillExecutor):
        """Service has access to executor."""
        assert service.executor is executor

    @pytest.mark.asyncio
    async def test_service_uses_matcher(
        self, registry: SkillRegistry, executor: SkillExecutor
    ):
        """Service uses matcher to find skills."""
        mock_matcher = AsyncMock(spec=SkillMatcher)
        mock_matcher.match.return_value = None

        service = SkillService(
            registry=registry,
            matcher=mock_matcher,
            executor=executor,
        )

        message = create_test_message("test")
        user = create_test_user()

        await service.try_handle(message, user)

        mock_matcher.match.assert_called_once_with("test")

    @pytest.mark.asyncio
    async def test_service_uses_executor_when_matched(
        self, registry: SkillRegistry, mock_gateway: AsyncMock
    ):
        """Service uses executor when skill matches."""
        skill = HelpSkill()

        mock_matcher = AsyncMock(spec=SkillMatcher)
        mock_matcher.match.return_value = SkillMatch(
            skill=skill,
            confidence=1.0,
            parameters={},
            match_type="command",
        )

        mock_executor = AsyncMock(spec=SkillExecutor)
        mock_executor.execute.return_value = SkillResult(success=True)

        service = SkillService(
            registry=registry,
            matcher=mock_matcher,
            executor=mock_executor,
        )

        message = create_test_message("/help")
        user = create_test_user()

        await service.try_handle(message, user)

        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args
        assert call_args[1]["skill"] is skill
        assert call_args[1]["message"] is message
        assert call_args[1]["user"] is user
        assert call_args[1]["parameters"] == {}
