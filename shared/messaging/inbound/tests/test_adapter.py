"""
Tests for BasePlatformAdapter

Tests:
1. BasePlatformAdapter cannot be instantiated directly
2. Mock implementation works correctly
3. All abstract methods must be implemented
"""

from datetime import UTC, datetime
from typing import Optional

import pytest

from shared.messaging.inbound import (
    BasePlatformAdapter,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)


class TestBasePlatformAdapterAbstract:
    """Test that BasePlatformAdapter is properly abstract"""

    def test_cannot_instantiate_directly(self):
        """BasePlatformAdapter cannot be instantiated directly"""
        with pytest.raises(TypeError) as exc_info:
            BasePlatformAdapter()  # type: ignore
        assert "abstract" in str(exc_info.value).lower()

    def test_partial_implementation_fails(self):
        """Class with only some methods implemented cannot be instantiated"""

        class PartialAdapter(BasePlatformAdapter):
            @property
            def platform(self) -> Platform:
                return Platform.FEISHU

            # Missing all other abstract methods

        with pytest.raises(TypeError) as exc_info:
            PartialAdapter()  # type: ignore
        assert "abstract" in str(exc_info.value).lower()

    def test_missing_platform_property_fails(self):
        """Class missing platform property cannot be instantiated"""

        class NoPlatformAdapter(BasePlatformAdapter):
            # Missing platform property

            async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
                return None

            async def parse_action(
                self, raw_callback: dict
            ) -> Optional[UnifiedAction]:
                return None

            async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
                return ""

            async def send_text(self, chat_id: str, text: str) -> str:
                return ""

            async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
                return False

            async def get_user_email(self, platform_user_id: str) -> Optional[str]:
                return None

            async def get_user_name(self, platform_user_id: str) -> Optional[str]:
                return None

        with pytest.raises(TypeError) as exc_info:
            NoPlatformAdapter()  # type: ignore
        assert "abstract" in str(exc_info.value).lower()


class MockPlatformAdapter(BasePlatformAdapter):
    """Mock implementation for testing"""

    def __init__(self, platform_type: Platform = Platform.FEISHU):
        self._platform = platform_type
        self.sent_cards: list[tuple[str, UnifiedCard]] = []
        self.sent_texts: list[tuple[str, str]] = []
        self.updated_cards: list[tuple[str, UnifiedCard]] = []

    @property
    def platform(self) -> Platform:
        return self._platform

    async def parse_message(self, raw_event: dict) -> Optional[UnifiedMessage]:
        if "message_id" not in raw_event:
            return None
        return UnifiedMessage(
            platform=self._platform,
            message_id=raw_event["message_id"],
            chat_id=raw_event.get("chat_id", "test_chat"),
            sender_id=raw_event.get("sender_id", "test_sender"),
            content=raw_event.get("content", ""),
            timestamp=datetime.now(UTC),
        )

    async def parse_action(self, raw_callback: dict) -> Optional[UnifiedAction]:
        if "action_id" not in raw_callback:
            return None
        return UnifiedAction(
            platform=self._platform,
            action_id=raw_callback["action_id"],
            message_id=raw_callback.get("message_id", "test_msg"),
            operator_id=raw_callback.get("operator_id", "test_operator"),
            value=raw_callback.get("value", {}),
        )

    async def send_card(self, chat_id: str, card: UnifiedCard) -> str:
        self.sent_cards.append((chat_id, card))
        return f"msg_{len(self.sent_cards)}"

    async def send_text(self, chat_id: str, text: str) -> str:
        self.sent_texts.append((chat_id, text))
        return f"msg_{len(self.sent_texts)}"

    async def update_card(self, message_id: str, card: UnifiedCard) -> bool:
        self.updated_cards.append((message_id, card))
        return True

    async def get_user_email(self, platform_user_id: str) -> Optional[str]:
        if platform_user_id == "unknown":
            return None
        return f"{platform_user_id}@example.com"

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        if platform_user_id == "unknown":
            return None
        return f"User {platform_user_id}"


class TestMockPlatformAdapter:
    """Test that a complete implementation works correctly"""

    def test_can_instantiate_complete_implementation(self):
        """Complete implementation can be instantiated"""
        adapter = MockPlatformAdapter()
        assert adapter is not None
        assert adapter.platform == Platform.FEISHU

    def test_platform_property(self):
        """Platform property returns correct value"""
        feishu_adapter = MockPlatformAdapter(Platform.FEISHU)
        wecom_adapter = MockPlatformAdapter(Platform.WECOM)
        web_adapter = MockPlatformAdapter(Platform.WEB)

        assert feishu_adapter.platform == Platform.FEISHU
        assert wecom_adapter.platform == Platform.WECOM
        assert web_adapter.platform == Platform.WEB

    @pytest.mark.asyncio
    async def test_parse_message_success(self):
        """parse_message returns UnifiedMessage for valid input"""
        adapter = MockPlatformAdapter()
        raw_event = {
            "message_id": "msg_123",
            "chat_id": "chat_456",
            "sender_id": "user_789",
            "content": "Hello, world!",
        }

        result = await adapter.parse_message(raw_event)

        assert result is not None
        assert isinstance(result, UnifiedMessage)
        assert result.message_id == "msg_123"
        assert result.chat_id == "chat_456"
        assert result.sender_id == "user_789"
        assert result.content == "Hello, world!"
        assert result.platform == Platform.FEISHU

    @pytest.mark.asyncio
    async def test_parse_message_returns_none_for_invalid(self):
        """parse_message returns None for invalid input"""
        adapter = MockPlatformAdapter()
        raw_event = {"invalid": "data"}

        result = await adapter.parse_message(raw_event)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_action_success(self):
        """parse_action returns UnifiedAction for valid input"""
        adapter = MockPlatformAdapter()
        raw_callback = {
            "action_id": "approve",
            "message_id": "msg_123",
            "operator_id": "user_456",
            "value": {"requirement_id": "req_789"},
        }

        result = await adapter.parse_action(raw_callback)

        assert result is not None
        assert isinstance(result, UnifiedAction)
        assert result.action_id == "approve"
        assert result.message_id == "msg_123"
        assert result.operator_id == "user_456"
        assert result.value == {"requirement_id": "req_789"}

    @pytest.mark.asyncio
    async def test_parse_action_returns_none_for_invalid(self):
        """parse_action returns None for invalid input"""
        adapter = MockPlatformAdapter()
        raw_callback = {"invalid": "data"}

        result = await adapter.parse_action(raw_callback)

        assert result is None

    @pytest.mark.asyncio
    async def test_send_card(self):
        """send_card sends card and returns message ID"""
        adapter = MockPlatformAdapter()
        card = UnifiedCard(title="Test Card", content="Test content")

        message_id = await adapter.send_card("chat_123", card)

        assert message_id == "msg_1"
        assert len(adapter.sent_cards) == 1
        assert adapter.sent_cards[0] == ("chat_123", card)

    @pytest.mark.asyncio
    async def test_send_text(self):
        """send_text sends text and returns message ID"""
        adapter = MockPlatformAdapter()

        message_id = await adapter.send_text("chat_123", "Hello!")

        assert message_id == "msg_1"
        assert len(adapter.sent_texts) == 1
        assert adapter.sent_texts[0] == ("chat_123", "Hello!")

    @pytest.mark.asyncio
    async def test_update_card(self):
        """update_card updates card and returns success"""
        adapter = MockPlatformAdapter()
        card = UnifiedCard(title="Updated Card", content="Updated content")

        result = await adapter.update_card("msg_123", card)

        assert result is True
        assert len(adapter.updated_cards) == 1
        assert adapter.updated_cards[0] == ("msg_123", card)

    @pytest.mark.asyncio
    async def test_get_user_email_found(self):
        """get_user_email returns email for known user"""
        adapter = MockPlatformAdapter()

        email = await adapter.get_user_email("john")

        assert email == "john@example.com"

    @pytest.mark.asyncio
    async def test_get_user_email_not_found(self):
        """get_user_email returns None for unknown user"""
        adapter = MockPlatformAdapter()

        email = await adapter.get_user_email("unknown")

        assert email is None

    @pytest.mark.asyncio
    async def test_get_user_name_found(self):
        """get_user_name returns name for known user"""
        adapter = MockPlatformAdapter()

        name = await adapter.get_user_name("john")

        assert name == "User john"

    @pytest.mark.asyncio
    async def test_get_user_name_not_found(self):
        """get_user_name returns None for unknown user"""
        adapter = MockPlatformAdapter()

        name = await adapter.get_user_name("unknown")

        assert name is None


class TestAdapterInheritance:
    """Test inheritance and type checking"""

    def test_mock_is_instance_of_base(self):
        """Mock adapter is instance of BasePlatformAdapter"""
        adapter = MockPlatformAdapter()
        assert isinstance(adapter, BasePlatformAdapter)

    def test_mock_is_subclass_of_base(self):
        """MockPlatformAdapter is subclass of BasePlatformAdapter"""
        assert issubclass(MockPlatformAdapter, BasePlatformAdapter)
