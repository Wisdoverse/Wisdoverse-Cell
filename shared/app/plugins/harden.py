"""HardenPlugin — RuntimePlugin that wraps agents with input validation + audit logging.

Validates every incoming event payload (size + injection detection) before
delegating to the inner agent. Emits structured audit_log entries for
security events, successful handling, and handler failures.
"""

from typing import Any

from shared.app.runtime import RuntimePlugin
from shared.config import settings
from shared.infra.audit_log import AuditAction, audit_log
from shared.infra.input_validator import InputValidationError, InputValidator
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class HardenedAgent(BaseAgent):
    """Composition wrapper that adds input validation and audit logging to any BaseAgent."""

    def __init__(self, agent: BaseAgent):
        super().__init__(
            agent_id=agent.agent_id,
            agent_name=agent.agent_name,
            subscribed_events=agent.subscribed_events,
            published_events=agent.published_events,
            a2a_enabled=agent.a2a_enabled,
            mcp_enabled=agent.mcp_enabled,
        )
        self._agent = agent
        self._validator = InputValidator(max_payload_bytes=settings.max_payload_size_bytes)

    @staticmethod
    def _trace_id_from_request(request: dict) -> str | None:
        trace_id = request.get("trace_id")
        if isinstance(trace_id, str):
            return trace_id
        metadata = request.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("trace_id"), str):
            return metadata["trace_id"]
        return None

    @staticmethod
    def _request_action(request: dict) -> str:
        action = request.get("action", "")
        return str(action)[:64] if action else ""

    async def handle_event(self, event: Event) -> list[Event]:
        # 1. Validate input
        try:
            self._validator.validate(event.payload)
        except InputValidationError:
            audit_log(
                action=AuditAction.INJECTION_BLOCKED,
                agent_id=self.agent_id,
                detail={"event_type": event.event_type, "event_id": event.event_id},
                trace_id=event.metadata.trace_id,
            )
            raise

        # 2. Delegate to inner agent
        try:
            results = await self._agent.handle_event(event)
        except Exception as exc:
            audit_log(
                action=AuditAction.EVENT_FAILED,
                agent_id=self.agent_id,
                detail={
                    "event_type": event.event_type,
                    "event_id": event.event_id,
                    "error": str(exc),
                },
                trace_id=event.metadata.trace_id,
            )
            raise

        # 3. Audit success
        audit_log(
            action=AuditAction.EVENT_HANDLED,
            agent_id=self.agent_id,
            detail={"event_type": event.event_type, "event_id": event.event_id},
            trace_id=event.metadata.trace_id,
        )
        return results

    # ── Delegated methods ────────────────────────────────────────────────────

    async def handle_request(self, request: dict) -> dict:
        trace_id = self._trace_id_from_request(request)
        action = self._request_action(request)

        try:
            self._validator.validate(request)
        except InputValidationError:
            audit_log(
                action=AuditAction.INJECTION_BLOCKED,
                agent_id=self.agent_id,
                detail={"request_action": action},
                trace_id=trace_id,
            )
            raise

        try:
            result = await self._agent.handle_request(request)
        except Exception as exc:
            audit_log(
                action=AuditAction.REQUEST_FAILED,
                agent_id=self.agent_id,
                detail={
                    "request_action": action,
                    "error_type": type(exc).__name__,
                },
                trace_id=trace_id,
            )
            raise

        audit_log(
            action=AuditAction.REQUEST_HANDLED,
            agent_id=self.agent_id,
            detail={"request_action": action},
            trace_id=trace_id,
        )
        return result

    async def startup(self) -> None:
        await self._agent.startup()

    async def shutdown(self) -> None:
        await self._agent.shutdown()

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the wrapped agent for methods not explicitly delegated."""
        return getattr(self._agent, name)

    def __repr__(self) -> str:
        return f"<HardenedAgent wrapping {self._agent!r}>"


class HardenPlugin(RuntimePlugin):
    """RuntimePlugin that wraps any BaseAgent with input validation and audit logging."""

    name = "harden"

    def wrap_agent(self, agent: BaseAgent) -> BaseAgent:
        return HardenedAgent(agent)
