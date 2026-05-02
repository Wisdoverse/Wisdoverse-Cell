"""
Event Schema - Agent间通信的标准事件格式

所有Agent之间的通信都通过Event进行，这是系统的"语言"。
"""
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..utils.id_generator import generate_id


class EventMetadata(BaseModel):
    """事件元数据"""
    trace_id: Optional[str] = None      # 追踪ID，用于关联一系列事件
    retry_count: int = 0                 # 重试次数
    correlation_id: Optional[str] = None # 关联ID，用于请求-响应模式


class Event(BaseModel):
    """
    标准事件格式

    事件类型命名规范: {domain}.{action}
    - requirement.extracted  需求已提取
    - requirement.confirmed  需求已确认
    - requirement.changed    需求已变更
    - code.committed        代码已提交
    - test.passed           测试通过
    - device.alert          设备告警
    """

    model_config = ConfigDict(
        ser_json_timedelta="iso8601",
    )

    # 必填字段
    event_id: str = Field(default_factory=lambda: generate_id("evt"))
    event_type: str                      # 格式: {domain}.{action}
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_agent: str                    # 发送事件的Agent ID
    payload: dict[str, Any]              # 事件负载数据
    schema_version: str = "1.0"          # 事件 schema 版本，用于向前兼容

    # 可选字段
    metadata: EventMetadata = Field(default_factory=EventMetadata)

    @classmethod
    def create(
        cls,
        event_type: str,
        source_agent: str,
        payload: dict[str, Any],
        trace_id: Optional[str] = None
    ) -> "Event":
        """创建事件的便捷方法"""
        return cls(
            event_type=event_type,
            source_agent=source_agent,
            payload=payload,
            metadata=EventMetadata(trace_id=trace_id)
        )


# 预定义的事件类型常量
class EventTypes:
    """事件类型常量"""

    # 需求相关
    REQUIREMENT_EXTRACTED = "requirement.extracted"
    REQUIREMENT_CONFIRMED = "requirement.confirmed"
    REQUIREMENT_CHANGED = "requirement.changed"
    REQUIREMENT_REJECTED = "requirement.rejected"
    REQUIREMENT_DELETED = "requirement.deleted"

    # 开发相关
    CODE_COMMITTED = "code.committed"
    CODE_REVIEWED = "code.reviewed"
    FEATURE_COMPLETED = "feature.completed"

    # 测试相关
    TEST_PASSED = "test.passed"
    TEST_FAILED = "test.failed"

    # 交付相关
    DEPLOYMENT_STARTED = "deployment.started"
    DEPLOYMENT_COMPLETED = "deployment.completed"

    # 运维相关
    DEVICE_ONLINE = "device.online"
    DEVICE_OFFLINE = "device.offline"
    DEVICE_ALERT = "device.alert"

    # 客户相关
    LEAD_QUALIFIED = "lead.qualified"
    DEAL_WON = "deal.won"
    TICKET_CREATED = "ticket.created"

    # 审批相关
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_REJECTED = "approval.rejected"

    # Control-plane ledger
    GOAL_CREATED = "goal.created"
    GOAL_UPDATED = "goal.updated"
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    DECISION_CREATED = "decision.created"
    DECISION_UPDATED = "decision.updated"
    AGENT_ROLE_CREATED = "agent_role.created"
    AGENT_ROLE_STATUS_UPDATED = "agent_role.status-updated"
    AGENT_WAKEUP_REQUESTED = "agent.wakeup-requested"
    AGENT_WAKEUP_COMPLETED = "agent.wakeup-completed"
    AGENT_RUN_STARTED = "agent_run.started"
    AGENT_RUN_SUCCEEDED = "agent_run.succeeded"
    AGENT_RUN_FAILED = "agent_run.failed"
    BUDGET_USAGE_RECORDED = "budget.usage-recorded"
    ARTIFACT_CREATED = "artifact.created"
    AUDIT_EVENT_RECORDED = "audit.event-recorded"

    # PM 同步相关
    SYNC_STARTED = "sync.started"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"
    SYNC_TRIGGER = "sync.trigger"

    # 分析报告相关
    REPORT_DAILY_GENERATED = "report.daily-generated"
    REPORT_WEEKLY_GENERATED = "report.weekly-generated"
    ANALYSIS_RISK_DETECTED = "analysis.risk-detected"
    ANALYSIS_QUALITY_EVALUATED = "analysis.quality-evaluated"

    # PM 预警相关
    PM_ALERT_TRIGGERED = "pm.alert-triggered"

    # PM 任务拆解相关
    SYNC_TASK_NEEDS_DECOMPOSE = "sync.task-needs-decompose"
    PM_DECOMPOSE_COMPLETED = "pm.decompose-completed"
    PM_DECOMPOSITION_FAILED = "pm.decomposition-failed"
    PM_APPROVAL_TIMEOUT = "pm.approval-timeout"

    # QA 验收相关
    QA_RUN_REQUESTED = "qa.run-requested"
    QA_ACCEPTANCE_COMPLETED = "qa.acceptance-completed"
    QA_GATE_FAILED = "qa.gate-failed"

    # 聊天相关
    CHAT_PM_QUERY = "chat.pm-query"
    CHAT_PM_RESPONSE = "chat.pm-response"

    # Evolution system
    EXECUTION_TRACED = "execution.traced"
    EVOLUTION_CYCLE_TRIGGERED = "evolution.cycle-triggered"
    EVOLUTION_SKILL_PROPOSED = "evolution.skill-proposed"
    EVOLUTION_HUMAN_FEEDBACK = "evolution.human-feedback"

    # Collaboration events
    EVOLUTION_PATTERN_PROPOSED = "evolution.pattern-proposed"
    EVOLUTION_PATTERN_APPROVED = "evolution.pattern-approved"
    EVOLUTION_PATTERN_SHADOW_COMPLETE = "evolution.pattern-shadow-complete"

    # Dead Letter Queue
    DLQ_FAILED = "dlq.failed"

    # Dev Agent 相关
    PM_TASKS_READY_FOR_DEV = "pm.tasks-ready-for-dev"
    DEV_WORKFLOW_CREATED = "dev.workflow-created"
    DEV_WORKFLOW_COMPLETED = "dev.workflow-completed"
    DEV_MR_CREATED = "dev.mr-created"
    DEV_TASK_COMPLETED = "dev.task-completed"
    DEV_TASK_FAILED = "dev.task-failed"

    # Coordinator 编排相关
    COORDINATOR_COMMAND = "coordinator.command"
    COORDINATOR_RESPONSE = "coordinator.response"
    COORDINATOR_DISPATCH = "coordinator.dispatch"
    TASK_NOTIFICATION = "task.notification"
    TASK_PROGRESS = "task.progress"
    PM_PRD_READY = "pm.prd-ready"
