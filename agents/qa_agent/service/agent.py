"""QAAgent — automated acceptance verification for AI-generated code.

Subscribes to code.committed and qa.run-requested events.
Orchestrates: validate → run → persist → notify → metrics.
Returns [] from handle_event (side effects only, no response events in return list).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.exc import IntegrityError

from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventMetadata, EventTypes
from shared.utils.logger import get_logger

from ..core.acceptance_execution_use_cases import (
    QAAcceptanceExecutionUseCase,
    build_acceptance_events,
    derive_severity,
    result_from_run,
)
from ..core.acceptance_runner import AcceptanceRunnerService
from ..core.event_use_cases import QAEventUseCase
from ..core.health_ports import QAHealthStore
from ..core.health_use_cases import QAHealthUseCase
from ..core.notifier import QANotifier
from ..core.outbox_ports import QAEventOutboxStore
from ..core.request_use_cases import QARequestUseCase
from ..core.run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyQAHealthStore
from ..db.outbox_store import SqlAlchemyQAEventOutboxStore
from ..db.report_store import SqlAlchemyQAReportStore as QAReportStore
from ..db.run_store import SqlAlchemyQAAcceptanceRunStore
from ..models.schemas import (
    AcceptanceExecutionResult,
    QARunRequest,
    QARunStats,
)
from .notifier_factory import build_qa_core_config, build_qa_notifier

logger = get_logger("qa_agent.service")


class QAAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
        event_publisher: Optional[EventPublisher] = None,
        runner: Optional[AcceptanceRunnerService] = None,
        notifier: Optional[QANotifier] = None,
        outbox_store: QAEventOutboxStore | None = None,
        run_store: QAAcceptanceRunStore | None = None,
        health_store: QAHealthStore | None = None,
    ):
        super().__init__(
            agent_id="qa-agent",
            agent_name="QA Agent",
            subscribed_events=[
                EventTypes.CODE_COMMITTED,
                EventTypes.QA_RUN_REQUESTED,
            ],
            published_events=[
                EventTypes.QA_ACCEPTANCE_COMPLETED,
                EventTypes.QA_GATE_FAILED,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._event_publisher = event_publisher or EventBusEventPublisher(self._event_bus)
        self._outbox_store = outbox_store or SqlAlchemyQAEventOutboxStore(
            self._db_manager
        )
        self._run_store = run_store or SqlAlchemyQAAcceptanceRunStore(self._db_manager)
        self._health_store = health_store or SqlAlchemyQAHealthStore(self._db_manager)
        core_config = build_qa_core_config() if runner is None or notifier is None else None
        self._runner = runner or AcceptanceRunnerService(config=core_config)
        self._notifier = notifier or build_qa_notifier(
            bus=self._event_bus,
            config=core_config,
        )

    async def startup(self) -> None:
        logger.info("qa_agent_starting")

    async def shutdown(self) -> None:
        logger.info("qa_agent_shutting_down")
        try:
            await self._db_manager.close()
        except Exception as e:
            logger.warning("db_close_failed", error=str(e))

    async def handle_event(self, event: Event) -> list[Event]:
        """Process events — side effects only, return empty list."""
        return await self._event_use_case().handle(event)

    def _event_use_case(self) -> QAEventUseCase:
        return QAEventUseCase(runner=self)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle API/RPC requests."""
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        return await self._request_use_case().handle(request)

    def _request_use_case(self) -> QARequestUseCase:
        return QARequestUseCase(self)

    async def health_check(self) -> dict[str, bool]:
        return await self._health_use_case().check()

    def _health_use_case(self) -> QAHealthUseCase:
        return QAHealthUseCase(health_store=self._health_store)

    # ---------------------------------------------------------------
    # Public orchestration methods (shared by event + API paths)
    # ---------------------------------------------------------------

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        return await self._acceptance_execution_use_case().run_acceptance(
            request,
            trace_id=trace_id,
            trigger_event_id=trigger_event_id,
        )

    def _acceptance_execution_use_case(self) -> QAAcceptanceExecutionUseCase:
        return QAAcceptanceExecutionUseCase(
            db_manager=self._db_manager,
            runner=self._runner,
            notifier=self._notifier,
            run_store=self._run_store,
            report_store_factory=QAReportStore,
            stage_event=self._stage_qa_event,
            publish_staged_events=self._publish_staged_qa_events_for_use_case,
            record_metrics=self._record_metrics,
            duplicate_persist_error_types=(IntegrityError,),
        )

    async def _publish_staged_qa_events_for_use_case(
        self,
        events: list[Event],
        run_id: str | None,
    ) -> dict[str, Any]:
        return await self._publish_staged_qa_events(events, run_id=run_id)

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        runs = await self._run_store.list_runs(
            agent_name=agent_name,
            limit=limit,
            offset=offset,
        )
        return [
            {
                "id": r.id,
                "run_id": r.id,
                "agent_name": r.agent_name,
                "commit_sha": r.commit_sha,
                "mr_iid": r.mr_iid,
                "trigger": r.trigger,
                "l0_status": r.l0_status,
                "l1_status": r.l1_status,
                "total_checks": r.total_checks,
                "duration_seconds": r.duration_seconds,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in runs
        ]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = await self._run_store.get_by_id(run_id)
        if not run:
            return None
        return {
            "id": run.id,
            "run_id": run.id,
            "agent_name": run.agent_name,
            "commit_sha": run.commit_sha,
            "mr_iid": run.mr_iid,
            "trigger": run.trigger,
            "level": run.level,
            "files_changed": run.files_changed or [],
            "summary": {
                "l0_gate": run.l0_status,
                "l1_check": run.l1_status,
                "l2_report": run.l2_status,
                "total_checks": run.total_checks,
                "l0_failures": run.l0_failure_count,
                "l1_warnings": run.l1_warning_count,
            },
            "findings": run.raw_report.get("results", []) if run.raw_report else [],
            "raw_report": run.raw_report or {},
            "report_markdown": run.report_markdown,
            "notification_summary": run.notification_summary or {},
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        return await self._run_store.get_stats(agent_name=agent_name, days=days)

    async def publish_pending_qa_events(self, limit: int = 100) -> dict[str, int]:
        """
        Retry pending QA outbox events.

        This stays as an application use case so runtime plugins, workers, or
        admin operations do not need to know persistence details.
        """
        rows = await self._outbox_store.list_pending(limit=limit)

        published = 0
        failed = 0
        for row in rows:
            event = self._event_from_outbox(row)
            try:
                ok = await self._event_publisher.publish(event)
                if not ok:
                    raise RuntimeError("event_bus_publish_returned_false")
                await self._mark_qa_event_published(event)
                published += 1
            except Exception as exc:
                await self._mark_qa_event_failed(event, exc)
                failed += 1

        logger.info(
            "qa_outbox_dispatch_completed",
            total=len(rows),
            published=published,
            failed=failed,
        )
        return {"total": len(rows), "published": published, "failed": failed}

    async def publish_event_via_outbox(self, event: Event) -> bool:
        """Stage a runtime-produced QA event before EventBus delivery."""
        await self._outbox_store.add(event)
        result = await self._publish_staged_qa_events([event], run_id=None)
        return bool(result.get("sent"))

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    async def _stage_qa_event(self, session, event: Event) -> Event:
        """Persist an integration event in the local QA outbox."""
        await self._outbox_store.stage(session, event)
        return event

    def _event_from_outbox(self, row) -> Event:
        """Rebuild an immutable Event from a QA outbox row."""
        return Event(
            event_id=row.event_id,
            event_type=row.event_type,
            timestamp=row.created_at,
            source_agent=row.source_agent,
            payload=row.payload,
            schema_version=row.schema_version,
            metadata=EventMetadata(
                trace_id=row.trace_id,
                correlation_id=row.correlation_id,
                retry_count=row.retry_count,
            ),
        )

    async def _publish_staged_qa_events(
        self,
        events: list[Event],
        *,
        run_id: str | None,
    ) -> dict[str, Any]:
        """Publish outbox-staged QA events after the local transaction commits."""
        if not events:
            return {"sent": False, "reason": "no_events"}

        published = 0
        failed = 0
        for event in events:
            try:
                ok = await self._event_publisher.publish(event)
                if not ok:
                    raise RuntimeError("event_bus_publish_returned_false")
                await self._mark_qa_event_published(event)
                published += 1
            except Exception as exc:
                await self._mark_qa_event_failed(event, exc)
                logger.error(
                    "qa_event_publish_failed",
                    event_id=event.event_id,
                    event_type=event.event_type,
                    run_id=run_id,
                    error=str(exc),
                )
                failed += 1

        return {
            "sent": failed == 0,
            "published": published,
            "failed": failed,
        }

    async def _mark_qa_event_published(self, event: Event) -> None:
        """Best-effort mark for a successfully published outbox event."""
        try:
            await self._outbox_store.mark_published(event.event_id)
        except Exception as exc:
            logger.warning(
                "qa_outbox_mark_published_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                error=str(exc),
            )

    async def _mark_qa_event_failed(self, event: Event, error: Exception) -> None:
        """Best-effort failure recording for an outbox event publish attempt."""
        try:
            await self._outbox_store.mark_failed(event.event_id, str(error))
        except Exception as exc:
            logger.warning(
                "qa_outbox_mark_failed_failed",
                event_id=event.event_id,
                event_type=event.event_type,
                publish_error=str(error),
                error=str(exc),
            )

    def _build_acceptance_events(
        self,
        *,
        run_id: str,
        request: QARunRequest,
        result: AcceptanceExecutionResult,
        summary: dict,
        findings: list[dict],
        report_markdown: str | None,
        trace_id: str | None,
    ) -> list[Event]:
        return build_acceptance_events(
            run_id=run_id,
            request=request,
            result=result,
            summary=summary,
            findings=findings,
            report_markdown=report_markdown,
            trace_id=trace_id,
        )

    @staticmethod
    def _result_from_run(run: QAAcceptanceRunRecord) -> AcceptanceExecutionResult:
        return result_from_run(run)

    @staticmethod
    def _derive_severity(finding: dict) -> str:
        return derive_severity(finding)

    @staticmethod
    def _record_metrics(
        agent_name: str,
        trigger: str,
        result: AcceptanceExecutionResult,
    ) -> None:
        try:
            from ..app.metrics import ACCEPTANCE_DURATION, ACCEPTANCE_RUNS

            if ACCEPTANCE_RUNS:
                ACCEPTANCE_RUNS.labels(
                    agent_name=agent_name,
                    trigger=trigger,
                    l0_status=result.summary.l0_gate,
                ).inc()
            if ACCEPTANCE_DURATION:
                ACCEPTANCE_DURATION.labels(
                    agent_name=agent_name,
                ).observe(result.duration_seconds)
        except Exception as e:
            logger.warning("metrics_recording_failed", error=str(e), error_type=type(e).__name__)


agent = QAAgent()


def get_agent() -> QAAgent:
    return agent
