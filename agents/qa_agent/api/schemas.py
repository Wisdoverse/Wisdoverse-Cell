from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models.schemas import AcceptanceFinding, AcceptanceSummary, QACheckAggregate


class QARunTriggerRequest(BaseModel):
    """POST /api/v1/qa/run request body."""

    model_config = ConfigDict(strict=True)

    agent_name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    level: Literal["l0", "l1", "l2", "all"] = "all"
    commit_sha: str | None = Field(default=None, min_length=7, max_length=40)
    files_changed: list[str] = Field(default_factory=list)
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    requested_by: str = "api"
    reason: str | None = None


class QARunTriggerResponse(BaseModel):
    """POST /api/v1/qa/run response body."""

    run_id: str
    status: Literal["passed", "failed", "warn", "error"]
    agent_name: str
    level: Literal["l0", "l1", "l2", "all"]
    summary: AcceptanceSummary
    duration_seconds: float
    notification_summary: dict[str, Any] = Field(default_factory=dict)


class QARunListItem(BaseModel):
    """GET /api/v1/qa/runs list item."""

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    mr_iid: int | None = None
    trigger: str
    l0_status: str
    l1_status: str
    total_checks: int
    duration_seconds: float
    created_at: datetime


class QARunListResponse(BaseModel):
    """GET /api/v1/qa/runs response body."""

    total: int
    items: list[QARunListItem]


class QARunDetailResponse(BaseModel):
    """GET /api/v1/qa/runs/{id} response body."""

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    trigger: str
    level: str
    summary: AcceptanceSummary
    findings: list[AcceptanceFinding] = Field(default_factory=list)
    raw_report: dict[str, Any]
    report_markdown: str | None = None
    notification_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: datetime | None = None


class QAStatsResponse(BaseModel):
    """GET /api/v1/qa/stats response body."""

    agent_name: str | None = None
    days: int
    total_runs: int
    pass_runs: int
    warn_runs: int
    failed_runs: int
    l0_fail_rate: float
    avg_duration_seconds: float
    top_l0_failures: list[QACheckAggregate] = Field(default_factory=list)
    top_l1_warnings: list[QACheckAggregate] = Field(default_factory=list)
