"""Application use cases for QA acceptance execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from shared.core.identifiers import AcceptanceRunId
from shared.core.ids import generate_ulid
from shared.schemas.event import Event, EventTypes
from shared.utils.logger import get_logger

from ..models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceFinding,
    AcceptanceSummary,
    QARunRequest,
)
from .domain.acceptance_run import AcceptanceRun, AcceptanceRunCompleted
from .domain.acceptance_verdict import AcceptanceVerdict
from .domain.acceptance_vocabulary import (
    FINDING_LEVEL_L0,
    FINDING_SKIP,
    is_blocking_finding,
    is_informational_finding,
    is_warning_finding,
)
from .run_store import QAAcceptanceRunRecord, QAAcceptanceRunStore
from .unit_of_work_ports import QAUnitOfWorkFactory

logger = get_logger("qa_agent.acceptance_execution")


def _new_acceptance_run_id() -> AcceptanceRunId:
    """Generate a QA acceptance run identity before persistence."""
    return AcceptanceRunId(generate_ulid())


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


RecordQAMetrics = Callable[[str, str, AcceptanceExecutionResult], None]
RunIdFactory = Callable[[], AcceptanceRunId]


class PublishStagedQAEvents(Protocol):
    """Publishes QA events already staged in the transactional outbox."""

    async def __call__(
        self,
        events: list[Event],
        *,
        run_id: AcceptanceRunId | None,
    ) -> dict[str, Any]:
        """Publish staged events for a persisted acceptance run."""


class QAAcceptanceExecutionUseCase:
    """Run acceptance checks, persist results, publish events, and notify."""

    def __init__(
        self,
        *,
        uow_factory: QAUnitOfWorkFactory,
        runner: QAAcceptanceRunnerPort,
        notifier: QANotifierPort,
        run_store: QAAcceptanceRunStore,
        publish_staged_events: PublishStagedQAEvents,
        record_metrics: RecordQAMetrics,
        run_id_factory: RunIdFactory | None = None,
        duplicate_persist_error_types: tuple[type[BaseException], ...] = (),
    ) -> None:
        self._uow_factory = uow_factory
        self._runner = runner
        self._notifier = notifier
        self._run_store = run_store
        self._publish_staged_events = publish_staged_events
        self._record_metrics = record_metrics
        self._run_id_factory = run_id_factory or _new_acceptance_run_id
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

        result.run_id = str(run_id or "")
        eventbus_summary = await self._publish_staged_events(
            staged_events,
            run_id=run_id,
        )
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
        verdict = AcceptanceVerdict.from_summary(summary_data)
        result = AcceptanceExecutionResult(
            success=not verdict.is_blocking,
            exit_code=report.get("exit_code", -1),
            summary=AcceptanceSummary(
                l0_gate=verdict.l0_gate,
                l1_check=verdict.l1_status,
                l2_report=verdict.l2_status,
                total_checks=summary_data.get("total_checks", 0),
                l0_failures=verdict.l0_failure_count,
                l1_warnings=verdict.l1_warning_count,
            ),
            findings=[
                AcceptanceFinding(
                    level=f.get("level", FINDING_LEVEL_L0),
                    category=f.get("category", ""),
                    check=f.get("check", ""),
                    status=f.get("status", FINDING_SKIP),
                    details=f.get("details"),
                    file=f.get("file"),
                    line=f.get("line"),
                    severity=derive_severity(f),
                    is_blocking=is_blocking_finding(
                        level=f.get("level", FINDING_LEVEL_L0),
                        status=f.get("status", FINDING_SKIP),
                    ),
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
    ) -> tuple[AcceptanceRunId | None, list[Event]]:
        try:
            aggregate = build_acceptance_run(
                run_id=self._run_id_factory(),
                request=request,
                result=result,
                summary=summary_data,
                findings=findings_data,
                report_markdown=report_md,
            )
            staged_events = build_acceptance_events_from_run(
                aggregate,
                trace_id=trace_id,
            )
            async with self._uow_factory() as uow:
                run = await uow.reports.save_execution_result(
                    request,
                    result,
                    run_id=aggregate.run_id,
                    trace_id=trace_id,
                    trigger_event_id=trigger_event_id,
                    completed_at=aggregate.completed_at,
                )
                run_id = AcceptanceRunId(run.id)
                if run_id != aggregate.run_id:
                    raise RuntimeError(
                        "persisted QA run id changed across the UOW boundary"
                    )
                for event in staged_events:
                    await uow.outbox.stage(event)
                await uow.commit()
                return run_id, staged_events
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
        run_id: AcceptanceRunId | None,
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
        run_id: AcceptanceRunId | None,
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
    run_id: AcceptanceRunId,
    request: QARunRequest,
    result: AcceptanceExecutionResult,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    report_markdown: str | None,
    trace_id: str | None,
) -> list[Event]:
    """Build QA integration events from an acceptance run aggregate."""
    aggregate = build_acceptance_run(
        run_id=run_id,
        request=request,
        result=result,
        summary=summary,
        findings=findings,
        report_markdown=report_markdown,
    )
    return build_acceptance_events_from_run(aggregate, trace_id=trace_id)


def build_acceptance_run(
    *,
    run_id: AcceptanceRunId,
    request: QARunRequest,
    result: AcceptanceExecutionResult,
    summary: dict[str, Any],
    findings: list[dict[str, Any]],
    report_markdown: str | None,
) -> AcceptanceRun:
    """Build and complete the domain aggregate before persistence."""
    aggregate = AcceptanceRun.request(
        run_id=run_id,
        agent_name=request.agent_name,
        commit_sha=request.commit_sha,
        mr_iid=request.mr_iid,
        gitlab_project_id=request.gitlab_project_id,
        trigger=request.trigger,
        level=request.level,
    )
    aggregate.start()
    aggregate.record_completion(
        summary=summary,
        findings=findings,
        duration_seconds=result.duration_seconds,
        report_markdown=report_markdown,
    )
    return aggregate


def build_acceptance_events_from_run(
    aggregate: AcceptanceRun,
    *,
    trace_id: str | None,
) -> list[Event]:
    """Translate aggregate-raised completion events into integration events."""
    [completion] = aggregate.pull_events()
    events = [
        Event.create(
            event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
            source_agent="qa-agent",
            payload=_completed_payload(completion),
            trace_id=trace_id,
        )
    ]

    if aggregate.is_blocking:
        events.append(
            Event.create(
                event_type=EventTypes.QA_GATE_FAILED,
                source_agent="qa-agent",
                payload=_gate_failed_payload(completion),
                trace_id=trace_id,
            )
        )
    return events


def _completed_payload(event: AcceptanceRunCompleted) -> dict[str, Any]:
    return {
        "run_id": str(event.run_id),
        "agent_name": event.agent_name,
        "commit_sha": event.commit_sha,
        "mr_iid": event.mr_iid,
        "gitlab_project_id": event.gitlab_project_id,
        "trigger": event.trigger,
        "level": event.level,
        "target": event.target,
        "summary": dict(event.summary),
        "findings": [dict(finding) for finding in event.findings],
        "duration_seconds": event.duration_seconds,
        "report_markdown": event.report_markdown,
        "completed_at": event.completed_at.isoformat(),
    }


def _gate_failed_payload(event: AcceptanceRunCompleted) -> dict[str, Any]:
    return {
        "run_id": str(event.run_id),
        "agent_name": event.agent_name,
        "commit_sha": event.commit_sha,
        "mr_iid": event.mr_iid,
        "gitlab_project_id": event.gitlab_project_id,
        "l0_failure_count": event.verdict.l0_failure_count,
        "blocking_findings": [dict(finding) for finding in event.blocking_findings[:10]],
        "duration_seconds": event.duration_seconds,
        "report_markdown": event.report_markdown,
    }


def result_from_run(run: QAAcceptanceRunRecord) -> AcceptanceExecutionResult:
    """Rebuild an execution result from a persisted run."""
    raw_report = run.raw_report or {}
    findings = []
    for finding in raw_report.get("results", []) or []:
        try:
            findings.append(
                AcceptanceFinding(
                    level=finding.get("level", FINDING_LEVEL_L0),
                    category=finding.get("category", ""),
                    check=finding.get("check", ""),
                    status=finding.get("status", FINDING_SKIP),
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

    verdict = AcceptanceVerdict(
        l0_gate=run.l0_status,
        l1_status=run.l1_status,
        l2_status=run.l2_status,
        l0_failure_count=run.l0_failure_count,
        l1_warning_count=run.l1_warning_count,
    )

    return AcceptanceExecutionResult(
        success=not verdict.is_blocking,
        exit_code=run.runner_exit_code,
        summary=AcceptanceSummary(
            l0_gate=verdict.l0_gate,
            l1_check=verdict.l1_status,
            l2_report=verdict.l2_status,
            total_checks=run.total_checks,
            l0_failures=verdict.l0_failure_count,
            l1_warnings=verdict.l1_warning_count,
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
    if is_blocking_finding(level=level, status=status):
        return "critical"
    if is_warning_finding(level=level, status=status):
        return "medium"
    if is_informational_finding(level=level, status=status):
        return "info"
    return "low"
