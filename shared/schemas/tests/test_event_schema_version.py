"""B11: Event schema_version field tests."""
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
