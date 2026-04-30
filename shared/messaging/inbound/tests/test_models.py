"""
Tests for Gateway Models - 跨平台统一消息模型测试
"""
from datetime import UTC, datetime

from shared.messaging.inbound.models import (
    ActionResponse,
    AgentResponse,
    CardAction,
    CardActionStyle,
    MessageType,
    Platform,
    UnifiedAction,
    UnifiedCard,
    UnifiedMessage,
)


class TestEnums:
    """测试枚举类型"""

    def test_platform_values(self):
        """测试 Platform 枚举值"""
        assert Platform.FEISHU.value == "feishu"
        assert Platform.WECOM.value == "wecom"
        assert Platform.WEB.value == "web"

    def test_message_type_values(self):
        """测试 MessageType 枚举值"""
        assert MessageType.TEXT.value == "text"
        assert MessageType.IMAGE.value == "image"
        assert MessageType.FILE.value == "file"
        assert MessageType.POST.value == "post"
        assert MessageType.CARD.value == "card"

    def test_card_action_style_values(self):
        """测试 CardActionStyle 枚举值"""
        assert CardActionStyle.PRIMARY.value == "primary"
        assert CardActionStyle.DANGER.value == "danger"
        assert CardActionStyle.DEFAULT.value == "default"


class TestUnifiedMessage:
    """测试 UnifiedMessage 模型"""

    def test_minimal_instantiation(self):
        """测试最小参数实例化"""
        msg = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_001",
            chat_id="chat_001",
            sender_id="user_001",
            timestamp=datetime.now(UTC),
        )
        assert msg.platform == Platform.FEISHU
        assert msg.message_id == "msg_001"
        assert msg.chat_id == "chat_001"
        assert msg.sender_id == "user_001"

    def test_default_values(self):
        """测试默认值"""
        msg = UnifiedMessage(
            platform=Platform.WECOM,
            message_id="msg_002",
            chat_id="chat_002",
            sender_id="user_002",
            timestamp=datetime.now(UTC),
        )
        assert msg.chat_type == "private"
        assert msg.sender_name == ""
        assert msg.user_id is None
        assert msg.message_type == MessageType.TEXT
        assert msg.content == ""
        assert msg.mentions == []
        assert msg.attachments == []
        assert msg.raw_data == {}

    def test_full_instantiation(self):
        """测试完整参数实例化"""
        now = datetime.now(UTC)
        msg = UnifiedMessage(
            platform=Platform.WEB,
            message_id="msg_003",
            chat_id="chat_003",
            chat_type="group",
            sender_id="user_003",
            sender_name="Test User",
            user_id="unified_user_003",
            message_type=MessageType.POST,
            content="Hello, world!",
            mentions=["user_a", "user_b"],
            attachments=[{"type": "image", "url": "https://example.com/img.png"}],
            timestamp=now,
            raw_data={"original": "data"},
        )
        assert msg.chat_type == "group"
        assert msg.sender_name == "Test User"
        assert msg.user_id == "unified_user_003"
        assert msg.message_type == MessageType.POST
        assert msg.content == "Hello, world!"
        assert len(msg.mentions) == 2
        assert len(msg.attachments) == 1
        assert msg.timestamp == now
        assert msg.raw_data == {"original": "data"}

    def test_serialization(self):
        """测试序列化"""
        msg = UnifiedMessage(
            platform=Platform.FEISHU,
            message_id="msg_004",
            chat_id="chat_004",
            sender_id="user_004",
            timestamp=datetime(2026, 1, 27, 10, 0, 0, tzinfo=UTC),
        )
        json_str = msg.model_dump_json()
        assert '"platform":"feishu"' in json_str
        assert '"message_id":"msg_004"' in json_str

    def test_deserialization(self):
        """测试反序列化"""
        json_data = {
            "platform": "wecom",
            "message_id": "msg_005",
            "chat_id": "chat_005",
            "sender_id": "user_005",
            "timestamp": "2026-01-27T10:00:00Z",
        }
        msg = UnifiedMessage.model_validate(json_data)
        assert msg.platform == Platform.WECOM
        assert msg.message_id == "msg_005"


class TestCardAction:
    """测试 CardAction 模型"""

    def test_minimal_instantiation(self):
        """测试最小参数实例化"""
        action = CardAction(label="Submit", action_id="submit_btn")
        assert action.label == "Submit"
        assert action.action_id == "submit_btn"

    def test_default_values(self):
        """测试默认值"""
        action = CardAction(label="Cancel", action_id="cancel_btn")
        assert action.value == {}
        assert action.style == CardActionStyle.DEFAULT

    def test_full_instantiation(self):
        """测试完整参数实例化"""
        action = CardAction(
            label="Confirm",
            action_id="confirm_btn",
            value={"key": "value"},
            style=CardActionStyle.PRIMARY,
        )
        assert action.value == {"key": "value"}
        assert action.style == CardActionStyle.PRIMARY

    def test_serialization(self):
        """测试序列化"""
        action = CardAction(
            label="Delete",
            action_id="delete_btn",
            style=CardActionStyle.DANGER,
        )
        json_str = action.model_dump_json()
        assert '"label":"Delete"' in json_str
        assert '"style":"danger"' in json_str


class TestUnifiedCard:
    """测试 UnifiedCard 模型"""

    def test_minimal_instantiation(self):
        """测试最小参数实例化"""
        card = UnifiedCard(title="Test Card", content="# Hello")
        assert card.title == "Test Card"
        assert card.content == "# Hello"

    def test_default_values(self):
        """测试默认值"""
        card = UnifiedCard(title="Test", content="Content")
        assert card.status is None
        assert card.status_color is None
        assert card.priority is None
        assert card.fields == []
        assert card.actions == []
        assert card.context == {}

    def test_full_instantiation(self):
        """测试完整参数实例化"""
        action = CardAction(label="Approve", action_id="approve_btn")
        card = UnifiedCard(
            title="Requirement Card",
            content="## Description\n\nThis is a test.",
            status="pending",
            status_color="orange",
            priority="high",
            fields=[{"label": "Category", "value": "Feature"}],
            actions=[action],
            context={"requirement_id": "req_001"},
        )
        assert card.status == "pending"
        assert card.status_color == "orange"
        assert card.priority == "high"
        assert len(card.fields) == 1
        assert len(card.actions) == 1
        assert card.context == {"requirement_id": "req_001"}

    def test_serialization_deserialization(self):
        """测试序列化和反序列化"""
        original = UnifiedCard(
            title="Test",
            content="Content",
            status="active",
            actions=[CardAction(label="Click", action_id="click_btn")],
        )
        json_str = original.model_dump_json()
        restored = UnifiedCard.model_validate_json(json_str)
        assert restored.title == original.title
        assert restored.status == original.status
        assert len(restored.actions) == 1


class TestUnifiedAction:
    """测试 UnifiedAction 模型"""

    def test_minimal_instantiation(self):
        """测试最小参数实例化"""
        action = UnifiedAction(
            platform=Platform.FEISHU,
            action_id="btn_click",
            message_id="msg_001",
            operator_id="user_001",
        )
        assert action.platform == Platform.FEISHU
        assert action.action_id == "btn_click"
        assert action.message_id == "msg_001"
        assert action.operator_id == "user_001"

    def test_default_values(self):
        """测试默认值"""
        action = UnifiedAction(
            platform=Platform.WECOM,
            action_id="action_001",
            message_id="msg_002",
            operator_id="user_002",
        )
        assert action.user_id is None
        assert action.value == {}
        assert action.raw_data == {}

    def test_full_instantiation(self):
        """测试完整参数实例化"""
        action = UnifiedAction(
            platform=Platform.WEB,
            action_id="approve",
            message_id="msg_003",
            operator_id="user_003",
            user_id="unified_user_003",
            value={"approved": True},
            raw_data={"original": "callback"},
        )
        assert action.user_id == "unified_user_003"
        assert action.value == {"approved": True}
        assert action.raw_data == {"original": "callback"}


class TestAgentResponse:
    """测试 AgentResponse 模型"""

    def test_empty_instantiation(self):
        """测试空实例化"""
        response = AgentResponse()
        assert response.text is None
        assert response.card is None
        assert response.update_card is False

    def test_text_response(self):
        """测试文本响应"""
        response = AgentResponse(text="Hello, user!")
        assert response.text == "Hello, user!"
        assert response.card is None

    def test_card_response(self):
        """测试卡片响应"""
        card = UnifiedCard(title="Response", content="Success!")
        response = AgentResponse(card=card, update_card=True)
        assert response.card is not None
        assert response.card.title == "Response"
        assert response.update_card is True

    def test_serialization(self):
        """测试序列化"""
        response = AgentResponse(text="Test")
        json_str = response.model_dump_json()
        assert '"text":"Test"' in json_str


class TestActionResponse:
    """测试 ActionResponse 模型"""

    def test_empty_instantiation(self):
        """测试空实例化"""
        response = ActionResponse()
        assert response.update_card is False
        assert response.card is None
        assert response.toast is None

    def test_toast_response(self):
        """测试 toast 响应"""
        response = ActionResponse(toast="Operation successful!")
        assert response.toast == "Operation successful!"

    def test_card_update_response(self):
        """测试卡片更新响应"""
        card = UnifiedCard(title="Updated", content="New content")
        response = ActionResponse(update_card=True, card=card)
        assert response.update_card is True
        assert response.card is not None
        assert response.card.title == "Updated"

    def test_full_response(self):
        """测试完整响应"""
        card = UnifiedCard(title="Result", content="Done")
        response = ActionResponse(
            update_card=True,
            card=card,
            toast="Saved successfully!",
        )
        assert response.update_card is True
        assert response.card.title == "Result"
        assert response.toast == "Saved successfully!"
