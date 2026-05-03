"""B11: Event schema_version field tests."""
import pytest
from pydantic import ValidationError

from shared.schemas.event import Event


class TestEventSchemaVersion:
    """Verify schema_version is present in serialized events."""

    def test_default_schema_version(self):
        event = Event(
            event_type="test.created",
            source_agent="test-agent",
            payload={"key": "value"},
        )
        assert event.schema_version == "1.0"

    def test_schema_version_in_serialized_output(self):
        event = Event(
            event_type="test.created",
            source_agent="test-agent",
            payload={},
        )
        data = event.model_dump()
        assert "schema_version" in data
        assert data["schema_version"] == "1.0"

    def test_schema_version_in_json(self):
        event = Event(
            event_type="test.created",
            source_agent="test-agent",
            payload={},
        )
        json_str = event.model_dump_json()
        assert '"schema_version":"1.0"' in json_str

    def test_schema_version_roundtrip(self):
        event = Event(
            event_type="test.created",
            source_agent="test-agent",
            payload={},
            schema_version="2.0",
        )
        restored = Event.model_validate_json(event.model_dump_json())
        assert restored.schema_version == "2.0"

    def test_create_factory_includes_schema_version(self):
        event = Event.create(
            event_type="test.created",
            source_agent="test-agent",
            payload={"data": 1},
        )
        assert event.schema_version == "1.0"

    def test_event_type_requires_domain_action_name(self):
        with pytest.raises(ValidationError, match="event_type must use"):
            Event.create(
                event_type="invalid",
                source_agent="test-agent",
                payload={},
            )

    def test_source_agent_requires_publishing_agent_id(self):
        for source_agent in ("", "   ", "Test Agent", "test.agent"):
            with pytest.raises(ValidationError, match="source_agent must be"):
                Event.create(
                    event_type="test.created",
                    source_agent=source_agent,
                    payload={},
                )

        event = Event.create(
            event_type="test.created",
            source_agent="test-agent_1",
            payload={},
        )
        assert event.source_agent == "test-agent_1"

    def test_event_fields_are_immutable(self):
        event = Event.create(
            event_type="test.created",
            source_agent="test-agent",
            payload={"data": 1},
        )
        with pytest.raises(ValidationError):
            event.event_type = "test.changed"  # type: ignore[misc]

    def test_event_metadata_is_immutable(self):
        event = Event.create(
            event_type="test.created",
            source_agent="test-agent",
            payload={"data": 1},
            trace_id="trace_001",
        )
        with pytest.raises(ValidationError):
            event.metadata.trace_id = "trace_002"  # type: ignore[misc]

    def test_event_payload_is_recursively_read_only(self):
        event = Event.create(
            event_type="test.created",
            source_agent="test-agent",
            payload={"nested": {"items": [{"value": 1}]}},
        )
        with pytest.raises(TypeError):
            event.payload["extra"] = "nope"  # type: ignore[index]
        with pytest.raises(TypeError):
            event.payload["nested"]["items"][0]["value"] = 2  # type: ignore[index]

    def test_read_only_payload_serializes_as_json_object(self):
        event = Event.create(
            event_type="test.created",
            source_agent="test-agent",
            payload={"nested": {"items": [{"value": 1}]}},
        )
        assert event.model_dump()["payload"] == {"nested": {"items": [{"value": 1}]}}
        restored = Event.model_validate_json(event.model_dump_json())
        assert restored.model_dump()["payload"] == {"nested": {"items": [{"value": 1}]}}

    def test_event_payload_rejects_non_json_values(self):
        with pytest.raises(ValidationError, match="non-JSON-serializable"):
            Event.create(
                event_type="test.created",
                source_agent="test-agent",
                payload={"bad": object()},
            )

    def test_event_payload_rejects_non_finite_numbers(self):
        with pytest.raises(ValidationError, match="finite JSON numbers"):
            Event.create(
                event_type="test.created",
                source_agent="test-agent",
                payload={"bad": float("nan")},
            )
