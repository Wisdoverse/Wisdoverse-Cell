"""
PMAgent - 预警调度 + 任务拆解 Agent

订阅 sync.completed、analysis.risk-detected、chat.pm-query 和 sync.task-needs-decompose，
执行预警检查、风险推送、PM 查询响应和自动任务拆解。
"""

from datetime import UTC, datetime, timedelta
from typing import Optional

from shared.config import settings as app_settings
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.llm_gateway import llm_gateway
from shared.integrations.feishu.bitable import bitable_service
from shared.integrations.openproject.client import get_op_client
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..core.alert_service import AlertService
from ..core.config_service import PMConfigService
from ..core.decompose import DecomposeService
from ..core.decomposition_orchestrator import DecompositionOrchestrator
from ..core.op_writer import OPWriterService
from ..core.push_service import PushService
from ..core.report_service import ReportService
from ..db.database import DatabaseManager, db_manager
from ..db.repository import AlertLogRepository, DecompositionRepository
from ..models.schemas import ChatPMQueryPayload, RiskDetectedPayload

try:
    from ..app.metrics import ALERTS_TRIGGERED

    _metrics_available = True
except ImportError:
    _metrics_available = False

logger = get_logger("pjm_agent.service")

# --- Named constants (formerly magic numbers) ---
STALE_APPROVAL_HOURS = 24  # Hours before a pending approval is considered stale
CHAT_ALERTS_PREVIEW = 5  # Max alerts returned in chat query response


class PMAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
    ):
        super().__init__(
            agent_id="pjm-agent",
            agent_name="PJM Agent",
            subscribed_events=[
                EventTypes.SYNC_COMPLETED,
                EventTypes.ANALYSIS_RISK_DETECTED,
                EventTypes.CHAT_PM_QUERY,
                EventTypes.SYNC_TASK_NEEDS_DECOMPOSE,
                EventTypes.COORDINATOR_DISPATCH,
            ],
            published_events=[
                EventTypes.PM_ALERT_TRIGGERED,
                EventTypes.CHAT_PM_RESPONSE,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_TASKS_READY_FOR_DEV,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._config: PMConfigService | None = None
        self._alert: AlertService | None = None
        self._push: PushService | None = None
        self._decompose: DecomposeService | None = None
        self._op_writer: OPWriterService | None = None
        self._report: ReportService | None = None
        self._decomposition_orchestrator: DecompositionOrchestrator | None = None

    async def startup(self):
        logger.info("agent_starting", agent_id=self.agent_id)

        if app_settings.app_env == "development":
            await self._db_manager.create_tables()
            logger.info("database_initialized")

        await self._event_bus.connect()
        logger.info("event_bus_connected")

        self._config = PMConfigService(bitable_service)
        self._alert = AlertService(bitable_service, self._config)
        self._push = PushService()
        self._decompose = DecomposeService(llm_gateway)
        self._op_writer = OPWriterService(get_op_client())
        self._report = ReportService(get_op_client())
        self._decomposition_orchestrator = DecompositionOrchestrator(
            db_manager=self._db_manager,
            op_writer=self._op_writer,
            decompose_service=self._decompose,
            push_service=self._push,
            create_event_fn=self.create_event,
            event_bus=self._event_bus,
        )
        await self._config.refresh()

        # Event loop is managed by AgentRuntime.start_event_loop()
        # This ensures events go through EvolvedAgent for trace collection

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        logger.info("agent_stopping", agent_id=self.agent_id)
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        if event.event_type == EventTypes.SYNC_COMPLETED:
            return await self._run_alerts(event)
        if event.event_type == EventTypes.ANALYSIS_RISK_DETECTED:
            return await self._handle_risks(event)
        if event.event_type == EventTypes.CHAT_PM_QUERY:
            return await self._handle_chat_query(event)
        if event.event_type == EventTypes.SYNC_TASK_NEEDS_DECOMPOSE:
            return await self._handle_decompose(event)
        if event.event_type == EventTypes.COORDINATOR_DISPATCH:
            if event.payload.get("target_agent") == self.agent_id:
                logger.info(
                    "coordinator_dispatch_received",
                    task_id=event.payload.get("task_id"),
                    workflow_id=event.payload.get("workflow_id"),
                    instruction=event.payload.get("instruction"),
                )
            return []
        return []

    async def handle_request(self, request: dict) -> dict:
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "config":
            return {
                "members": self._config.members,
                "projects": self._config.projects,
                "rules": self._config.rules,
            }
        if action == "alerts":
            alerts = await self._alert.check_all()
            return {"alerts": alerts}
        if action == "refresh_config":
            await self._config.refresh()
            return {"status": "refreshed"}
        if action == "push_alerts":
            alerts = request.get("alerts", [])
            await self._push.push_alerts(alerts)
            return {"status": "pushed", "count": len(alerts)}
        if action == "retry_decompose":
            return await self._retry_decompose(request.get("wp_id"))
        if action == "get_decompose":
            return await self._get_decompose(request.get("wp_id"))
        if action == "daily_report":
            return await self._run_report("daily")
        if action == "weekly_report":
            return await self._run_report("weekly")
        if action == "check_stale_approvals":
            await self._check_stale_approvals()
            return {"status": "ok"}
        return {"error": "unknown action"}

    async def health_check(self) -> dict[str, bool]:
        """Public health check for readiness probes."""
        checks = {"database": False}
        try:
            if self._db_manager:
                from sqlalchemy import text

                async with self._db_manager.session() as session:
                    await session.execute(text("SELECT 1"))
                checks["database"] = True
        except Exception as e:
            logger.error("health_check_db_failed", error=str(e), error_type=type(e).__name__)
        checks["config_loaded"] = len(self._config.members) > 0 if self._config else False
        return checks

    async def _run_alerts(self, event: Event) -> list[Event]:
        events = []

        # 1. Check alerts
        try:
            alerts = await self._alert.check_all()
        except Exception as e:
            logger.error("pm_alert_check_failed", error=str(e), trace_id=event.metadata.trace_id)
            return events

        if not alerts:
            return events

        # 2. Push to Feishu
        push_ok = False
        try:
            push_ok = await self._push.push_alerts(alerts)
        except Exception as e:
            logger.error("pm_alert_push_failed", error=str(e), alert_count=len(alerts))

        # 3. Record metrics
        if _metrics_available:
            for a in alerts:
                ALERTS_TRIGGERED.labels(alert_type=a["type"], severity=a["severity"]).inc()

        # 4. Log to database
        try:
            async with self._db_manager.session() as session:
                repo = AlertLogRepository(session)
                for a in alerts:
                    await repo.create(
                        alert_type=a["type"],
                        target=a.get("task", ""),
                        message=a["message"],
                        severity=a["severity"],
                    )
        except Exception as e:
            logger.error("pm_alert_log_failed", error=str(e))

        # 5. Publish event (always, even if push failed)
        events.append(
            self.create_event(
                EventTypes.PM_ALERT_TRIGGERED,
                {"alert_count": len(alerts), "alerts": alerts, "push_ok": push_ok},
                trace_id=event.metadata.trace_id,
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
        except Exception as e:
            logger.warning("pm_risks_push_failed", error=str(e), count=len(risks))
        return []

    async def _handle_chat_query(self, event: Event) -> list[Event]:
        payload = ChatPMQueryPayload.model_validate(event.payload)
        user_id = payload.user_id
        try:
            config = {"members": len(self._config.members), "projects": len(self._config.projects)}
            alerts = await self._alert.check_all()
            response = {
                "config_summary": config,
                "active_alerts": len(alerts),
                "alerts": alerts[:CHAT_ALERTS_PREVIEW],
            }
        except Exception as e:
            logger.error(
                "chat_query_failed",
                error=str(e),
                error_type=type(e).__name__,
                user_id=user_id,
                trace_id=event.metadata.trace_id,
            )
            response = {"error": f"Failed to retrieve PM status: {type(e).__name__}"}
        return [
            self.create_event(
                EventTypes.CHAT_PM_RESPONSE,
                {"user_id": user_id, "response": response},
                trace_id=event.metadata.trace_id,
            )
        ]

    async def _handle_decompose(self, event: Event) -> list[Event]:
        """Delegate decomposition to the DecompositionOrchestrator."""
        try:
            return await self._decomposition_orchestrator.handle_decompose(event)
        except Exception as e:
            logger.error("decomposition_failed", error=str(e), trace_id=event.metadata.trace_id)
            # Notify via event bus so gateway can send Feishu message
            try:
                await self._event_bus.publish(
                    Event.create(
                        event_type=EventTypes.PM_DECOMPOSITION_FAILED,
                        source_agent="pjm-agent",
                        payload={
                            "error": str(e),
                            "trace_id": event.metadata.trace_id,
                            "requirement_title": event.payload.get("title", "Unknown"),
                        },
                    )
                )
            except Exception:
                pass
            return []

    async def _retry_decompose(self, wp_id: int | None) -> dict:
        """Delegate to DecompositionOrchestrator."""
        return await self._decomposition_orchestrator.retry_decompose(wp_id)

    async def _get_decompose(self, wp_id: int | None) -> dict:
        """Delegate to DecompositionOrchestrator."""
        return await self._decomposition_orchestrator.get_decompose(wp_id)

    async def _run_report(self, report_type: str) -> dict:
        try:
            if report_type == "weekly":
                result = await self._report.generate_weekly()
            else:
                result = await self._report.generate_daily()
            await self._report.push_card(result["card"])
            return {"status": "sent", "total": result["stats"]["total"]}
        except Exception as e:
            logger.error("report_failed", report_type=report_type, error=str(e))
            return {"error": str(e)}

    async def _check_stale_approvals(self) -> None:
        """Scan for decomposition records pending > 24 hours and send a reminder."""
        try:
            async with self._db_manager.session() as session:
                repo = DecompositionRepository(session)
                stale = await repo.get_stale_pending(older_than_hours=STALE_APPROVAL_HOURS)
            if not stale:
                return
            logger.info("stale_approvals_found", count=len(stale))
            for record in stale:
                subject = (record.decompose_result or {}).get("summary", f"WP#{record.wp_id}")
                try:
                    await self._push.send_stale_approval_reminder(
                        wp_id=record.wp_id,
                        subject=subject,
                    )
                except Exception as e:
                    logger.warning(
                        "stale_approval_reminder_failed", wp_id=record.wp_id, error=str(e)
                    )
        except Exception as e:
            logger.error("stale_approvals_check_failed", error=str(e))

    async def check_approval_timeouts(self):
        """Scan for pending approvals older than 24h and send reminders."""
        async with self._db_manager.session() as session:
            repo = DecompositionRepository(session)
            # Get all pending records older than 24h
            pending = await repo.get_stale_pending(older_than_hours=STALE_APPROVAL_HOURS)
            now = datetime.now(UTC)
            for record in pending:
                if hasattr(record, "created_at") and record.created_at:
                    age = now - record.created_at
                    if age > timedelta(hours=STALE_APPROVAL_HOURS):
                        logger.warning(
                            "approval_timeout",
                            record_id=record.id,
                            age_hours=age.total_seconds() / 3600,
                        )
                        # Send reminder via event bus
                        try:
                            from shared.schemas.event import Event, EventTypes

                            await self._event_bus.publish(
                                Event.create(
                                    event_type=EventTypes.PM_APPROVAL_TIMEOUT,
                                    source_agent="pjm-agent",
                                    payload={
                                        "record_id": str(record.id),
                                        "age_hours": round(age.total_seconds() / 3600, 1),
                                    },
                                )
                            )
                        except Exception as e:
                            logger.error("approval_timeout_notify_failed", error=str(e))

    async def approve_decomposition(self, wp_id: int, approved_by: str) -> dict | None:
        """Delegate to DecompositionOrchestrator."""
        return await self._decomposition_orchestrator.approve_decomposition(wp_id, approved_by)

    async def reject_decomposition(
        self, wp_id: int, rejected_by: str, reason: str = ""
    ) -> dict | None:
        """Delegate to DecompositionOrchestrator."""
        return await self._decomposition_orchestrator.reject_decomposition(
            wp_id, rejected_by, reason=reason
        )


agent = PMAgent()


def get_agent() -> PMAgent:
    return agent
