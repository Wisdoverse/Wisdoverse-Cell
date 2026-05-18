"""SQLAlchemy adapter for QA report persistence."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..core.report_store import QAReportStore
from ..models.qa import QAAcceptanceRun
from ..models.schemas import AcceptanceExecutionResult, QARunRequest
from .repository import AcceptanceResultRepository, AcceptanceRunRepository

logger = get_logger("qa_agent.report_store")


class SqlAlchemyQAReportStore(QAReportStore):
    """SQLAlchemy-backed QA report store."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = AcceptanceRunRepository(session)
        self.result_repo = AcceptanceResultRepository(session)

    async def save_execution_result(
        self,
        request: QARunRequest,
        result: AcceptanceExecutionResult,
        *,
        trace_id: str | None = None,
        trigger_event_id: str | None = None,
        notification_summary: dict[str, Any] | None = None,
    ) -> QAAcceptanceRun:
        """Persist an acceptance execution result to the database."""
        run = await self.run_repo.create(
            trace_id=trace_id,
            trigger_event_id=trigger_event_id,
            agent_name=request.agent_name,
            target_path=f"agents/{request.agent_name}",
            commit_sha=request.commit_sha,
            branch=request.branch,
            mr_iid=request.mr_iid,
            gitlab_project_id=request.gitlab_project_id,
            trigger=request.trigger,
            level=request.level,
            l0_status=result.summary.l0_gate,
            l1_status=result.summary.l1_check,
            l2_status=result.summary.l2_report,
            total_checks=result.summary.total_checks,
            l0_failure_count=result.summary.l0_failures,
            l1_warning_count=result.summary.l1_warnings,
            duration_seconds=result.duration_seconds,
            runner_exit_code=result.exit_code,
            files_changed=request.files_changed,
            raw_report=result.raw_report,
            report_markdown=result.report_markdown,
            notification_summary=notification_summary or {},
            completed_at=datetime.now(UTC),
        )

        if result.findings:
            finding_dicts = [
                {
                    "run_id": run.id,
                    "level": finding.level,
                    "category": finding.category,
                    "check_name": finding.check,
                    "status": finding.status,
                    "severity": finding.severity,
                    "is_blocking": finding.is_blocking,
                    "details": finding.details,
                    "file_path": finding.file,
                    "line_number": finding.line,
                }
                for finding in result.findings
            ]
            await self.result_repo.create_batch(finding_dicts)

        logger.info(
            "qa_run_persisted",
            run_id=run.id,
            agent_name=run.agent_name,
            l0_status=run.l0_status,
        )
        return run
