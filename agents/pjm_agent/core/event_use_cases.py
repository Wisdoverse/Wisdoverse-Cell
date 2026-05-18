"""Application use cases for PJM agent event dispatch."""
from __future__ import annotations

from typing import Any, Protocol

from shared.core import request_error
from shared.observability.privacy import hash_identifier
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import ChatPMQueryPayload, RiskDetectedPayload
from .alert_ports import PJMAlertLogStore

logger = get_logger("pjm_agent.events")

CHAT_ALERTS_PREVIEW = 5


class PJMEventConfigPort(Protocol):
    """Configuration snapshot needed by PJM event responses."""

    members: list[Any]
    projects: list[Any]


class PJMEventAlertPort(Protocol):
    """Alert operations required by PJM event handling."""

    async def check_all(self) -> list[dict[str, Any]]:
        """Return currently active alerts."""


class PJMEventPushPort(Protocol):
    """Outbound notification operations required by PJM event handling."""

    async def push_alerts(self, alerts: list[dict[str, Any]]) -> Any:
        """Push active alerts to the configured channel."""

    async def push_risks(self, risks: list[dict[str, Any]]) -> Any:
        """Push risk notifications to the configured channel."""


class PJMDecompositionEventPort(Protocol):
    """Decomposition operations required by PJM event handling."""

    async def handle_decompose(self, event: Event) -> list[Event]:
        """Handle a decomposition event."""

    async def publish_event_via_outbox(
        self,
        event: Event,
        *,
        wp_id: int | None = None,
    ) -> None:
        """Stage and publish an event through the durable outbox boundary."""


class PJMEventFactoryPort(Protocol):
    """Event factory owned by the service shell."""

    def create_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
    ) -> Event:
        """Create an integration event with the service identity."""


class PJMMetricsPort(Protocol):
    """Metrics sink for PJM event handling."""

    def record_alert_triggered(self, *, alert_type: str, severity: str) -> None:
        """Record one triggered alert."""


class NoopPJMMetrics:
    """No-op metrics sink for tests and environments without Prometheus."""

    def record_alert_triggered(self, *, alert_type: str, severity: str) -> None:
        return None


class PJMEventUseCase:
    """Dispatch and execute PJM event workflows outside the service shell."""

    def __init__(
        self,
        *,
        agent_id: str,
        config: PJMEventConfigPort,
        alert: PJMEventAlertPort,
        push: PJMEventPushPort,
        alert_log_store: PJMAlertLogStore,
        decomposition: PJMDecompositionEventPort,
        event_factory: PJMEventFactoryPort,
        metrics: PJMMetricsPort | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._config = config
        self._alert = alert
        self._push = push
        self._alert_log_store = alert_log_store
        self._decomposition = decomposition
        self._event_factory = event_factory
        self._metrics = metrics or NoopPJMMetrics()

    async def handle(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.SYNC_COMPLETED:
            return await self._run_alerts(event)
        if event.event_type == EventTypes.ANALYSIS_RISK_DETECTED:
            return await self._handle_risks(event)
        if event.event_type == EventTypes.CHAT_PM_QUERY:
            return await self._handle_chat_query(event)
        if event.event_type == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE:
            return await self._handle_decompose(event)
        if event.event_type == EventTypes.COORDINATOR_DISPATCH:
            return self._handle_coordinator_dispatch(event)
        return []

    async def _run_alerts(self, event: Event) -> list[Event]:
        events: list[Event] = []
        trace_id = _trace_id(event)

        try:
            alerts = await self._alert.check_all()
        except Exception as exc:
            logger.error("pm_alert_check_failed", error=str(exc), trace_id=trace_id)
            return events

        if not alerts:
            return events

        push_ok = False
        try:
            push_ok = await self._push.push_alerts(alerts)
        except Exception as exc:
            logger.error("pm_alert_push_failed", error=str(exc), alert_count=len(alerts))

        for alert in alerts:
            self._metrics.record_alert_triggered(
                alert_type=alert["type"],
                severity=alert["severity"],
            )

        try:
            await self._alert_log_store.record_alerts(alerts)
        except Exception as exc:
            logger.error("pm_alert_log_failed", error=str(exc))

        events.append(
            self._event_factory.create_event(
                EventTypes.PM_ALERT_TRIGGERED,
                {
                    "alert_count": len(alerts),
                    "alerts": alerts,
                    "push_ok": push_ok,
                },
                trace_id=trace_id,
            )
        )
        return events

    async def _handle_risks(self, event: Event) -> list[Event]:
        payload = RiskDetectedPayload.model_validate(event.payload)
        risks = payload.risks
        if not risks:
            return []
        logger.info("pm_risks_received", count=len(risks))
        try:
            await self._push.push_risks(risks)
        except Exception as exc:
            logger.warning("pm_risks_push_failed", error=str(exc), count=len(risks))
        return []

    async def _handle_chat_query(self, event: Event) -> list[Event]:
        payload = ChatPMQueryPayload.model_validate(event.payload)
        user_id = payload.user_id
        trace_id = _trace_id(event)
        try:
            config = {
                "members": len(self._config.members),
                "projects": len(self._config.projects),
            }
            alerts = await self._alert.check_all()
            response = {
                "config_summary": config,
                "active_alerts": len(alerts),
                "alerts": alerts[:CHAT_ALERTS_PREVIEW],
            }
        except Exception as exc:
            logger.error(
                "chat_query_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                user_hash=hash_identifier(user_id),
                trace_id=trace_id,
            )
            response = request_error(
                f"Failed to retrieve PM status: {type(exc).__name__}",
                "pm_chat_query_failed",
            )
        return [
            self._event_factory.create_event(
                EventTypes.CHAT_PM_RESPONSE,
                {"user_id": user_id, "response": response},
                trace_id=trace_id,
            )
        ]

    async def _handle_decompose(self, event: Event) -> list[Event]:
        try:
            return await self._decomposition.handle_decompose(event)
        except Exception as exc:
            trace_id = _trace_id(event)
            logger.error("decomposition_failed", error=str(exc), trace_id=trace_id)
            failure_event = self._event_factory.create_event(
                EventTypes.PM_DECOMPOSITION_FAILED,
                {
                    "error": str(exc),
                    "trace_id": trace_id,
                    "requirement_title": event.payload.get("title", "Unknown"),
                },
                trace_id=trace_id,
            )
            try:
                await self._decomposition.publish_event_via_outbox(failure_event)
            except Exception as publish_error:
                logger.error(
                    "decomposition_failed_notify_failed",
                    error=str(publish_error),
                    trace_id=trace_id,
                )
            return []

    def _handle_coordinator_dispatch(self, event: Event) -> list[Event]:
        if event.payload.get("target_agent") == self._agent_id:
            logger.info(
                "coordinator_dispatch_received",
                task_id=event.payload.get("task_id"),
                workflow_id=event.payload.get("workflow_id"),
                instruction=event.payload.get("instruction"),
            )
        return []


def _trace_id(event: Event) -> str | None:
    return event.metadata.trace_id if event.metadata else None
