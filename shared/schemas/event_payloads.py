"""
Event Payloads - 事件 Payload 契约定义

定义各类事件的 payload 格式，供契约测试和类型检查使用。
其他 Agent 订阅事件时可参照这些模型。
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ============ 需求相关事件 ============

class RequirementSummary(BaseModel):
    """需求简要信息（用于列表）"""
    id: str
    title: str
    priority: str
    category: str


class RequirementExtractedPayload(BaseModel):
    """
    requirement.extracted 事件 payload

    当从会议中提取出需求时发布。
    """
    model_config = ConfigDict(strict=True)

    meeting_id: str = Field(..., description="来源会议 ID")
    requirement_ids: list[str] = Field(..., description="提取的需求 ID 列表")
    count: int = Field(..., ge=1, description="提取的需求数量")
    requirements: list[RequirementSummary] = Field(..., description="需求简要信息")


class RequirementConfirmedPayload(BaseModel):
    """
    requirement.confirmed 事件 payload

    当需求被人工确认时发布。
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="需求 ID")
    title: str = Field(..., description="需求标题")
    priority: str = Field(..., description="优先级")
    category: str = Field(..., description="分类")
    confirmed_by: str = Field(..., description="确认人")
    confirmed_at: str = Field(..., description="确认时间 (ISO format)")


class RequirementRejectedPayload(BaseModel):
    """
    requirement.rejected 事件 payload

    当需求被拒绝时发布。
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="需求 ID")
    title: str = Field(..., description="需求标题")
    reason: str = Field(..., description="拒绝原因")
    rejected_at: str = Field(..., description="拒绝时间 (ISO format)")


class RequirementChangedPayload(BaseModel):
    """
    requirement.changed 事件 payload

    当需求内容被修改时发布。
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="需求 ID")
    title: str = Field(..., description="需求标题")
    changed_fields: list[str] = Field(..., description="变更的字段列表")
    changed_by: str = Field(..., description="修改人")
    changed_at: str = Field(..., description="修改时间 (ISO format)")


class RequirementDeletedPayload(BaseModel):
    """
    requirement.deleted 事件 payload

    当需求被删除时发布。
    """
    model_config = ConfigDict(strict=True)

    requirement_id: str = Field(..., description="需求 ID")
    title: str = Field(..., description="需求标题")
    deleted_by: str = Field(..., description="删除人")
    deleted_at: str = Field(..., description="删除时间 (ISO format)")


# ============ PM 同步相关事件 ============

class SyncCompletedPayload(BaseModel):
    """sync.completed 事件 payload"""
    synced_count: int = 0
    errors: list[str] = []


class SyncFailedPayload(BaseModel):
    """sync.failed 事件 payload"""
    error: str


# ============ 分析报告相关事件 ============

class ReportGeneratedPayload(BaseModel):
    """report.daily-generated / report.weekly-generated 事件 payload"""
    date: str = ""
    summary: str = ""


class RiskDetectedPayload(BaseModel):
    """analysis.risk-detected 事件 payload"""
    risks: list[dict] = []


# ============ PM 预警相关事件 ============

class AlertTriggeredPayload(BaseModel):
    """pm.alert-triggered 事件 payload"""
    alert_count: int = 0
    alerts: list[dict] = []
    push_ok: bool = False


# ============ 聊天相关事件 ============

class ChatPmQueryPayload(BaseModel):
    """chat.pm-query 事件 payload"""
    user_id: str
    query: str = ""


class ChatPmResponsePayload(BaseModel):
    """chat.pm-response 事件 payload"""
    user_id: str
    response: dict = {}


# ============ PM 任务拆解相关事件 ============

class SyncTaskNeedsDecomposePayload(BaseModel):
    """sync.task-needs-decompose 事件 payload"""
    wp_id: int
    subject: str
    description: str = ""
    wp_type: str
    project_id: int
    project_name: str = ""
    assignee: str = ""
    assignee_id: int | None = None


class PMDecomposeCompletedPayload(BaseModel):
    """pm.decompose-completed 事件 payload"""
    wp_id: int
    status: str
    user_story_count: int = 0
    task_count: int = 0


# ============ QA 验收相关事件 ============

class AcceptanceFindingPayload(BaseModel):
    """单项检查结果"""
    model_config = ConfigDict(strict=True)

    level: Literal["L0", "L1", "L2"] = Field(..., description="检查级别")
    category: str = Field(..., description="security/architecture/quality/...")
    check: str = Field(..., description="检查项名称")
    status: Literal["PASS", "FAIL", "WARN", "INFO", "SKIP"] = Field(..., description="检查状态")
    details: str | None = Field(default=None, description="详细说明")
    file: str | None = Field(default=None, description="文件路径")
    line: int | None = Field(default=None, description="行号")
    severity: Literal["critical", "high", "medium", "low", "info"] = Field(
        default="info", description="严重级别"
    )
    is_blocking: bool = Field(default=False, description="是否触发 gate fail")


class AcceptanceSummaryPayload(BaseModel):
    """验收总结"""
    model_config = ConfigDict(strict=True)

    l0_gate: Literal["PASS", "FAIL", "ERROR"] = Field(..., description="L0 gate 状态")
    l1_check: Literal["PASS", "WARN", "ERROR"] = Field(..., description="L1 check 状态")
    l2_report: Literal["INFO"] = Field(default="INFO")
    total_checks: int = Field(default=0, ge=0)
    l0_failures: int = Field(default=0, ge=0)
    l1_warnings: int = Field(default=0, ge=0)


class CodeCommittedPayload(BaseModel):
    """code.committed 事件 payload"""
    model_config = ConfigDict(strict=True)

    agent_name: str = Field(..., pattern=r"^[a-z][a-z0-9_-]*$")
    commit_sha: str = Field(..., min_length=7, max_length=40)
    files_changed: list[str] = Field(default_factory=list)
    branch: str | None = None
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    diff_ref: str | None = None
    triggered_by: str = "event"


class QARunRequestedPayload(BaseModel):
    """qa.run-requested 事件 payload"""
    model_config = ConfigDict(strict=True)

    agent_name: str = Field(..., pattern=r"^[a-z][a-z0-9_-]*$")
    level: str = Field(default="all", description="l0/l1/l2/all")
    commit_sha: str | None = Field(default=None, min_length=7, max_length=40)
    files_changed: list[str] = Field(default_factory=list)
    mr_iid: int | None = Field(default=None, ge=1)
    gitlab_project_id: int | None = Field(default=None, ge=1)
    requested_by: str = Field(default="system")
    reason: str | None = None


class QAAcceptanceCompletedPayload(BaseModel):
    """qa.acceptance-completed 事件 payload"""
    model_config = ConfigDict(strict=True)

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    mr_iid: int | None = None
    gitlab_project_id: int | None = None
    trigger: str = Field(..., description="event/manual/api/scheduled")
    level: str = Field(default="all")
    target: str = Field(default="")
    summary: AcceptanceSummaryPayload
    findings: list[AcceptanceFindingPayload] = Field(default_factory=list)
    duration_seconds: float = Field(default=0, ge=0)
    report_markdown: str | None = None
    notification_summary: dict = Field(default_factory=dict)
    completed_at: str = Field(default="", description="ISO 8601")


class QAGateFailedPayload(BaseModel):
    """qa.gate-failed 事件 payload"""
    model_config = ConfigDict(strict=True)

    run_id: str
    agent_name: str
    commit_sha: str | None = None
    mr_iid: int | None = None
    gitlab_project_id: int | None = None
    l0_failure_count: int = Field(..., ge=0)
    blocking_findings: list[AcceptanceFindingPayload] = Field(
        default_factory=list,
    )
    duration_seconds: float = Field(default=0, ge=0)
    report_markdown: str | None = None


# ============ Dev Agent 相关事件 ============

class DevTaskInfo(BaseModel):
    """开发任务信息（嵌套模型，用于任务列表）"""
    model_config = ConfigDict(strict=True)

    id: int = Field(..., description="任务 ID (OP work package ID)")
    title: str = Field(..., description="任务标题")
    description: str = Field(default="", description="任务描述")
    estimated_hours: float = Field(default=8, ge=0, le=100, description="预估工时")
    parent_story: str = Field(default="", description="所属 User Story")
    related_files: list[str] = Field(default_factory=list, description="相关文件路径")


class PMTasksReadyForDevPayload(BaseModel):
    """pm.tasks-ready-for-dev 事件 payload"""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    tasks: list[DevTaskInfo] = Field(..., description="待开发任务列表", min_length=1)


class DevWorkflowCreatedPayload(BaseModel):
    """dev.workflow-created 事件 payload"""
    model_config = ConfigDict(strict=True)

    task_id: str = Field(..., description="任务 ID")
    workflow_id: str = Field(..., description="工作流 ID")
    node_count: int = Field(..., ge=1, description="工作流节点数")


class DevWorkflowCompletedPayload(BaseModel):
    """dev.workflow-completed 事件 payload"""
    model_config = ConfigDict(strict=True)

    task_id: str = Field(..., description="任务 ID")
    workflow_id: str = Field(..., description="工作流 ID")
    duration_s: float = Field(..., ge=0, description="执行耗时（秒）")


class DevMRCreatedPayload(BaseModel):
    """dev.mr-created 事件 payload"""
    model_config = ConfigDict(strict=True)

    mr_url: str = Field(..., description="MR 链接")
    wp_id: int = Field(..., description="Work Package ID")
    branch: str = Field(..., description="分支名")
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="MEDIUM", description="风险级别"
    )


class DevTaskCompletedPayload(BaseModel):
    """dev.task-completed 事件 payload"""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    mr_url: str = Field(..., description="MR 链接")
    duration_s: float = Field(..., ge=0, description="执行耗时（秒）")


class DevTaskFailedPayload(BaseModel):
    """dev.task-failed 事件 payload"""
    model_config = ConfigDict(strict=True)

    wp_id: int = Field(..., description="Work Package ID")
    error: str = Field(..., description="错误信息")
    failed_node: str | None = Field(default=None, description="失败的工作流节点")
    runbook_url: str | None = Field(default=None, description="运维手册链接")


# ============ 事件类型到 Payload 模型的映射 ============

EVENT_PAYLOAD_MODELS = {
    "requirement.extracted": RequirementExtractedPayload,
    "requirement.confirmed": RequirementConfirmedPayload,
    "requirement.rejected": RequirementRejectedPayload,
    "requirement.changed": RequirementChangedPayload,
    "requirement.deleted": RequirementDeletedPayload,
    "sync.completed": SyncCompletedPayload,
    "sync.failed": SyncFailedPayload,
    "report.daily-generated": ReportGeneratedPayload,
    "report.weekly-generated": ReportGeneratedPayload,
    "analysis.risk-detected": RiskDetectedPayload,
    "pm.alert-triggered": AlertTriggeredPayload,
    "chat.pm-query": ChatPmQueryPayload,
    "chat.pm-response": ChatPmResponsePayload,
    "sync.task-needs-decompose": SyncTaskNeedsDecomposePayload,
    "pm.decompose-completed": PMDecomposeCompletedPayload,
    "code.committed": CodeCommittedPayload,
    "qa.run-requested": QARunRequestedPayload,
    "qa.acceptance-completed": QAAcceptanceCompletedPayload,
    "qa.gate-failed": QAGateFailedPayload,
    "pm.tasks-ready-for-dev": PMTasksReadyForDevPayload,
    "dev.workflow-created": DevWorkflowCreatedPayload,
    "dev.workflow-completed": DevWorkflowCompletedPayload,
    "dev.mr-created": DevMRCreatedPayload,
    "dev.task-completed": DevTaskCompletedPayload,
    "dev.task-failed": DevTaskFailedPayload,
}


def validate_event_payload(event_type: str, payload: dict) -> BaseModel:
    """
    验证事件 payload 是否符合契约

    Args:
        event_type: 事件类型
        payload: 事件 payload

    Returns:
        验证后的 Pydantic 模型

    Raises:
        KeyError: 未知的事件类型
        ValidationError: payload 不符合契约
    """
    model = EVENT_PAYLOAD_MODELS.get(event_type)
    if model is None:
        raise KeyError(f"Unknown event type: {event_type}")
    return model.model_validate(payload)
