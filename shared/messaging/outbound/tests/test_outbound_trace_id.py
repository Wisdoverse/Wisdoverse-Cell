"""B14: OutboundMessage trace_id field tests."""
from shared.messaging.outbound.models.messages import OutboundMessage


class TestOutboundMessageTraceId:
    """Verify trace_id field on OutboundMessage for end-to-end tracing."""

    def test_default_trace_id_is_none(self):
        msg = OutboundMessage(
            channel_id="feishu",
            target_chat_id="oc_xxx",
            content="hello",
        )
        assert msg.trace_id is None

    def test_trace_id_set_explicitly(self):
        msg = OutboundMessage(
            channel_id="feishu",
            target_chat_id="oc_xxx",
            content="hello",
            trace_id="trace_abc123",
        )
        assert msg.trace_id == "trace_abc123"

    def test_trace_id_in_serialized_output(self):
        msg = OutboundMessage(
            channel_id="feishu",
            target_chat_id="oc_xxx",
            content="hello",
            trace_id="trace_xyz",
        )
        data = msg.model_dump()
        assert data["trace_id"] == "trace_xyz"

    def test_trace_id_roundtrip(self):
        msg = OutboundMessage(
            channel_id="feishu",
            target_chat_id="oc_xxx",
            content="test",
            trace_id="trace_roundtrip",
        )
        restored = OutboundMessage.model_validate_json(msg.model_dump_json())
        assert restored.trace_id == "trace_roundtrip"
