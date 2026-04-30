from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AcceptanceFinding(BaseModel):
    """单条验收发现项"""

    model_config = ConfigDict(strict=True)

    level: Literal["L0", "L1", "L2"]
    category: str
    check: str
    status: Literal["PASS", "FAIL", "WARN", "INFO", "SKIP"]
    details: str | None = None
    file: str | None = None
    line: int | None = None
    severity: Literal["critical", "high", "medium", "low", "info"] = "info"
    is_blocking: bool = False


class AcceptanceSummary(BaseModel):
    """验收汇总"""

    model_config = ConfigDict(strict=True)

    l0_gate: Literal["PASS", "FAIL", "ERROR"]
    l1_check: Literal["PASS", "WARN", "ERROR"]
    l2_report: Literal["INFO"] = "INFO"
    total_checks: int = Field(default=0, ge=0)
    l0_failures: int = Field(default=0, ge=0)
    l1_warnings: int = Field(default=0, ge=0)


class AcceptanceExecutionResult(BaseModel):
    """验收执行结果 (Runner 输出)"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    exit_code: int
    summary: AcceptanceSummary
    findings: list[AcceptanceFinding] = Field(default_factory=list)
    raw_report: dict[str, Any] = Field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float = Field(default=0, ge=0)
    report_markdown: str | None = None
    run_id: str = ""
    notification_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class QARunRequest(BaseModel):
    """QA 运行请求"""

    model_config = ConfigDict(strict=True)

    agent_name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    level: Literal["l0", "l1", "l2", "all"] = "all"
    commit_sha: str | None = Field(default=None, min_length=7, max_length=40)
    diff_ref: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    branch: str | None = None
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    trigger: Literal["event", "manual", "api", "scheduled"] = "api"
    requested_by: str = "system"
    reason: str | None = None


class QACheckAggregate(BaseModel):
    """检查项聚合统计"""

    check: str
    count: int


class QARunStats(BaseModel):
    """QA 运行统计"""

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
