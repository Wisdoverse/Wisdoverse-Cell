"""Tests for protocol bridges."""

from unittest.mock import AsyncMock

import pytest

from shared.protocols.a2a.models import (
    DataPart,
    Task,
    TaskState,
    TextPart,
)
from shared.protocols.bridge.event_bridge import (
    EventA2AMapping,
    EventBusA2ABridge,
)
from shared.schemas.event import Event, EventMetadata


class TestEventA2AMapping:
    """Tests for EventA2AMapping."""

    def test_basic_mapping(self):
        """Test creating a basic mapping."""
        mapping = EventA2AMapping(
            event_type="requirement.extracted",
            target_agent_id="analysis-agent",
        )

        assert mapping.event_type == "requirement.extracted"
        assert mapping.target_agent_id == "analysis-agent"
        assert mapping.skill_id is None
        assert mapping.transform is None

    def test_mapping_with_transform(self):
        """Test creating a mapping with transform."""

        def transform(event: Event) -> dict:
            return {"transformed": event.payload}

        mapping = EventA2AMapping(
            event_type="test.event",
            target_agent_id="target-agent",
            transform=transform,
        )

        assert mapping.transform is not None


class TestEventBusA2ABridge:
    """Tests for EventBusA2ABridge."""

    @pytest.fixture
    def mock_registry(self):
        """Create a mock agent registry."""
        registry = AsyncMock()
        return registry

    @pytest.fixture
    def mock_event_bus(self):
        """Create a mock event bus."""
        event_bus = AsyncMock()
        return event_bus

    @pytest.fixture
    def bridge(self, mock_registry, mock_event_bus) -> EventBusA2ABridge:
        """Create a bridge with mocks."""
        return EventBusA2ABridge(
            registry=mock_registry,
            event_bus=mock_event_bus,
            source_agent_id="test-bridge",
        )

    def test_add_mapping(self, bridge: EventBusA2ABridge):
        """Test adding a mapping."""
        mapping = EventA2AMapping(
            event_type="test.event",
            target_agent_id="target-agent",
        )

        bridge.add_mapping(mapping)

        assert "test.event" in bridge._mappings

    def test_remove_mapping(self, bridge: EventBusA2ABridge):
        """Test removing a mapping."""
        mapping = EventA2AMapping(
            event_type="test.event",
            target_agent_id="target-agent",
        )
        bridge.add_mapping(mapping)

        result = bridge.remove_mapping("test.event")
        assert result is True
        assert "test.event" not in bridge._mappings

        result = bridge.remove_mapping("nonexistent")
        assert result is False

    def test_event_to_a2a_message(self, bridge: EventBusA2ABridge):
        """Test converting event to A2A message."""
        event = Event(
            event_type="requirement.extracted",
            source_agent="requirement-manager",
            payload={
                "meeting_id": "meeting_123",
                "requirements": [{"id": "req_1"}],
            },
            metadata=EventMetadata(trace_id="trace_abc"),
        )

        message = bridge.event_to_a2a_message(event)

        assert message.role == "user"
        assert len(message.parts) == 1
        assert isinstance(message.parts[0], DataPart)

        data = message.parts[0].data
        assert data["event_type"] == "requirement.extracted"
        assert data["trace_id"] == "trace_abc"

    def test_event_to_a2a_message_with_transform(self, bridge: EventBusA2ABridge):
        """Test converting event with custom transform."""

        def transform(event: Event) -> dict:
            return {"custom_field": event.payload.get("value", 0) * 2}

        mapping = EventA2AMapping(
            event_type="test.event",
            target_agent_id="target",
            transform=transform,
        )

        event = Event(
            event_type="test.event",
            source_agent="source",
            payload={"value": 10},
        )

        message = bridge.event_to_a2a_message(event, mapping)

        data = message.parts[0].data
        assert data["payload"]["custom_field"] == 20

    def test_event_to_a2a_message_with_text_summary(self, bridge: EventBusA2ABridge):
        """Test event conversion includes text summary when message present."""
        event = Event(
            event_type="notification.sent",
            source_agent="notifier",
            payload={"message": "Hello World", "recipient": "user_123"},
        )

        message = bridge.event_to_a2a_message(event)

        assert len(message.parts) == 2
        assert isinstance(message.parts[0], TextPart)
        assert message.parts[0].text == "Hello World"

    def test_a2a_task_to_event_completed(self, bridge: EventBusA2ABridge):
        """Test converting completed A2A task to event."""
        task = Task()
        task.update_status(TaskState.completed("Done!"))

        original_event = Event(
            event_id="orig_123",
            event_type="test.event",
            source_agent="source",
            payload={},
            metadata=EventMetadata(trace_id="trace_xyz"),
        )

        result_event = bridge.a2a_task_to_event(task, original_event)

        assert result_event.event_type == "a2a.task.completed"
        assert result_event.source_agent == "test-bridge"
        assert result_event.metadata.trace_id == "trace_xyz"
        assert result_event.metadata.correlation_id == "orig_123"
        assert result_event.payload["status"] == "completed"

    def test_a2a_task_to_event_failed(self, bridge: EventBusA2ABridge):
        """Test converting failed A2A task to event."""
        task = Task()
        task.update_status(TaskState.failed("Something went wrong"))

        result_event = bridge.a2a_task_to_event(task)

        assert result_event.event_type == "a2a.task.failed"
        assert "Something went wrong" in result_event.payload.get("message", "")

    def test_a2a_task_to_event_canceled(self, bridge: EventBusA2ABridge):
        """Test converting canceled A2A task to event."""
        task = Task()
        task.update_status(TaskState.canceled("User canceled"))

        result_event = bridge.a2a_task_to_event(task)

        assert result_event.event_type == "a2a.task.canceled"

    def test_a2a_task_to_event_with_artifacts(self, bridge: EventBusA2ABridge):
        """Test converting task with artifacts."""
        from shared.protocols.a2a.models import Artifact

        task = Task()
        task.add_artifact(
            Artifact(
                name="result.json",
                description="Analysis result",
                parts=[DataPart(data={"result": "success"})],
            )
        )
        task.update_status(TaskState.completed())

        result_event = bridge.a2a_task_to_event(task)

        assert "artifacts" in result_event.payload
        assert len(result_event.payload["artifacts"]) == 1
        assert result_event.payload["artifacts"][0]["name"] == "result.json"

    @pytest.mark.asyncio
    async def test_handle_event_unmapped(self, bridge: EventBusA2ABridge):
        """Test handling event without mapping."""
        event = Event(
            event_type="unmapped.event",
            source_agent="source",
            payload={},
        )

        result = await bridge.handle_event(event)

        assert result == []

    @pytest.mark.asyncio
    async def test_close_all_clients(self, bridge: EventBusA2ABridge):
        """Test closing all clients."""
        # Add some mock clients
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()
        bridge._active_clients["agent1"] = mock_client1
        bridge._active_clients["agent2"] = mock_client2

        await bridge.close_all_clients()

        mock_client1.disconnect.assert_called_once()
        mock_client2.disconnect.assert_called_once()
        assert len(bridge._active_clients) == 0


class TestEventA2AMappingIntegration:
    """Integration tests for event-A2A mapping scenarios."""

    def test_requirement_extraction_mapping(self):
        """Test mapping for requirement extraction workflow."""
        mapping = EventA2AMapping(
            event_type="meeting.transcribed",
            target_agent_id="requirement-manager",
            skill_id="requirement-extraction",
        )

        assert mapping.skill_id == "requirement-extraction"

    def test_approval_workflow_mapping(self):
        """Test mapping for approval workflow."""

        def extract_approval_data(event: Event) -> dict:
            return {
                "request_id": event.payload.get("request_id"),
                "approver_id": event.payload.get("assigned_to"),
                "priority": event.payload.get("priority", "normal"),
            }

        mapping = EventA2AMapping(
            event_type="approval.requested",
            target_agent_id="approval-agent",
            transform=extract_approval_data,
        )

        event = Event(
            event_type="approval.requested",
            source_agent="workflow-engine",
            payload={
                "request_id": "req_123",
                "assigned_to": "user_456",
                "priority": "high",
                "details": {"amount": 1000},
            },
        )

        # Simulate transform
        transformed = mapping.transform(event)

        assert transformed["request_id"] == "req_123"
        assert transformed["approver_id"] == "user_456"
        assert transformed["priority"] == "high"
        assert "details" not in transformed  # Filtered out
