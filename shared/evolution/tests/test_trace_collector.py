"""Tests for TraceCollector and PII sanitization — TDD: written before implementation."""

import hashlib

from shared.evolution.trace_collector import TraceCollector, TraceHandle, _sanitize_payload
from shared.schemas.event import Event

# ── _sanitize_payload ────────────────────────────────────────────────────────


class TestSanitizePayload:
    """_sanitize_payload replaces PII string fields with hash:...:len:... tokens."""

    def test_user_name_is_hashed(self):
        payload = {"user_name": "Alice"}
        result = _sanitize_payload(payload)
        assert result["user_name"] != "Alice"
        expected_hash = hashlib.sha256(b"Alice").hexdigest()[:16]
        assert result["user_name"] == f"hash:{expected_hash}:len:5"

    def test_email_is_hashed(self):
        payload = {"email": "alice@example.com"}
        result = _sanitize_payload(payload)
        assert "alice@example.com" not in result["email"]
        assert result["email"].startswith("hash:")

    def test_phone_is_hashed(self):
        payload = {"phone": "+8613800138000"}
        result = _sanitize_payload(payload)
        assert result["phone"].startswith("hash:")

    def test_message_is_hashed(self):
        payload = {"message": "Hello, world!"}
        result = _sanitize_payload(payload)
        assert result["message"].startswith("hash:")

    def test_content_is_hashed(self):
        payload = {"content": "Some content here"}
        result = _sanitize_payload(payload)
        assert result["content"].startswith("hash:")

    def test_text_is_hashed(self):
        payload = {"text": "raw text value"}
        result = _sanitize_payload(payload)
        assert result["text"].startswith("hash:")

    def test_user_id_is_hashed(self):
        payload = {"user_id": "usr_abc123"}
        result = _sanitize_payload(payload)
        assert result["user_id"].startswith("hash:")

    def test_non_pii_fields_untouched(self):
        payload = {"status": "active", "count": 42, "enabled": True}
        result = _sanitize_payload(payload)
        assert result["status"] == "active"
        assert result["count"] == 42
        assert result["enabled"] is True

    def test_non_string_pii_kept_as_is(self):
        """Non-string PII values (e.g. numeric user_id) are kept unchanged."""
        payload = {"user_id": 12345}
        result = _sanitize_payload(payload)
        assert result["user_id"] == 12345

    def test_nested_dict_recursion(self):
        payload = {
            "outer": "safe",
            "nested": {"user_name": "Bob", "count": 3},
        }
        result = _sanitize_payload(payload)
        assert result["outer"] == "safe"
        assert result["nested"]["user_name"].startswith("hash:")
        assert result["nested"]["count"] == 3

    def test_hash_format_structure(self):
        """Hash token format must be hash:<16-hex-chars>:len:<int>."""
        payload = {"user_name": "Test"}
        result = _sanitize_payload(payload)
        token = result["user_name"]
        parts = token.split(":")
        assert len(parts) == 4
        assert parts[0] == "hash"
        assert len(parts[1]) == 16
        assert parts[2] == "len"
        assert parts[3] == str(len("Test"))

    def test_empty_payload(self):
        assert _sanitize_payload({}) == {}

    def test_original_not_mutated(self):
        payload = {"user_name": "Alice", "status": "ok"}
        _sanitize_payload(payload)
        assert payload["user_name"] == "Alice"


# ── TraceHandle ──────────────────────────────────────────────────────────────


class TestTraceHandle:
    """TraceHandle captures execution details for one handle_event call."""

    def _make_event(self, event_type="test.action", payload=None):
        return Event.create(
            event_type=event_type,
            source_agent="test-agent",
            payload=payload or {"status": "ok"},
            trace_id="trace_test_001",
        )

    def test_init_sets_agent_id(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.agent_id == "pjm-agent"

    def test_init_sets_event_type(self):
        event = self._make_event(event_type="pm.decompose")
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.event_type == "pm.decompose"

    def test_trace_id_from_event_metadata(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.trace_id == "trace_test_001"

    def test_input_event_pii_sanitized(self):
        event = self._make_event(payload={"user_name": "Alice", "status": "ok"})
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.input_event["payload"]["user_name"].startswith("hash:")
        assert handle.input_event["payload"]["status"] == "ok"

    def test_started_at_set_on_init(self):
        from datetime import UTC, datetime
        event = self._make_event()
        before = datetime.now(UTC)
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        after = datetime.now(UTC)
        assert before <= handle.started_at <= after

    def test_success_defaults_to_none(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.success is None

    def test_record_success(self):
        event = self._make_event()
        out_event = Event.create(
            event_type="pm.done",
            source_agent="pjm-agent",
            payload={"result": "ok", "user_name": "Alice"},
        )
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.record_success([out_event])
        assert handle.success is True
        assert handle.error is None
        assert handle.completed_at is not None
        assert len(handle.output_events) == 1

    def test_record_success_output_events_no_payloads(self):
        """Output event summaries must NOT contain payloads."""
        event = self._make_event()
        out_event = Event.create(
            event_type="pm.done",
            source_agent="pjm-agent",
            payload={"secret": "sensitive_data"},
        )
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.record_success([out_event])
        summary = handle.output_events[0]
        assert "payload" not in summary
        assert summary["event_type"] == "pm.done"
        assert summary["source_agent"] == "pjm-agent"

    def test_record_failure(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.record_failure(ValueError("Something went wrong"))
        assert handle.success is False
        assert "Something went wrong" in handle.error
        assert handle.completed_at is not None

    def test_add_llm_call(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        llm_record = {"model_id": "claude-sonnet-4-20250514", "tokens": 100}
        handle.add_llm_call(llm_record)
        assert len(handle.llm_calls) == 1
        assert handle.llm_calls[0] == llm_record

    def test_add_multiple_llm_calls(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.add_llm_call({"call": 1})
        handle.add_llm_call({"call": 2})
        assert len(handle.llm_calls) == 2

    def test_skill_used_and_version_default_none(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        assert handle.skill_used is None
        assert handle.skill_version is None

    def test_to_dict_complete(self):
        event = self._make_event(payload={"status": "ok"})
        out_event = Event.create(
            event_type="pm.done",
            source_agent="pjm-agent",
            payload={"result": "done"},
        )
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.record_success([out_event])
        handle.add_llm_call({"model_id": "claude-sonnet-4-20250514"})

        d = handle.to_dict()
        assert d["agent_id"] == "pjm-agent"
        assert d["event_type"] == "test.action"
        assert d["trace_id"] == "trace_test_001"
        assert d["success"] is True
        assert isinstance(d["output_events"], list)
        assert isinstance(d["llm_calls"], list)
        assert "started_at" in d
        assert "completed_at" in d
        assert d["error"] is None

    def test_to_dict_failure(self):
        event = self._make_event()
        handle = TraceHandle(agent_id="pjm-agent", event=event)
        handle.record_failure(RuntimeError("Timeout"))
        d = handle.to_dict()
        assert d["success"] is False
        assert "Timeout" in d["error"]


# ── TraceCollector ───────────────────────────────────────────────────────────


class TestTraceCollector:
    """TraceCollector creates TraceHandles for each handle_event call."""

    def test_start_returns_trace_handle(self):
        collector = TraceCollector(agent_id="pjm-agent")
        event = Event.create(
            event_type="pm.decompose",
            source_agent="sync-module",
            payload={"task_id": "t_001"},
            trace_id="trace_abc",
        )
        handle = collector.start(event)
        assert isinstance(handle, TraceHandle)

    def test_start_sets_correct_agent_id(self):
        collector = TraceCollector(agent_id="chat-agent")
        event = Event.create(
            event_type="chat.pm-query",
            source_agent="frontend",
            payload={"query": "status?"},
            trace_id="trace_xyz",
        )
        handle = collector.start(event)
        assert handle.agent_id == "chat-agent"

    def test_full_success_flow(self):
        collector = TraceCollector(agent_id="pjm-agent")
        event = Event.create(
            event_type="pm.decompose",
            source_agent="sync-module",
            payload={"task_id": "t_001", "user_name": "Charlie"},
            trace_id="trace_full",
        )
        out_event = Event.create(
            event_type="pm.decompose-completed",
            source_agent="pjm-agent",
            payload={"subtasks": 3},
        )
        handle = collector.start(event)
        handle.record_success([out_event])

        assert handle.success is True
        assert handle.agent_id == "pjm-agent"
        assert handle.event_type == "pm.decompose"
        assert len(handle.output_events) == 1
        assert handle.output_events[0]["event_type"] == "pm.decompose-completed"
        # PII must be sanitized
        assert handle.input_event["payload"]["user_name"].startswith("hash:")

    def test_full_failure_flow(self):
        collector = TraceCollector(agent_id="sync-module")
        event = Event.create(
            event_type="sync.trigger",
            source_agent="scheduler",
            payload={"run_id": "r_001"},
            trace_id="trace_fail",
        )
        handle = collector.start(event)
        handle.record_failure(ConnectionError("Feishu API down"))

        assert handle.success is False
        assert "Feishu API down" in handle.error
        d = handle.to_dict()
        assert d["success"] is False
        assert "Feishu API down" in d["error"]
