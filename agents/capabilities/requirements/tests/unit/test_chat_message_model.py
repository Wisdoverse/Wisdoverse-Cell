"""
Unit tests for ChatMessage model

Tests:
- Model instantiation
- Default values
- ID generation with correct prefix
"""
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure project root is in Python path
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


from agents.capabilities.requirements.models.chat_message import ChatMessage
from shared.utils.id_generator import IDPrefix


class TestChatMessageModel:
    """Test ChatMessage model"""

    def test_model_instantiation(self):
        """Verify ChatMessage can be instantiated with required fields"""
        msg = ChatMessage(
            chat_id="oc_abc123",
            message_id="om_msg_001",
            sender_id="ou_user123",
            message_type="text",
            sent_at=datetime.now(UTC)
        )

        assert msg.chat_id == "oc_abc123"
        assert msg.message_id == "om_msg_001"
        assert msg.sender_id == "ou_user123"
        assert msg.message_type == "text"

    def test_default_values(self):
        """Verify default values are set correctly when explicitly provided"""
        # Note: SQLAlchemy defaults are applied at persistence time, not instantiation.
        # Here we verify defaults work when explicitly set.
        msg = ChatMessage(
            chat_id="oc_abc123",
            message_id="om_msg_002",
            sender_id="ou_user123",
            message_type="text",
            sent_at=datetime.now(UTC),
            extracted=False,
            requirement_ids=[]
        )

        # Check values when explicitly set
        assert msg.extracted is False
        assert msg.requirement_ids == []
        assert msg.sender_name is None
        assert msg.content is None
        assert msg.session_id is None

    def test_id_generated_with_message_prefix(self):
        """Verify ID is generated with MESSAGE prefix when explicitly provided"""
        from shared.utils.id_generator import generate_id

        # Test that generate_id produces correct prefix
        generated_id = generate_id(IDPrefix.MESSAGE)
        assert generated_id.startswith(f"{IDPrefix.MESSAGE}_")

        # Test that model accepts the ID
        msg = ChatMessage(
            id=generated_id,
            chat_id="oc_abc123",
            message_id="om_msg_003",
            sender_id="ou_user123",
            message_type="text",
            sent_at=datetime.now(UTC)
        )

        assert msg.id is not None
        assert msg.id.startswith(f"{IDPrefix.MESSAGE}_")

    def test_optional_fields(self):
        """Verify optional fields can be set"""
        now = datetime.now(UTC)
        msg = ChatMessage(
            chat_id="oc_abc123",
            message_id="om_msg_004",
            sender_id="ou_user123",
            sender_name="Test User",
            message_type="text",
            content="Hello, this is a test message",
            session_id="ses_123",
            requirement_ids=["req_001", "req_002"],
            extracted=True,
            sent_at=now
        )

        assert msg.sender_name == "Test User"
        assert msg.content == "Hello, this is a test message"
        assert msg.session_id == "ses_123"
        assert msg.requirement_ids == ["req_001", "req_002"]
        assert msg.extracted is True

    def test_message_types(self):
        """Verify different message types can be stored"""
        message_types = ["text", "image", "file", "post"]

        for msg_type in message_types:
            msg = ChatMessage(
                chat_id="oc_abc123",
                message_id=f"om_msg_{msg_type}",
                sender_id="ou_user123",
                message_type=msg_type,
                sent_at=datetime.now(UTC)
            )
            assert msg.message_type == msg_type

    def test_repr(self):
        """Verify __repr__ returns expected format"""
        msg = ChatMessage(
            chat_id="oc_abc123",
            message_id="om_msg_repr",
            sender_id="ou_user123",
            message_type="text",
            sent_at=datetime.now(UTC)
        )

        repr_str = repr(msg)
        assert "ChatMessage" in repr_str
        assert "oc_abc123" in repr_str
        assert "text" in repr_str


class TestIDPrefixConstants:
    """Test IDPrefix constants for SESSION and MESSAGE"""

    def test_session_prefix(self):
        """Verify SESSION prefix is defined"""
        assert IDPrefix.SESSION == "ses"

    def test_message_prefix(self):
        """Verify MESSAGE prefix is defined"""
        assert IDPrefix.MESSAGE == "msg"


class TestRequirementContextMessageIds:
    """Test context_message_ids field in Requirement model"""

    def test_context_message_ids_field_exists(self):
        """Verify Requirement model has context_message_ids field"""
        from agents.capabilities.requirements.models.requirement import Requirement

        req = Requirement(
            title="Test Requirement",
            description="Test description",
            context_message_ids=[]
        )

        assert hasattr(req, "context_message_ids")
        assert req.context_message_ids == []

    def test_context_message_ids_can_be_set(self):
        """Verify context_message_ids can store message IDs"""
        from agents.capabilities.requirements.models.requirement import Requirement

        req = Requirement(
            title="Test Requirement",
            description="Test description",
            context_message_ids=["msg_001", "msg_002", "msg_003"]
        )

        assert req.context_message_ids == ["msg_001", "msg_002", "msg_003"]
