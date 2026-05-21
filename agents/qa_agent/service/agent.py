"""QAAgent — automated acceptance verification for AI-generated code.

Subscribes to code.committed and qa.run-requested events.
Orchestrates: validate → run → persist → notify → metrics.
Returns [] from handle_event (side effects only, no response events in return list).
"""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError

from shared.core import EventPublisher
from shared.infra.event_bus import EventBus, event_bus
from shared.infra.event_publisher import EventBusEventPublisher
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
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
from ..core.outbox_delivery_use_cases import QAOutboxDeliveryUseCase
from ..core.outbox_ports import QAEventOutboxStore
from ..core.request_use_cases import QARequestUseCase
from ..core.run_query_use_cases import QARunQueryUseCase
from ..core.run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore
from ..db.database import DatabaseManager, db_manager
from ..db.health_store import SqlAlchemyQAHealthStore
from ..db.outbox_store import SqlAlchemyQAEventOutboxStore
from ..db.report_store import SqlAlchemyQAReportStore as QAReportStore
from ..db.run_store import SqlAlchemyQAAcceptanceRunStore
from ..db.unit_of_work import SqlAlchemyQAUnitOfWorkFactory
from ..models.schemas import (
    AcceptanceExecutionResult,
    QARunRequest,
    QARunStats,
)
from .notifier_factory import build_qa_core_config, build_qa_notifier

logger = get_logger("qa_agent.service")


class _SessionQAOutboxWriter:
    """Compatibility outbox writer for mocked session factories in tests."""

    def __init__(self, stage_event, session) -> None:
        self._stage_event = stage_event
        self._session = session

    async def stage(self, event: Event) -> None:
        await self._stage_event(self._session, event)


class _SessionQAUnitOfWork:
    """Compatibility UOW for session factories without async_session."""

    def __init__(self, *, session, stage_event) -> None:
        self._session = session
        self.reports = QAReportStore(session)
        self.outbox = _SessionQAOutboxWriter(stage_event, session)
        self.completed = False

    async def commit(self) -> None:
        result = self._session.commit()
        if inspect.isawaitable(result):
            await result
        self.completed = True

    async def rollback(self) -> None:
        rollback = getattr(self._session, "rollback", None)
        if rollback is not None:
            result = rollback()
            if inspect.isawaitable(result):
                await result
        self.completed = True


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
            uow_factory=self._get_acceptance_unit_of_work,
            runner=self._runner,
            notifier=self._notifier,
            run_store=self._run_store,
            publish_staged_events=self._publish_staged_qa_events_for_use_case,
            record_metrics=self._record_metrics,
            duplicate_persist_error_types=(IntegrityError,),
        )

    def _get_acceptance_unit_of_work(self):
        """Open a QA acceptance unit-of-work context."""
        if "async_session" in vars(self._db_manager):
            return SqlAlchemyQAUnitOfWorkFactory(self._db_manager)()
        return self._session_acceptance_unit_of_work()

    @asynccontextmanager
    async def _session_acceptance_unit_of_work(self):
        async with self._db_manager.session() as session:
            uow = _SessionQAUnitOfWork(
                session=session,
                stage_event=self._stage_qa_event,
            )
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()

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
        return await self._run_query_use_case().list_runs(
            agent_name=agent_name,
            limit=limit,
            offset=offset,
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return await self._run_query_use_case().get_run(run_id)

    async def get_stats(
        self,
        *,
        agent_name: str | None = None,
        days: int = 30,
    ) -> QARunStats:
        return await self._run_query_use_case().get_stats(
            agent_name=agent_name,
            days=days,
        )

    def _run_query_use_case(self) -> QARunQueryUseCase:
        return QARunQueryUseCase(run_store=self._run_store)

    async def publish_pending_qa_events(self, limit: int = 100) -> dict[str, int]:
        return await self._outbox_delivery_use_case().publish_pending_events(
            limit=limit,
        )

    async def publish_event_via_outbox(self, event: Event) -> bool:
        return await self._outbox_delivery_use_case().publish_event_via_outbox(event)

    def _outbox_delivery_use_case(self) -> QAOutboxDeliveryUseCase:
        return QAOutboxDeliveryUseCase(
            outbox_store=self._outbox_store,
            event_publisher=self._event_publisher,
        )

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    async def _stage_qa_event(self, session, event: Event) -> Event:
        """Persist an integration event in the local QA outbox."""
        await self._outbox_store.stage(session, event)
        return event

    async def _publish_staged_qa_events(
        self,
        events: list[Event],
        *,
        run_id: str | None,
    ) -> dict[str, Any]:
        return await self._outbox_delivery_use_case().publish_staged_events(
            events,
            run_id=run_id,
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
