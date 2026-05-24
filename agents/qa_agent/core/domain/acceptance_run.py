"""AcceptanceRun aggregate root for QA acceptance execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from shared.core.identifiers import AcceptanceRunId

from .acceptance_verdict import AcceptanceVerdict
from .acceptance_vocabulary import is_blocking_finding


class InvalidAcceptanceRunError(ValueError):
    """Raised when an acceptance run violates domain invariants."""


class AcceptanceRunStatus(str, Enum):
    """Lifecycle states for one QA acceptance run."""

    REQUESTED = "requested"
    RUNNING = "running"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class AcceptanceRunCompleted:
    """In-memory domain event raised when an AcceptanceRun completes."""

    run_id: AcceptanceRunId
    agent_name: str
    commit_sha: str | None
    mr_iid: int | None
    gitlab_project_id: int | None
    trigger: str
    level: str
    target: str
    summary: Mapping[str, Any]
    findings: tuple[Mapping[str, Any], ...]
    verdict: AcceptanceVerdict
    duration_seconds: float
    report_markdown: str | None
    completed_at: datetime

    @property
    def blocking_findings(self) -> list[Mapping[str, Any]]:
        """Return findings that block the L0 gate."""
        return [
            finding
            for finding in self.findings
            if is_blocking_finding(
                level=str(finding.get("level", "")),
                status=str(finding.get("status", "")),
            )
        ]


@dataclass
class AcceptanceRun:
    """Aggregate root for one QA acceptance run lifecycle."""

    run_id: AcceptanceRunId
    agent_name: str
    commit_sha: str | None
    mr_iid: int | None
    gitlab_project_id: int | None
    trigger: str
    level: str
    target: str
    status: AcceptanceRunStatus
    requested_at: datetime
    started_at: datetime | None = None
    verdict: AcceptanceVerdict | None = None
    total_checks: int = 0
    duration_seconds: float = 0.0
    report_markdown: str | None = None
    completed_at: datetime | None = None
    _events: list[AcceptanceRunCompleted] = field(default_factory=list)

    @classmethod
    def request(
        cls,
        *,
        run_id: AcceptanceRunId,
        agent_name: str,
        commit_sha: str | None,
        mr_iid: int | None,
        gitlab_project_id: int | None,
        trigger: str,
        level: str,
        requested_at: datetime | None = None,
    ) -> AcceptanceRun:
        """Create a requested run aggregate before external checks start."""
        target = f"agents/{agent_name}"
        _validate_run_identity(
            run_id=run_id,
            agent_name=agent_name,
            target=target,
            trigger=trigger,
            level=level,
        )
        return cls(
            run_id=AcceptanceRunId(run_id),
            agent_name=agent_name,
            commit_sha=commit_sha,
            mr_iid=mr_iid,
            gitlab_project_id=gitlab_project_id,
            trigger=trigger,
            level=level,
            target=target,
            status=AcceptanceRunStatus.REQUESTED,
            requested_at=requested_at or datetime.now(UTC),
        )

    @classmethod
    def complete(
        cls,
        *,
        run_id: AcceptanceRunId,
        agent_name: str,
        commit_sha: str | None,
        mr_iid: int | None,
        gitlab_project_id: int | None,
        trigger: str,
        level: str,
        summary: Mapping[str, Any],
        findings: Sequence[Mapping[str, Any]],
        duration_seconds: float,
        report_markdown: str | None,
        completed_at: datetime | None = None,
    ) -> AcceptanceRun:
        """Create a completed run through the explicit lifecycle transitions."""
        completed_time = completed_at or datetime.now(UTC)
        run = cls.request(
            run_id=run_id,
            agent_name=agent_name,
            commit_sha=commit_sha,
            mr_iid=mr_iid,
            gitlab_project_id=gitlab_project_id,
            trigger=trigger,
            level=level,
            requested_at=completed_time,
        )
        run.start(started_at=completed_time)
        run.record_completion(
            summary=summary,
            findings=findings,
            duration_seconds=duration_seconds,
            report_markdown=report_markdown,
            completed_at=completed_time,
        )
        return run

    def start(self, *, started_at: datetime | None = None) -> None:
        """Move a requested run into the running state."""
        if self.status is not AcceptanceRunStatus.REQUESTED:
            raise InvalidAcceptanceRunError("only requested runs can start")
        self.status = AcceptanceRunStatus.RUNNING
        self.started_at = started_at or datetime.now(UTC)

    def record_completion(
        self,
        *,
        summary: Mapping[str, Any],
        findings: Sequence[Mapping[str, Any]],
        duration_seconds: float,
        report_markdown: str | None,
        completed_at: datetime | None = None,
    ) -> None:
        """Complete a running run and raise its completion event."""
        if self.status is not AcceptanceRunStatus.RUNNING:
            raise InvalidAcceptanceRunError("only running runs can complete")
        verdict = AcceptanceVerdict.from_summary(summary)
        total_checks = int(summary.get("total_checks", 0) or 0)
        _validate_completion(
            run_id=self.run_id,
            agent_name=self.agent_name,
            target=self.target,
            total_checks=total_checks,
            l0_failure_count=verdict.l0_failure_count,
            l1_warning_count=verdict.l1_warning_count,
            duration_seconds=duration_seconds,
        )
        completed_time = completed_at or datetime.now(UTC)
        self.status = AcceptanceRunStatus.COMPLETED
        self.verdict = verdict
        self.total_checks = total_checks
        self.duration_seconds = duration_seconds
        self.report_markdown = report_markdown
        self.completed_at = completed_time
        self._events.append(
            AcceptanceRunCompleted(
                run_id=self.run_id,
                agent_name=self.agent_name,
                commit_sha=self.commit_sha,
                mr_iid=self.mr_iid,
                gitlab_project_id=self.gitlab_project_id,
                trigger=self.trigger,
                level=self.level,
                target=self.target,
                summary=dict(summary),
                findings=tuple(dict(finding) for finding in findings),
                verdict=verdict,
                duration_seconds=self.duration_seconds,
                report_markdown=self.report_markdown,
                completed_at=completed_time,
            )
        )

    @property
    def is_blocking(self) -> bool:
        """Return whether this run blocks merge/release promotion."""
        return self.verdict.is_blocking if self.verdict is not None else False

    def pull_events(self) -> list[AcceptanceRunCompleted]:
        """Drain raised domain events for outbox staging."""
        drained = list(self._events)
        self._events.clear()
        return drained


def _validate_run_identity(
    *,
    run_id: AcceptanceRunId,
    agent_name: str,
    target: str,
    trigger: str,
    level: str,
) -> None:
    if not run_id:
        raise InvalidAcceptanceRunError("acceptance run requires run_id")
    if not agent_name:
        raise InvalidAcceptanceRunError("acceptance run requires agent_name")
    if not target.startswith("agents/"):
        raise InvalidAcceptanceRunError("acceptance run target must be agent-scoped")
    if not trigger:
        raise InvalidAcceptanceRunError("acceptance run requires trigger")
    if not level:
        raise InvalidAcceptanceRunError("acceptance run requires level")


def _validate_completion(
    *,
    run_id: AcceptanceRunId,
    agent_name: str,
    target: str,
    total_checks: int,
    l0_failure_count: int,
    l1_warning_count: int,
    duration_seconds: float,
) -> None:
    _validate_run_identity(
        run_id=run_id,
        agent_name=agent_name,
        target=target,
        trigger="completion",
        level="completion",
    )
    if duration_seconds < 0:
        raise InvalidAcceptanceRunError("duration_seconds must be non-negative")
    if total_checks < 0:
        raise InvalidAcceptanceRunError("total_checks must be non-negative")
    if l0_failure_count < 0:
        raise InvalidAcceptanceRunError("l0_failure_count must be non-negative")
    if l1_warning_count < 0:
        raise InvalidAcceptanceRunError("l1_warning_count must be non-negative")
    if l0_failure_count + l1_warning_count > total_checks:
        raise InvalidAcceptanceRunError("failure and warning counts cannot exceed total_checks")


__all__ = [
    "AcceptanceRun",
    "AcceptanceRunCompleted",
    "AcceptanceRunStatus",
    "InvalidAcceptanceRunError",
]
