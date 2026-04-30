# shared/services/skill/tests/test_models.py
"""
Tests for skill system models - Permission, SkillContext, SkillResult, SkillError.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.infra.skill.models import (
    Permission,
    SkillContext,
    SkillError,
    SkillMatch,
    SkillResult,
)
from shared.messaging.inbound.models import (
    AgentResponse,
    Platform,
    UnifiedCard,
    UnifiedMessage,
)


class TestPermission:
    """Test Permission enum values."""

    def test_permission_values(self):
        """Permission enum contains expected values."""
        assert Permission.DB_READ == "db:read"
        assert Permission.DB_WRITE == "db:write"
        assert Permission.GATEWAY_REPLY == "gateway:reply"
        assert Permission.GATEWAY_SEND == "gateway:send"
        assert Permission.EVENT_PUBLISH == "event:publish"
        assert Permission.REDIS_READ == "redis:read"
        assert Permission.REDIS_WRITE == "redis:write"

    def test_permission_is_string_enum(self):
        """Permission values can be used as strings."""
        # Permission is a str subclass, so .value returns the string
        assert Permission.DB_READ.value == "db:read"
        assert Permission.GATEWAY_REPLY.value == "gateway:reply"
        # Can compare directly with strings due to str inheritance
        assert Permission.DB_READ == "db:read"

    def test_permission_comparison(self):
        """Permission can be compared with strings."""
        assert Permission.DB_READ == "db:read"
        assert Permission.DB_READ in ["db:read", "db:write"]


class TestSkillContext:
    """Test SkillContext creation and methods."""

    def _create_test_message(self) -> UnifiedMessage:
        """Create a test message."""
        return UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_123",
            chat_id="chat_456",
            sender_id="sender_789",
            content="Test message",
            timestamp=datetime.now(UTC),
        )

    def _create_test_user(self) -> MagicMock:
        """Create a mock user."""
        user = MagicMock()
        user.id = "user_abc"
        user.name = "Test User"
        user.email = "test@example.com"
        return user

    def test_context_creation_minimal(self):
        """SkillContext can be created with minimal params."""
        message = self._create_test_message()
        user = self._create_test_user()
        parameters = {"req_id": "REQ123"}

        context = SkillContext(
            message=message,
            user=user,
            parameters=parameters,
        )

        assert context.message == message
        assert context.user == user
        assert context.parameters == parameters
        assert context.db is None
        assert context.redis is None
        assert context.gateway is None
        assert context.event_bus is None

    def test_context_creation_with_resources(self):
        """SkillContext can be created with all resources."""
        message = self._create_test_message()
        user = self._create_test_user()
        parameters = {}
        mock_db = MagicMock()
        mock_redis = MagicMock()
        mock_gateway = MagicMock()
        mock_event_bus = MagicMock()

        context = SkillContext(
            message=message,
            user=user,
            parameters=parameters,
            db=mock_db,
            redis=mock_redis,
            gateway=mock_gateway,
            event_bus=mock_event_bus,
        )

        assert context.db == mock_db
        assert context.redis == mock_redis
        assert context.gateway == mock_gateway
        assert context.event_bus == mock_event_bus

    @pytest.mark.asyncio
    async def test_reply_text_with_gateway(self):
        """reply_text sends text via gateway."""
        message = self._create_test_message()
        user = self._create_test_user()
        mock_gateway = AsyncMock()
        mock_gateway.send_text.return_value = "msg_sent_1"

        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            gateway=mock_gateway,
        )

        result = await context.reply_text("Hello!")

        assert result == "msg_sent_1"
        mock_gateway.send_text.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            text="Hello!",
        )

    @pytest.mark.asyncio
    async def test_reply_text_without_gateway(self):
        """reply_text returns None when gateway is not available."""
        message = self._create_test_message()
        user = self._create_test_user()

        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            gateway=None,
        )

        result = await context.reply_text("Hello!")

        assert result is None

    @pytest.mark.asyncio
    async def test_reply_card_with_gateway(self):
        """reply_card sends card via gateway."""
        message = self._create_test_message()
        user = self._create_test_user()
        mock_gateway = AsyncMock()
        mock_gateway.send_card.return_value = "msg_card_1"

        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            gateway=mock_gateway,
        )

        card = UnifiedCard(title="Test Card", content="Card content")
        result = await context.reply_card(card)

        assert result == "msg_card_1"
        mock_gateway.send_card.assert_called_once_with(
            platform=Platform.FEISHU,
            chat_id="chat_456",
            card=card,
        )

    @pytest.mark.asyncio
    async def test_reply_card_without_gateway(self):
        """reply_card returns None when gateway is not available."""
        message = self._create_test_message()
        user = self._create_test_user()

        context = SkillContext(
            message=message,
            user=user,
            parameters={},
            gateway=None,
        )

        card = UnifiedCard(title="Test Card", content="Card content")
        result = await context.reply_card(card)

        assert result is None


class TestSkillMatch:
    """Test SkillMatch model."""

    def test_skill_match_creation(self):
        """SkillMatch can be created with required fields."""
        mock_skill = MagicMock()
        mock_skill.name = "test_skill"

        match = SkillMatch(
            skill=mock_skill,
            confidence=0.95,
            parameters={"req_id": "REQ123"},
            match_type="command",
        )

        assert match.skill == mock_skill
        assert match.confidence == 0.95
        assert match.parameters == {"req_id": "REQ123"}
        assert match.match_type == "command"

    def test_skill_match_default_parameters(self):
        """SkillMatch uses empty dict as default parameters."""
        mock_skill = MagicMock()

        match = SkillMatch(
            skill=mock_skill,
            confidence=1.0,
            match_type="pattern",
        )

        assert match.parameters == {}

    def test_skill_match_confidence_bounds(self):
        """SkillMatch validates confidence is between 0 and 1."""
        mock_skill = MagicMock()

        # Valid confidence values
        match_low = SkillMatch(skill=mock_skill, confidence=0.0, match_type="llm")
        match_high = SkillMatch(skill=mock_skill, confidence=1.0, match_type="llm")

        assert match_low.confidence == 0.0
        assert match_high.confidence == 1.0

    def test_skill_match_type_options(self):
        """SkillMatch supports command, pattern, and llm match types."""
        mock_skill = MagicMock()

        for match_type in ["command", "pattern", "llm"]:
            match = SkillMatch(
                skill=mock_skill,
                confidence=0.8,
                match_type=match_type,
            )
            assert match.match_type == match_type


class TestSkillResult:
    """Test SkillResult model."""

    def test_skill_result_success(self):
        """SkillResult can represent success with response."""
        response = AgentResponse(text="Operation completed!")

        result = SkillResult(
            success=True,
            response=response,
        )

        assert result.success is True
        assert result.response == response
        assert result.error is None
        assert result.follow_up is None

    def test_skill_result_failure(self):
        """SkillResult can represent failure with error."""
        result = SkillResult(
            success=False,
            error="Something went wrong",
        )

        assert result.success is False
        assert result.response is None
        assert result.error == "Something went wrong"

    def test_skill_result_with_follow_up(self):
        """SkillResult can include follow-up prompt."""
        result = SkillResult(
            success=True,
            follow_up="Would you like to do something else?",
        )

        assert result.success is True
        assert result.follow_up == "Would you like to do something else?"

    def test_skill_result_with_card_response(self):
        """SkillResult can include card response."""
        card = UnifiedCard(title="Result", content="Here are the results")
        response = AgentResponse(card=card)

        result = SkillResult(
            success=True,
            response=response,
        )

        assert result.response.card == card
        assert result.response.text is None


class TestSkillError:
    """Test SkillError exception."""

    def test_skill_error_creation(self):
        """SkillError can be created with message."""
        error = SkillError("Invalid request ID")

        assert error.message == "Invalid request ID"
        assert error.recoverable is True  # default

    def test_skill_error_non_recoverable(self):
        """SkillError can be marked as non-recoverable."""
        error = SkillError("System failure", recoverable=False)

        assert error.message == "System failure"
        assert error.recoverable is False

    def test_skill_error_str(self):
        """SkillError __str__ returns message."""
        error = SkillError("Test error message")

        assert str(error) == "Test error message"

    def test_skill_error_repr(self):
        """SkillError __repr__ includes all info."""
        error = SkillError("Test error", recoverable=False)

        repr_str = repr(error)
        assert "SkillError" in repr_str
        assert "Test error" in repr_str
        assert "recoverable=False" in repr_str

    def test_skill_error_is_exception(self):
        """SkillError is an Exception and can be raised/caught."""
        with pytest.raises(SkillError) as exc_info:
            raise SkillError("Test exception")

        assert exc_info.value.message == "Test exception"

    def test_skill_error_in_try_except(self):
        """SkillError can be caught as Exception."""

        def raise_skill_error():
            raise SkillError("Business error")

        caught = False
        try:
            raise_skill_error()
        except Exception as e:
            caught = True
            assert isinstance(e, SkillError)
            assert e.message == "Business error"

        assert caught is True
