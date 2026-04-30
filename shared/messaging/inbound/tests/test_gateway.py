# shared/messaging/inbound/tests/test_gateway.py
"""
Tests for UnifiedGateway - 统一网关测试
"""
from datetime import UTC, datetime
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.messaging.inbound import (
    ActionResponse,
    AgentResponse,
    BasePlatformAdapter,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedGateway,
    UnifiedMessage,
)


class MockAdapter(BasePlatformAdapter):
    """Mock adapter for testing"""

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
        return f"{platform_user_id}@example.com"

    async def get_user_name(self, platform_user_id: str) -> Optional[str]:
        return f"User {platform_user_id}"


class MockUserService:
    """Mock UserService for testing"""

    def __init__(self):
        self.resolved_users: dict[str, MagicMock] = {}

    def set_adapters(self, adapters):
        pass

    async def resolve_user(self, platform: Platform, platform_user_id: str):
        if platform_user_id not in self.resolved_users:
            user = MagicMock()
            user.id = f"user_{platform_user_id}"
            user.name = f"User {platform_user_id}"
            self.resolved_users[platform_user_id] = user
        return self.resolved_users[platform_user_id]


class TestUnifiedGatewayInit:
    """Test UnifiedGateway initialization"""

    def test_init_minimal(self):
        """Can initialize with minimal params"""
        user_service = MockUserService()
        gateway = UnifiedGateway(user_service=user_service)

        assert gateway.user_service == user_service
        assert gateway.adapters == {}

    def test_init_with_adapters(self):
        """Can initialize with adapters"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
        )

        assert Platform.FEISHU in gateway.adapters
        assert gateway.adapters[Platform.FEISHU] == adapter

    def test_register_adapter(self):
        """Can register adapter after init"""
        user_service = MockUserService()
        gateway = UnifiedGateway(user_service=user_service)
        adapter = MockAdapter(Platform.WECOM)

        gateway.register_adapter(adapter)

        assert Platform.WECOM in gateway.adapters


class TestUnifiedGatewayMessageHandling:
    """Test message handling"""

    @pytest.mark.asyncio
    async def test_handle_message_success(self):
        """handle_message processes valid message"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        handler = AsyncMock(return_value=AgentResponse(text="Hello!"))

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
            message_handler=handler,
        )

        raw_event = {
            "message_id": "msg_123",
            "chat_id": "chat_456",
            "sender_id": "user_789",
            "content": "Test message",
        }

        await gateway.handle_message(Platform.FEISHU, raw_event)

        # Verify handler was called
        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert isinstance(call_args, UnifiedMessage)
        assert call_args.message_id == "msg_123"
        assert call_args.user_id == "user_user_789"

        # Verify response was sent
        assert len(adapter.sent_texts) == 1
        assert adapter.sent_texts[0] == ("chat_456", "Hello!")

    @pytest.mark.asyncio
    async def test_handle_message_unknown_platform(self):
        """handle_message ignores unknown platform"""
        user_service = MockUserService()
        handler = AsyncMock()

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={},
            message_handler=handler,
        )

        await gateway.handle_message(Platform.FEISHU, {"message_id": "msg_123"})

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_invalid_event(self):
        """handle_message ignores invalid event"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        handler = AsyncMock()

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
            message_handler=handler,
        )

        await gateway.handle_message(Platform.FEISHU, {"invalid": "data"})

        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_no_handler(self):
        """handle_message does nothing without handler"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
        )

        # Should not raise
        await gateway.handle_message(Platform.FEISHU, {"message_id": "msg_123"})

    @pytest.mark.asyncio
    async def test_handle_message_card_response(self):
        """handle_message sends card response"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        card = UnifiedCard(title="Response Card", content="Success!")
        handler = AsyncMock(return_value=AgentResponse(card=card))

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
            message_handler=handler,
        )

        await gateway.handle_message(
            Platform.FEISHU,
            {"message_id": "msg_123", "chat_id": "chat_456", "sender_id": "user_1"},
        )

        assert len(adapter.sent_cards) == 1
        assert adapter.sent_cards[0][0] == "chat_456"
        assert adapter.sent_cards[0][1].title == "Response Card"


class TestUnifiedGatewayActionHandling:
    """Test action/callback handling"""

    @pytest.mark.asyncio
    async def test_handle_action_success(self):
        """handle_action processes valid action"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        handler = AsyncMock(return_value=ActionResponse(toast="Success!"))

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
            action_handler=handler,
        )

        raw_callback = {
            "action_id": "confirm",
            "message_id": "msg_123",
            "operator_id": "user_456",
            "value": {"req_id": "req_789"},
        }

        result = await gateway.handle_action(Platform.FEISHU, raw_callback)

        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert isinstance(call_args, UnifiedAction)
        assert call_args.action_id == "confirm"
        assert call_args.user_id == "user_user_456"

        assert result is not None
        assert result["toast"]["content"] == "Success!"

    @pytest.mark.asyncio
    async def test_handle_action_with_card_update(self):
        """handle_action updates card when requested"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)
        updated_card = UnifiedCard(title="Updated", content="Done!")
        handler = AsyncMock(return_value=ActionResponse(
            update_card=True,
            card=updated_card,
            toast="Updated!",
        ))

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
            action_handler=handler,
        )

        raw_callback = {
            "action_id": "confirm",
            "message_id": "msg_123",
            "operator_id": "user_456",
        }

        result = await gateway.handle_action(Platform.FEISHU, raw_callback)

        assert len(adapter.updated_cards) == 1
        assert adapter.updated_cards[0][0] == "msg_123"
        assert result["toast"]["content"] == "Updated!"

    @pytest.mark.asyncio
    async def test_handle_action_unknown_platform(self):
        """handle_action returns None for unknown platform"""
        user_service = MockUserService()
        handler = AsyncMock()

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={},
            action_handler=handler,
        )

        result = await gateway.handle_action(
            Platform.FEISHU,
            {"action_id": "confirm"},
        )

        assert result is None
        handler.assert_not_called()


class TestUnifiedGatewayDirectSend:
    """Test direct send methods"""

    @pytest.mark.asyncio
    async def test_send_card(self):
        """send_card sends card to platform"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
        )

        card = UnifiedCard(title="Direct Card", content="Content")
        message_id = await gateway.send_card(Platform.FEISHU, "chat_123", card)

        assert message_id == "msg_1"
        assert len(adapter.sent_cards) == 1
        assert adapter.sent_cards[0][0] == "chat_123"

    @pytest.mark.asyncio
    async def test_send_text(self):
        """send_text sends text to platform"""
        user_service = MockUserService()
        adapter = MockAdapter(Platform.FEISHU)

        gateway = UnifiedGateway(
            user_service=user_service,
            adapters={Platform.FEISHU: adapter},
        )

        message_id = await gateway.send_text(Platform.FEISHU, "chat_123", "Hello!")

        assert message_id == "msg_1"
        assert len(adapter.sent_texts) == 1
        assert adapter.sent_texts[0] == ("chat_123", "Hello!")

    @pytest.mark.asyncio
    async def test_send_card_unknown_platform(self):
        """send_card returns None for unknown platform"""
        user_service = MockUserService()

        gateway = UnifiedGateway(user_service=user_service, adapters={})

        card = UnifiedCard(title="Test", content="Content")
        result = await gateway.send_card(Platform.FEISHU, "chat_123", card)

        assert result is None

    @pytest.mark.asyncio
    async def test_send_text_unknown_platform(self):
        """send_text returns None for unknown platform"""
        user_service = MockUserService()

        gateway = UnifiedGateway(user_service=user_service, adapters={})

        result = await gateway.send_text(Platform.FEISHU, "chat_123", "Hello!")

        assert result is None


class TestUnifiedGatewayHandlerSetup:
    """Test handler setup methods"""

    def test_set_message_handler(self):
        """set_message_handler sets the handler"""
        user_service = MockUserService()
        gateway = UnifiedGateway(user_service=user_service)

        handler = AsyncMock()
        gateway.set_message_handler(handler)

        assert gateway._message_handler == handler

    def test_set_action_handler(self):
        """set_action_handler sets the handler"""
        user_service = MockUserService()
        gateway = UnifiedGateway(user_service=user_service)

        handler = AsyncMock()
        gateway.set_action_handler(handler)

        assert gateway._action_handler == handler
