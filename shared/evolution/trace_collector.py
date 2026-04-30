"""
Trace Collector — wraps handle_event calls and sanitizes PII.

Provides:
- _sanitize_payload: module-level PII redaction for event payloads
- TraceHandle: mutable handle for recording one handle_event execution
- TraceCollector: factory that creates TraceHandles
"""

import hashlib
from datetime import UTC, datetime
from typing import Any, Optional

from shared.schemas.event import Event
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# PII field names whose string values must be hashed before storage
_PII_FIELDS: frozenset[str] = frozenset(
    {"user_name", "user_id", "email", "phone", "message", "content", "text"}
)


# ── PII sanitization ─────────────────────────────────────────────────────────


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of *payload* with PII string fields replaced by hash tokens.

    For each key that is in ``_PII_FIELDS``:
    - If the value is a ``str``, replace with ``"hash:<sha256[:16]>:len:<length>"``.
    - If the value is a ``dict``, recurse into it.
    - Otherwise leave as-is (e.g. numeric IDs).

    The original dict is **never** mutated.
    """
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _PII_FIELDS:
            if isinstance(value, str):
                digest = hashlib.sha256(value.encode()).hexdigest()[:16]
                result[key] = f"hash:{digest}:len:{len(value)}"
            elif isinstance(value, dict):
                result[key] = _sanitize_payload(value)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = _sanitize_payload(value)
        elif isinstance(value, list):
            result[key] = [
                _sanitize_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


# ── TraceHandle ──────────────────────────────────────────────────────────────


class TraceHandle:
    """Mutable handle for recording execution details during one handle_event call.

    Usage::

        handle = collector.start(event)
        try:
            results = await agent._process(event)
            handle.record_success(results)
        except Exception as exc:
            handle.record_failure(exc)
        await repo.save(handle.to_dict())
    """

    def __init__(self, agent_id: str, event: Event) -> None:
        self._agent_id: str = agent_id
        self._event_type: str = event.event_type
        self._trace_id: str = event.metadata.trace_id or event.event_id

        # Sanitize input payload — store as plain dict (no Event object).
        # Use mode="json" so datetime fields are serialized as ISO strings,
        # which is required for SQLite's JSON column type.
        sanitized_payload = _sanitize_payload(event.payload)
        event_dict = event.model_dump(mode="json")
        event_dict["payload"] = sanitized_payload
        self._input_event: dict[str, Any] = event_dict

        self._output_events: list[dict[str, Any]] = []
        self._llm_calls: list[dict[str, Any]] = []
        self._skill_used: Optional[str] = None
        self._skill_version: Optional[int] = None
        self._started_at: datetime = datetime.now(UTC)
        self._completed_at: Optional[datetime] = None
        self._success: Optional[bool] = None
        self._error: Optional[str] = None
        self._auto_score: Optional[float] = None
        self._human_rating: Optional[int] = None
        self._human_correction: Optional[str] = None

    # ── mutators ─────────────────────────────────────────────────────────────

    def record_success(self, result_events: list[Event]) -> None:
        """Mark execution as successful and capture output event summaries.

        Only ``event_type`` and ``source_agent`` are stored — payloads are
        intentionally excluded to avoid storing unscanned PII in the trace.
        """
        self._success = True
        self._completed_at = datetime.now(UTC)
        self._output_events = [
            {"event_type": e.event_type, "source_agent": e.source_agent}
            for e in result_events
        ]
        logger.debug(
            "trace_success",
            trace_id=self._trace_id,
            agent_id=self._agent_id,
            event_type=self._event_type,
            output_count=len(result_events),
        )

    def record_failure(self, exc: Exception) -> None:
        """Mark execution as failed and capture the error message."""
        self._success = False
        self._completed_at = datetime.now(UTC)
        self._error = str(exc)
        logger.warning(
            "trace_failure",
            trace_id=self._trace_id,
            agent_id=self._agent_id,
            event_type=self._event_type,
            error=self._error,
        )

    def add_llm_call(self, record: dict[str, Any]) -> None:
        """Append an LLM call record (plain dict or LLMCallRecord.model_dump())."""
        self._llm_calls.append(record)

    # ── read-only properties ─────────────────────────────────────────────────

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def event_type(self) -> str:
        return self._event_type

    @property
    def input_event(self) -> dict[str, Any]:
        return self._input_event

    @property
    def output_events(self) -> list[dict[str, Any]]:
        return self._output_events

    @property
    def llm_calls(self) -> list[dict[str, Any]]:
        return self._llm_calls

    @property
    def skill_used(self) -> Optional[str]:
        return self._skill_used

    @skill_used.setter
    def skill_used(self, value: Optional[str]) -> None:
        self._skill_used = value

    @property
    def skill_version(self) -> Optional[int]:
        return self._skill_version

    @skill_version.setter
    def skill_version(self, value: Optional[int]) -> None:
        self._skill_version = value

    @property
    def started_at(self) -> datetime:
        return self._started_at

    @property
    def completed_at(self) -> Optional[datetime]:
        return self._completed_at

    @property
    def success(self) -> Optional[bool]:
        return self._success

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def auto_score(self) -> Optional[float]:
        return self._auto_score

    @auto_score.setter
    def auto_score(self, value: Optional[float]) -> None:
        self._auto_score = value

    @property
    def human_rating(self) -> Optional[int]:
        return self._human_rating

    @human_rating.setter
    def human_rating(self, value: Optional[int]) -> None:
        self._human_rating = value

    @property
    def human_correction(self) -> Optional[str]:
        return self._human_correction

    @human_correction.setter
    def human_correction(self, value: Optional[str]) -> None:
        self._human_correction = value

    # ── serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return all fields as a plain dict suitable for persistence."""
        return {
            "trace_id": self._trace_id,
            "agent_id": self._agent_id,
            "event_type": self._event_type,
            "input_event": self._input_event,
            "output_events": self._output_events,
            "llm_calls": self._llm_calls,
            "skill_used": self._skill_used,
            "skill_version": self._skill_version,
            "started_at": self._started_at.isoformat(),
            "completed_at": (
                self._completed_at.isoformat() if self._completed_at else None
            ),
            "success": self._success,
            "error": self._error,
        }


# ── TraceCollector ───────────────────────────────────────────────────────────


class TraceCollector:
    """Factory that creates :class:`TraceHandle` instances for one agent.

    Typically one ``TraceCollector`` is created per agent instance::

        self._tracer = TraceCollector(agent_id=self.agent_id)

    Then at the start of each ``handle_event`` call::

        handle = self._tracer.start(event)
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id

    def start(self, event: Event) -> TraceHandle:
        """Create and return a new :class:`TraceHandle` for *event*."""
        return TraceHandle(agent_id=self._agent_id, event=event)
