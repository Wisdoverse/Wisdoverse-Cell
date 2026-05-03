"""QAAgent — automated acceptance verification for AI-generated code.

Subscribes to code.committed and qa.run-requested events.
Orchestrates: validate → run → persist → notify → metrics.
Returns [] from handle_event (side effects only, no response events in return list).
"""

from __future__ import annotations

from typing import Any, Optional

from shared.infra.event_bus import EventBus, event_bus
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.schemas.event_payloads import CodeCommittedPayload, QARunRequestedPayload
from shared.utils.logger import get_logger

from ..core.acceptance_runner import AcceptanceRunnerService
from ..core.notifier import QANotifier
from ..core.report_store import QAReportStore
from ..db.database import DatabaseManager, db_manager
from ..db.repository import AcceptanceRunRepository
from ..models.schemas import (
    AcceptanceExecutionResult,
    AcceptanceFinding,
    AcceptanceSummary,
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
        runner: Optional[AcceptanceRunnerService] = None,
        notifier: Optional[QANotifier] = None,
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
        if event.event_type == EventTypes.CODE_COMMITTED:
            await self._handle_code_committed(event)
        elif event.event_type == EventTypes.QA_RUN_REQUESTED:
            if event.payload.get("instruction"):
                logger.info(
                    "coordinator_instruction_received",
                    instruction=event.payload.get("instruction"),
                    workflow_id=event.payload.get("workflow_id"),
                )
            await self._handle_run_requested(event)
        return []

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle API/RPC requests."""
        standard_response = await self.handle_standard_request(request)
        if standard_response is not None:
            return standard_response

        action = request.get("action")
        if action == "run":
            req = QARunRequest(
                agent_name=request["agent_name"],
                level=request.get("level", "all"),
                commit_sha=request.get("commit_sha"),
                mr_iid=request.get("mr_iid"),
                gitlab_project_id=request.get("gitlab_project_id"),
                trigger="api",
                requested_by=request.get("requested_by", "api"),
            )
            result = await self.run_acceptance(req)
            return result.raw_report
        if action == "list_runs":
            runs = await self.list_runs(
                agent_name=request.get("agent_name"),
                limit=request.get("limit", 20),
                offset=request.get("offset", 0),
            )
            return {"items": runs}
        if action == "get_run":
            run = await self.get_run(request["run_id"])
            return run or {"error": "not found"}
        if action == "stats":
            stats = await self.get_stats(
                agent_name=request.get("agent_name"),
                days=request.get("days", 30),
            )
            return stats.model_dump()
        return {"error": "unknown action"}

    async def health_check(self) -> dict[str, bool]:
        checks = {"database": False}
        try:
            from sqlalchemy import text

            async with self._db_manager.session() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as e:
            logger.error(
                "health_check_db_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
        return checks

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
        """Core orchestration: run → persist → notify → metrics."""
        agent_name = request.agent_name
        logger.info(
            "acceptance_start",
            agent_name=agent_name,
            trigger=request.trigger,
            level=request.level,
        )

        # 1. Run acceptance checks
        # Issue #1 fix: use diff_ref (not commit_sha) for incremental checks
        mr_id_str = f"!{request.mr_iid}" if request.mr_iid else ""
        report = await self._runner.run_json(
            agent_name,
            level=request.level,
            diff_ref=request.diff_ref,
            mr_id=mr_id_str,
        )

        # Get markdown for MR comment (only if MR exists)
        report_md = None
        if request.mr_iid:
            report_md = await self._runner.run_markdown(
                agent_name,
                level=request.level,
            )

        # 2. Parse into domain model
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
                    severity=self._derive_severity(f),
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

        # 3. Persist — if this fails, log and continue with run_id=None
        run_id: str | None = None
        try:
            async with self._db_manager.session() as session:
                store = QAReportStore(session)
                run = await store.save_execution_result(
                    request,
                    result,
                    trace_id=trace_id,
                    trigger_event_id=trigger_event_id,
                )
                run_id = run.id
        except Exception as e:
            logger.error(
                "persist_failed",
                error=str(e),
                error_type=type(e).__name__,
                agent_name=agent_name,
            )
            run_id = None

        result.run_id = run_id or ""

        # 4. Notify all channels
        notification_summary: dict[str, Any] = {}
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
            )

            # Update notification_summary in DB
            if run_id:
                try:
                    async with self._db_manager.session() as session:
                        repo = AcceptanceRunRepository(session)
                        run_obj = await repo.get_by_id(run_id)
                        if run_obj:
                            run_obj.notification_summary = notification_summary
                        else:
                            logger.warning("notification_summary_run_not_found", run_id=run_id)
                except Exception as e:
                    logger.warning(
                        "notification_summary_update_failed",
                        error=str(e),
                        run_id=run_id,
                    )
        except Exception as e:
            logger.error(
                "notify_failed",
                error=str(e),
                error_type=type(e).__name__,
                agent_name=agent_name,
                run_id=run_id,
            )
            notification_summary = {"_error": str(e)}

        result.notification_summary = notification_summary

        # 5. Metrics
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

    async def list_runs(
        self,
        *,
        agent_name: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            runs = await repo.list_runs(
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
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            run = await repo.get_by_id(run_id)
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
        async with self._db_manager.session() as session:
            repo = AcceptanceRunRepository(session)
            return await repo.get_stats(agent_name=agent_name, days=days)

    # ---------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------

    async def _handle_code_committed(self, event: Event) -> None:
        payload = CodeCommittedPayload.model_validate(event.payload)
        request = QARunRequest(
            agent_name=payload.agent_name,
            level="all",
            commit_sha=payload.commit_sha,
            diff_ref=payload.diff_ref,
            files_changed=payload.files_changed,
            branch=payload.branch,
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            trigger="event",
            requested_by="code.committed",
        )
        await self.run_acceptance(
            request,
            trace_id=event.metadata.trace_id if event.metadata else None,
            trigger_event_id=event.event_id,
        )

    async def _handle_run_requested(self, event: Event) -> None:
        payload = QARunRequestedPayload.model_validate(event.payload)
        request = QARunRequest(
            agent_name=payload.agent_name,
            level=payload.level,
            commit_sha=payload.commit_sha,
            files_changed=payload.files_changed,
            mr_iid=payload.mr_iid,
            gitlab_project_id=payload.gitlab_project_id,
            trigger="event",
            requested_by=payload.requested_by,
            reason=payload.reason,
        )
        await self.run_acceptance(
            request,
            trace_id=event.metadata.trace_id if event.metadata else None,
            trigger_event_id=event.event_id,
        )

    @staticmethod
    def _derive_severity(finding: dict) -> str:
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
