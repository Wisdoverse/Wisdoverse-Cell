# shared/services/skill/tests/test_executor.py
"""
Tests for SkillExecutor - context building, execution, and error handling.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.base import BaseSkill
from shared.infra.skill.executor import SkillExecutor
from shared.infra.skill.models import (
    Permission,
    SkillContext,
    SkillError,
    SkillResult,
)
from shared.messaging.inbound.models import (
    AgentResponse,
    Platform,
    UnifiedCard,
    UnifiedMessage,
)


class MockSkill(BaseSkill):
    """Mock skill for testing."""

    name = "mock_skill"
    description = "A mock skill"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class SkillWithDBAccess(BaseSkill):
    """Skill requiring DB read access."""

    name = "db_skill"
    description = "Skill with DB access"
    permissions = [Permission.GATEWAY_REPLY, Permission.DB_READ]

    async def execute(self, context: SkillContext) -> SkillResult:
        # Check that DB is injected
        if context.db is None:
            raise SkillError("DB not available")
        return SkillResult(success=True)


class SkillWithDBWrite(BaseSkill):
    """Skill requiring DB write access."""

    name = "db_write_skill"
    description = "Skill with DB write access"
    permissions = [Permission.GATEWAY_REPLY, Permission.DB_WRITE]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class SkillWithRedis(BaseSkill):
    """Skill requiring Redis access."""

    name = "redis_skill"
    description = "Skill with Redis access"
    permissions = [Permission.GATEWAY_REPLY, Permission.REDIS_READ]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class SkillWithEventBus(BaseSkill):
    """Skill requiring event bus access."""

    name = "event_skill"
    description = "Skill with event bus access"
    permissions = [Permission.GATEWAY_REPLY, Permission.EVENT_PUBLISH]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class SkillWithGatewaySend(BaseSkill):
    """Skill requiring gateway send access."""

    name = "gateway_send_skill"
    description = "Skill with gateway send access"
    permissions = [Permission.GATEWAY_SEND]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(success=True)


class SkillRaisesSkillError(BaseSkill):
    """Skill that raises SkillError."""

    name = "error_skill"
    description = "Skill that raises error"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        raise SkillError("Something went wrong", recoverable=True)


class SkillRaisesException(BaseSkill):
    """Skill that raises unexpected exception."""

    name = "exception_skill"
    description = "Skill that raises exception"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        raise RuntimeError("Unexpected error")


class SkillWithTextResponse(BaseSkill):
    """Skill that returns text response."""

    name = "text_response_skill"
    description = "Returns text response"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(
            success=True,
            response=AgentResponse(text="Hello from skill!"),
        )


class SkillWithCardResponse(BaseSkill):
    """Skill that returns card response."""

    name = "card_response_skill"
    description = "Returns card response"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        card = UnifiedCard(title="Result", content="Here are the results")
        return SkillResult(
            success=True,
            response=AgentResponse(card=card),
        )


class SkillWithFollowUp(BaseSkill):
    """Skill that returns follow-up."""

    name = "followup_skill"
    description = "Returns follow-up"
    permissions = [Permission.GATEWAY_REPLY]

    async def execute(self, context: SkillContext) -> SkillResult:
        return SkillResult(
            success=True,
            follow_up="What would you like to do next?",
        )


def create_test_message() -> UnifiedMessage:
    """Create a test message."""
    return UnifiedMessage(
        platform=Platform.FEISHU,
        message_id="msg_123",
        chat_id="chat_456",
        sender_id="sender_789",
        content="Test message",
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
def executor(mock_gateway: AsyncMock) -> SkillExecutor:
    """Create an executor with mock gateway."""
    return SkillExecutor(gateway=mock_gateway)


class TestSkillExecution:
    """Test basic skill execution."""

    @pytest.mark.asyncio
    async def test_execute_calls_skill(self, executor: SkillExecutor):
        """execute() calls skill.execute with context."""
        skill = MockSkill()
        message = create_test_message()
        user = create_test_user()
        parameters = {"key": "value"}

        result = await executor.execute(skill, message, user, parameters)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_passes_parameters(self, executor: SkillExecutor):
        """execute() passes parameters to context."""
        skill = MagicMock(spec=BaseSkill)
        skill.name = "test"
        skill.permissions = [Permission.GATEWAY_REPLY]
        skill.execute = AsyncMock(return_value=SkillResult(success=True))

        message = create_test_message()
        user = create_test_user()
        parameters = {"req_id": "REQ123", "format": "pdf"}

        await executor.execute(skill, message, user, parameters)

        # Check that execute was called with a context containing the parameters
        call_args = skill.execute.call_args[0][0]
        assert isinstance(call_args, SkillContext)
        assert call_args.parameters == parameters


class TestPermissionBasedInjection:
    """Test permission-based resource injection."""

    @pytest.mark.asyncio
    async def test_db_read_injects_db(self, mock_gateway: AsyncMock):
        """DB_READ permission injects db session."""
        mock_db_factory = MagicMock(return_value=MagicMock())
        executor = SkillExecutor(
            gateway=mock_gateway,
            db_session_factory=mock_db_factory,
        )
        skill = SkillWithDBAccess()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is True
        mock_db_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_write_injects_db(self, mock_gateway: AsyncMock):
        """DB_WRITE permission injects db session."""
        mock_db_factory = MagicMock(return_value=MagicMock())
        executor = SkillExecutor(
            gateway=mock_gateway,
            db_session_factory=mock_db_factory,
        )
        skill = SkillWithDBWrite()
        message = create_test_message()
        user = create_test_user()

        await executor.execute(skill, message, user, {})

        mock_db_factory.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_permission_injects_redis(self, mock_gateway: AsyncMock):
        """REDIS_READ permission injects redis client."""
        mock_redis = MagicMock()
        executor = SkillExecutor(
            gateway=mock_gateway,
            redis=mock_redis,
        )

        # Create skill that checks redis
        class CheckRedisSkill(BaseSkill):
            name = "check_redis"
            description = "Checks redis injection"
            permissions = [Permission.REDIS_READ]

            async def execute(self, context: SkillContext) -> SkillResult:
                assert context.redis is mock_redis
                return SkillResult(success=True)

        skill = CheckRedisSkill()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_event_publish_injects_event_bus(self, mock_gateway: AsyncMock):
        """EVENT_PUBLISH permission injects event bus."""
        mock_event_bus = MagicMock()
        executor = SkillExecutor(
            gateway=mock_gateway,
            event_bus=mock_event_bus,
        )

        class CheckEventBusSkill(BaseSkill):
            name = "check_event"
            description = "Checks event bus injection"
            permissions = [Permission.EVENT_PUBLISH]

            async def execute(self, context: SkillContext) -> SkillResult:
                assert context.event_bus is mock_event_bus
                return SkillResult(success=True)

        skill = CheckEventBusSkill()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_gateway_always_injected_for_reply(self, executor: SkillExecutor):
        """Gateway is always injected for reply methods."""

        class CheckGatewaySkill(BaseSkill):
            name = "check_gateway"
            description = "Checks gateway injection"
            permissions = [Permission.GATEWAY_REPLY]  # Default permission

            async def execute(self, context: SkillContext) -> SkillResult:
                assert context.gateway is not None
                return SkillResult(success=True)

        skill = CheckGatewaySkill()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_db_without_permission(self, mock_gateway: AsyncMock):
        """DB is not injected without permission."""
        mock_db_factory = MagicMock(return_value=MagicMock())
        executor = SkillExecutor(
            gateway=mock_gateway,
            db_session_factory=mock_db_factory,
        )

        class NoDB(BaseSkill):
            name = "no_db"
            description = "No DB permission"
            permissions = [Permission.GATEWAY_REPLY]

            async def execute(self, context: SkillContext) -> SkillResult:
                assert context.db is None
                return SkillResult(success=True)

        skill = NoDB()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is True
        mock_db_factory.assert_not_called()


class TestErrorHandling:
    """Test error handling in executor."""

    @pytest.mark.asyncio
    async def test_skill_error_sends_user_message(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """SkillError sends user-visible message."""
        skill = SkillRaisesSkillError()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is False
        assert result.error == "Something went wrong"
        mock_gateway.send_text.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            text="⚠️ Something went wrong",
        )

    @pytest.mark.asyncio
    async def test_exception_sends_generic_error(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """Unexpected exception sends generic error message."""
        skill = SkillRaisesException()
        message = create_test_message()
        user = create_test_user()

        result = await executor.execute(skill, message, user, {})

        assert result.success is False
        assert "Unexpected error" in result.error
        mock_gateway.send_text.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            text="系统繁忙，请稍后重试",
        )


class TestResponseHandling:
    """Test response sending via gateway."""

    @pytest.mark.asyncio
    async def test_text_response_sent(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """Text response is sent via gateway."""
        skill = SkillWithTextResponse()
        message = create_test_message()
        user = create_test_user()

        await executor.execute(skill, message, user, {})

        mock_gateway.send_text.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            text="Hello from skill!",
        )

    @pytest.mark.asyncio
    async def test_card_response_sent(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """Card response is sent via gateway."""
        skill = SkillWithCardResponse()
        message = create_test_message()
        user = create_test_user()

        await executor.execute(skill, message, user, {})

        mock_gateway.send_card.assert_called_once()
        call_args = mock_gateway.send_card.call_args
        assert call_args[1]["platform"] == Platform.FEISHU
        assert call_args[1]["chat_id"] == "chat_456"
        assert call_args[1]["card"].title == "Result"

    @pytest.mark.asyncio
    async def test_follow_up_sent(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """Follow-up text is sent via gateway."""
        skill = SkillWithFollowUp()
        message = create_test_message()
        user = create_test_user()

        await executor.execute(skill, message, user, {})

        mock_gateway.send_text.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            text="What would you like to do next?",
        )

    @pytest.mark.asyncio
    async def test_no_response_no_send(
        self, executor: SkillExecutor, mock_gateway: AsyncMock
    ):
        """No response means no gateway call."""
        skill = MockSkill()  # Returns SkillResult(success=True) with no response
        message = create_test_message()
        user = create_test_user()

        await executor.execute(skill, message, user, {})

        mock_gateway.send_text.assert_not_called()
        mock_gateway.send_card.assert_not_called()
