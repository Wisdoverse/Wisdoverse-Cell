"""Application use cases for QA acceptance execution."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import Any, Protocol

from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceFinding,
    AcceptanceSummary,
    QARunRequest,
)
from .report_store import QAReportStore
from .run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore

logger = get_logger("qa_agent.acceptance_execution")


class QAExecutionSessionManagerPort(Protocol):
    """Database session manager required for one acceptance execution."""

    def session(self) -> AbstractAsyncContextManager[Any]:
        """Return an async session context manager."""


class QAAcceptanceRunnerPort(Protocol):
    """Runs acceptance checks and returns structured/markdown reports."""

    async def run_json(
        self,
        agent_name: str,
        *,
        level: str,
        diff_ref: str | None = None,
        mr_id: str = "",
    ) -> dict[str, Any]:
        """Run acceptance and return a JSON-compatible report."""

    async def run_markdown(self, agent_name: str, *, level: str) -> str | None:
        """Run acceptance and return markdown output for comments."""


class QANotifierPort(Protocol):
    """Notification boundary for acceptance results."""

    async def notify_all(self, **kwargs: Any) -> dict[str, Any]:
        """Notify all configured channels."""


StageQAEvent = Callable[[Any, Event], Any]
PublishStagedQAEvents = Callable[[list[Event], str | None], Any]
QAReportStoreFactory = Callable[[Any], QAReportStore]
RecordQAMetrics = Callable[[str, str, AcceptanceExecutionResult], None]


class QAAcceptanceExecutionUseCase:
    """Run acceptance checks, persist results, publish events, and notify."""

    def __init__(
        self,
        *,
        db_manager: QAExecutionSessionManagerPort,
        runner: QAAcceptanceRunnerPort,
        notifier: QANotifierPort,
        run_store: QAAcceptanceRunStore,
        report_store_factory: QAReportStoreFactory,
        stage_event: StageQAEvent,
        publish_staged_events: PublishStagedQAEvents,
        record_metrics: RecordQAMetrics,
        duplicate_persist_error_types: tuple[type[BaseException], ...] = (),
    ) -> None:
        self._db_manager = db_manager
        self._runner = runner
        self._notifier = notifier
        self._run_store = run_store
        self._report_store_factory = report_store_factory
        self._stage_event = stage_event
        self._publish_staged_events = publish_staged_events
        self._record_metrics = record_metrics
        self._duplicate_persist_error_types = duplicate_persist_error_types

    async def run_acceptance(
        self,
        request: QARunRequest,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
    ) -> AcceptanceExecutionResult:
        """Run acceptance from event/API paths with idempotent persistence."""
        agent_name = request.agent_name
        logger.info(
            "acceptance_start",
            agent_name=agent_name,
            trigger=request.trigger,
            level=request.level,
        )

        existing_run = await self._get_existing_event_run(trigger_event_id)
        if existing_run is not None:
            logger.info(
                "qa_run_replay_skipped",
                trigger_event_id=trigger_event_id,
                run_id=existing_run.id,
                agent_name=existing_run.agent_name,
            )
            return result_from_run(existing_run)

        result, summary_data, findings_data, report_md = await self._run_checks(
            request,
            agent_name,
        )
        try:
            run_id, staged_events = await self._persist_result(
                request,
                result,
                summary_data,
                findings_data,
                report_md,
                trace_id=trace_id,
                trigger_event_id=trigger_event_id,
            )
        except Exception as exc:
            if not isinstance(exc, self._duplicate_persist_error_types):
                raise
            existing_run = await self._get_existing_event_run(trigger_event_id)
            if existing_run is not None:
                logger.info(
                    "qa_run_replay_race_skipped",
                    trigger_event_id=trigger_event_id,
                    run_id=existing_run.id,
                    agent_name=existing_run.agent_name,
                )
                return result_from_run(existing_run)
            logger.error(
                "persist_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                agent_name=agent_name,
            )
            run_id = None
            staged_events = []

        result.run_id = run_id or ""
        eventbus_summary = await self._publish_staged_events(staged_events, run_id)
        notification_summary = await self._notify(
            request,
            agent_name,
            result,
            summary_data,
            findings_data,
            report_md,
            run_id=run_id,
            trace_id=trace_id,
            eventbus_summary=eventbus_summary,
        )
        result.notification_summary = notification_summary

        self._record_metrics(agent_name, request.trigger, result)

        logger.info(
            "acceptance_complete",
            agent_name=agent_name,
            l0=result.summary.l0_gate,
            l1=result.summary.l1_check,
            duration=result.duration_seconds,
            run_id=run_id,
        )
        return result

    async def _run_checks(
        self,
        request: QARunRequest,
        agent_name: str,
    ) -> tuple[AcceptanceExecutionResult, dict[str, Any], list[dict[str, Any]], str | None]:
        mr_id_str = f"!{request.mr_iid}" if request.mr_iid else ""
        report = await self._runner.run_json(
            agent_name,
            level=request.level,
            diff_ref=request.diff_ref,
            mr_id=mr_id_str,
        )

        report_md = None
        if request.mr_iid:
            report_md = await self._runner.run_markdown(
                agent_name,
                level=request.level,
            )

        summary_data = report.get("summary", {})
        findings_data = report.get("results", [])
        result = AcceptanceExecutionResult(
            success=summary_data.get("l0_gate") != "FAIL",
            exit_code=report.get("exit_code", -1),
            summary=AcceptanceSummary(
                l0_gate=summary_data.get("l0_gate", "ERROR"),
                l1_check=summary_data.get("l1_check", "ERROR"),
                l2_report=summary_data.get("l2_report", "INFO"),
                total_checks=summary_data.get("total_checks", 0),
                l0_failures=summary_data.get("l0_failures", 0),
                l1_warnings=summary_data.get("l1_warnings", 0),
            ),
            findings=[
                AcceptanceFinding(
                    level=f.get("level", "L0"),
                    category=f.get("category", ""),
                    check=f.get("check", ""),
                    status=f.get("status", "SKIP"),
                    details=f.get("details"),
                    file=f.get("file"),
                    line=f.get("line"),
                    severity=derive_severity(f),
                    is_blocking=f.get("level") == "L0" and f.get("status") == "FAIL",
                )
                for f in findings_data
            ],
            raw_report=report,
            stdout=report.get("stdout"),
            stderr=report.get("stderr"),
            duration_seconds=report.get("duration_seconds", 0),
            report_markdown=report_md,
        )
        return result, summary_data, findings_data, report_md

    async def _persist_result(
        self,
        request: QARunRequest,
        result: AcceptanceExecutionResult,
        summary_data: dict[str, Any],
        findings_data: list[dict[str, Any]],
        report_md: str | None,
        *,
        trace_id: str | None,
        trigger_event_id: str | None,
    ) -> tuple[str | None, list[Event]]:
        try:
            async with self._db_manager.session() as session:
                store = self._report_store_factory(session)
                run = await store.save_execution_result(
                    request,
                    result,
                    trace_id=trace_id,
                    trigger_event_id=trigger_event_id,
                )
                staged_events = build_acceptance_events(
                    run_id=run.id,
                    request=request,
                    result=result,
                    summary=summary_data,
                    findings=findings_data,
                    report_markdown=report_md,
                    trace_id=trace_id,
                )
                for event in staged_events:
                    await self._stage_event(session, event)
                return run.id, staged_events
        except Exception as exc:
            if isinstance(exc, self._duplicate_persist_error_types):
                raise
            logger.error(
                "persist_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                agent_name=request.agent_name,
            )
            return None, []

    async def _notify(
        self,
        request: QARunRequest,
        agent_name: str,
        result: AcceptanceExecutionResult,
        summary_data: dict[str, Any],
        findings_data: list[dict[str, Any]],
        report_md: str | None,
        *,
        run_id: str | None,
        trace_id: str | None,
        eventbus_summary: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            notification_summary = await self._notifier.notify_all(
                run_id=run_id,
                agent_name=agent_name,
                summary=summary_data,
                findings=findings_data,
                duration_seconds=result.duration_seconds,
                commit_sha=request.commit_sha,
                mr_iid=request.mr_iid,
                gitlab_project_id=request.gitlab_project_id,
                trigger=request.trigger,
                level=request.level,
                target=f"agents/{agent_name}",
                report_markdown=report_md,
                trace_id=trace_id,
                eventbus_summary=eventbus_summary,
            )
            await self._update_notification_summary(run_id, notification_summary)
            return notification_summary
        except Exception as exc:
            logger.error(
                "notify_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                agent_name=agent_name,
                run_id=run_id,
            )
            return {"_error": str(exc)}

    async def _update_notification_summary(
        self,
        run_id: str | None,
        notification_summary: dict[str, Any],
    ) -> None:
        if not run_id:
            return
        try:
            updated = await self._run_store.update_notification_summary(
                run_id,
                notification_summary,
            )
            if not updated:
                logger.warning("notification_summary_run_not_found", run_id=run_id)
        except Exception as exc:
            logger.warning(
                "notification_summary_update_failed",
                error=str(exc),
                run_id=run_id,
            )

    async def _get_existing_event_run(
        self,
        trigger_event_id: str | None,
    ) -> QAAcceptanceRunRecord | None:
        if not trigger_event_id:
            return None
        return await self._run_store.get_by_trigger_event_id(trigger_event_id)

def build_acceptance_events(
    *,
    run_id: str,
    request: QARunRequest,
    result: AcceptanceExecutionResult,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    report_markdown: str | None,
    trace_id: str | None,
) -> list[Event]:
    """Build QA integration events for a persisted acceptance run."""
    completed_payload = {
        "run_id": run_id,
        "agent_name": request.agent_name,
        "commit_sha": request.commit_sha,
        "mr_iid": request.mr_iid,
        "gitlab_project_id": request.gitlab_project_id,
        "trigger": request.trigger,
        "level": request.level,
        "target": f"agents/{request.agent_name}",
        "summary": summary,
        "findings": findings,
        "duration_seconds": result.duration_seconds,
        "report_markdown": report_markdown,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    events = [
        Event.create(
            event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
            source_agent="qa-agent",
            payload=completed_payload,
            trace_id=trace_id,
        )
    ]

    if summary.get("l0_gate") == "FAIL":
        blocking = [
            finding
            for finding in findings
            if finding.get("level") == "L0" and finding.get("status") == "FAIL"
        ]
        events.append(
            Event.create(
                event_type=EventTypes.QA_GATE_FAILED,
                source_agent="qa-agent",
                payload={
                    "run_id": run_id,
                    "agent_name": request.agent_name,
                    "commit_sha": request.commit_sha,
                    "mr_iid": request.mr_iid,
                    "gitlab_project_id": request.gitlab_project_id,
                    "l0_failure_count": summary.get("l0_failures", 0),
                    "blocking_findings": blocking[:10],
                    "duration_seconds": result.duration_seconds,
                    "report_markdown": report_markdown,
                },
                trace_id=trace_id,
            )
        )
    return events


def result_from_run(run: QAAcceptanceRunRecord) -> AcceptanceExecutionResult:
    """Rebuild an execution result from a persisted run."""
    raw_report = run.raw_report or {}
    findings = []
    for finding in raw_report.get("results", []) or []:
        try:
            findings.append(
                AcceptanceFinding(
                    level=finding.get("level", "L0"),
                    category=finding.get("category", ""),
                    check=finding.get("check", ""),
                    status=finding.get("status", "SKIP"),
                    details=finding.get("details"),
                    file=finding.get("file"),
                    line=finding.get("line"),
                    severity=finding.get("severity", "info"),
                    is_blocking=bool(finding.get("is_blocking", False)),
                )
            )
        except Exception as exc:
            logger.warning(
                "qa_replay_finding_decode_failed",
                run_id=run.id,
                error_type=type(exc).__name__,
            )

    return AcceptanceExecutionResult(
        success=run.l0_status != "FAIL",
        exit_code=run.runner_exit_code,
        summary=AcceptanceSummary(
            l0_gate=run.l0_status,
            l1_check=run.l1_status,
            l2_report=run.l2_status,
            total_checks=run.total_checks,
            l0_failures=run.l0_failure_count,
            l1_warnings=run.l1_warning_count,
        ),
        findings=findings,
        raw_report=raw_report,
        duration_seconds=run.duration_seconds,
        report_markdown=run.report_markdown,
        run_id=run.id,
        notification_summary=run.notification_summary or {},
    )


def derive_severity(finding: dict[str, Any]) -> str:
    """Map level + status to severity for notification filtering."""
    level = finding.get("level", "")
    status = finding.get("status", "")
    if level == "L0" and status == "FAIL":
        return "critical"
    if level == "L1" and status == "WARN":
        return "medium"
    if level == "L2":
        return "info"
    return "low"
