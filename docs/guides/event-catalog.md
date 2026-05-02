# Wisdoverse Cell 事件目录 (Event Catalog)

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **最后更新**: 2026-05-02
>
> **版本**: v1.0
>
> **维护者**: PJM Agent / Architecture Board

---

## 1. 概述

Wisdoverse Cell 采用**事件驱动架构 (Event-Driven Architecture)**，26 个 Agent 通过 Redis EventBus 进行异步通信。每个事件是不可变的、fire-and-forget 的消息，携带 `trace_id` 用于全链路追踪。

For the durable control-plane contract, start with [SPEC](../../SPEC.md).
For the operator API that emits and reads control-plane evidence, see
[API Reference: Control Plane API](./api-reference.md#control-plane-api). For
runtime switches and operational checks, see
[Operations: Control Plane Operations](./operations.md#9-control-plane-operations).

核心事件结构：

```python
Event(
    event_id="evt_{ulid}",
    event_type="{domain}.{action}",
    source_agent="agent-id",       # kebab-case
    payload={...},
    trace_id="trace_{ulid}"
)
```

### 命名规范

事件类型遵循 `{domain}.{action}` 模式：

| 组成部分 | 规则 | 示例 |
|---------|------|------|
| `domain` | 业务域名称，小写单数 | `requirement`, `sync`, `pm` |
| `action` | 动作描述，小写，连字符分隔 | `extracted`, `daily-generated`, `task-needs-decompose` |

---

## 2. 活跃事件总览

### 2.1 事件一览表

| 事件类型 | 发布者 | 消费者 | 说明 |
|---------|--------|--------|------|
| `requirement.extracted` | requirement-manager | — | 从会议中提取出需求 |
| `requirement.confirmed` | requirement-manager | — | 需求已被确认 |
| `requirement.rejected` | requirement-manager | — | 需求已被驳回 |
| `requirement.changed` | requirement-manager | — | 需求字段变更 |
| `requirement.deleted` | requirement-manager | — | 需求已删除 |
| `sync.started` | sync-agent | — | 同步任务开始 |
| `sync.completed` | sync-agent | pjm-agent, analysis-agent | 同步任务完成 |
| `sync.failed` | sync-agent | — | 同步任务失败 |
| `sync.trigger` | chat-agent | sync-agent | 触发同步（来自聊天） |
| `sync.task-needs-decompose` | sync-agent | pjm-agent | 任务需要分解 |
| `report.daily-generated` | analysis-agent | — | 日报已生成 |
| `report.weekly-generated` | analysis-agent | — | 周报已生成 |
| `analysis.risk-detected` | analysis-agent | pjm-agent | 检测到项目风险 |
| `analysis.quality-evaluated` | analysis-agent | — | 质量评估完成 |
| `pm.alert-triggered` | pjm-agent | — | PM 告警已触发 |
| `pm.decompose-completed` | pjm-agent | — | 任务分解完成 |
| `pm.decomposition_failed` | pjm-agent | — | 任务分解失败 |
| `pm.approval_timeout` | pjm-agent | — | 审批超时 |
| `chat.pm-query` | chat-agent | pjm-agent | 用户 PM 相关查询 |
| `chat.pm-response` | pjm-agent | chat-agent | PM 查询响应 |
| `channel.message.inbound` | channel_gateway | — | 收到外部消息 |
| `channel.message.outbound` | channel_gateway | — | 发送外部消息 |
| `channel.message.delivered` | channel_gateway | — | 消息已送达 |
| `channel.message.edited` | channel_gateway | — | 消息已编辑 |
| `channel.message.deleted` | channel_gateway | — | 消息已删除 |
| `channel.reaction.added` | channel_gateway | — | 添加表情回应 |
| `channel.reaction.removed` | channel_gateway | — | 移除表情回应 |
| `channel.read.receipt` | channel_gateway | — | 已读回执 |
| `channel.adapter.status` | channel_gateway | — | 适配器状态变更 |
| `goal.created` | control-plane API | operator console | Durable company goal created |
| `goal.updated` | control-plane API | operator console | Goal status or progress changed |
| `work_item.created` | control-plane API | operator console | Durable work item created |
| `work_item.updated` | control-plane API | operator console | Work item status or owner changed |
| `decision.created` | control-plane API | operator console | Durable decision created |
| `decision.updated` | control-plane API | operator console | Decision status changed |
| `agent_role.created` | control-plane API | operator console | Agent role definition created |
| `agent_role.status-updated` | control-plane API | operator console | Agent role status changed |
| `agent.wakeup-requested` | control-plane API | agent runtime adapter | Manual wakeup requested for an AgentRole |
| `agent.wakeup-completed` | control-plane agent runner | operator console | Manual wakeup finished or failed |
| `agent_run.started` | runtime plugin / agent runner | operator console | AgentRun lifecycle started |
| `agent_run.succeeded` | runtime plugin / agent runner | operator console | AgentRun completed successfully |
| `agent_run.failed` | runtime plugin / agent runner | operator console | AgentRun failed with error evidence |
| `budget.usage-recorded` | budget guard / LLM gateway | operator console | Budget usage appended |
| `artifact.created` | agents | operator console | Artifact produced by an agent |
| `audit.event-recorded` | control-plane ledger | operator console | Audit event appended |

---

## 3. Payload 详细定义

### 3.0 Control Plane Domain

Control-plane events connect the durable ledger with independently deployed
agents. They SHOULD include `company_id`, `trace_id`, and the most specific
available IDs among `goal_id`, `work_item_id`, and `run_id`.

#### `goal.created` / `goal.updated`

```json
{
  "company_id": "cmp_projectcell",
  "goal_id": "goal_...",
  "title": "Ship SPEC control plane",
  "status": "active",
  "parent_goal_id": null,
  "owner_agent_id": "pjm-agent",
  "owner_user_id": null,
  "current_value": 25,
  "target_value": 100
}
```

#### `work_item.created` / `work_item.updated`

```json
{
  "company_id": "cmp_projectcell",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "title": "Expose goal API",
  "status": "ready",
  "priority": "high",
  "owner_agent_id": "dev-agent",
  "owner_user_id": null,
  "source": "manual",
  "external_ref": "spec-goal-api"
}
```

#### `decision.created` / `decision.updated`

```json
{
  "company_id": "cmp_projectcell",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "run_id": "run_...",
  "decision_id": "dec_...",
  "title": "Accept run output",
  "status": "accepted",
  "selected_option": "accept",
  "decided_by": "human:operator"
}
```

#### `artifact.created`

```json
{
  "company_id": "cmp_projectcell",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "run_id": "run_...",
  "artifact_id": "art_...",
  "artifact_type": "run_walkthrough",
  "title": "Run walkthrough",
  "uri": "artifact://runs/run_...",
  "created_by_agent_id": "ops-runner"
}
```

#### `agent.wakeup-requested`

```json
{
  "company_id": "cmp_projectcell",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "actor_id": "human:operator",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "input": {}
}
```

#### `agent.wakeup-completed`

```json
{
  "company_id": "cmp_projectcell",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "status": "succeeded",
  "output": {},
  "error_category": null,
  "error_message": null
}
```

#### `agent_run.started` / `agent_run.succeeded` / `agent_run.failed`

```json
{
  "company_id": "cmp_projectcell",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "status": "running",
  "adapter_type": "http",
  "error_category": null,
  "error_message": null
}
```

#### `approval.requested` / `approval.granted` / `approval.rejected`

```json
{
  "company_id": "cmp_projectcell",
  "approval_id": "apr_...",
  "category": "technical",
  "status": "pending",
  "requested_by": "agent:dev-agent",
  "source_agent_id": "dev-agent",
  "proposed_action": "Run workflow",
  "risk": "External system mutation",
  "resolved_by": null,
  "run_id": "run_...",
  "trace_id": "trace_..."
}
```

#### `budget.usage-recorded`

```json
{
  "company_id": "cmp_projectcell",
  "usage_id": "busg_...",
  "budget_id": "bud_...",
  "scope": "agent",
  "scope_id": "dev-agent",
  "period": "daily",
  "cost_usd": 0.42,
  "model": "tool:agentforge_run",
  "input_tokens": 0,
  "output_tokens": 0,
  "run_id": "run_...",
  "trace_id": "trace_..."
}
```

#### `audit.event-recorded`

```json
{
  "company_id": "cmp_projectcell",
  "audit_event_id": "aud_...",
  "action": "agent_run.started",
  "target_type": "agent_run",
  "target_id": "run_...",
  "actor_type": "agent",
  "actor_id": "dev-agent",
  "idempotency_key": "agent_run.started:run_...",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "detail": {}
}
```

#### Control-plane producers, consumers, and idempotency keys

| Event | Producer | Consumer | Idempotency key |
|-------|----------|----------|-----------------|
| `goal.created` / `goal.updated` | control-plane API | operator console, coordinator | `goal.{action}:{goal_id}:{updated_at}` |
| `work_item.created` / `work_item.updated` | control-plane API, PJM agent | operator console, assigned agent | `work_item.{action}:{work_item_id}:{updated_at}` |
| `decision.created` / `decision.updated` | control-plane API, operator console | operator console, governance agents | `decision.{action}:{decision_id}:{updated_at}` |
| `artifact.created` | agent runtime, control-plane API | operator console, QA agent | `artifact.created:{artifact_id}` |
| `agent_role.created` / `agent_role.status-updated` | control-plane API | operator console, scheduler | `agent_role.{action}:{company_id}:{agent_id}:{updated_at}` |
| `agent.wakeup-requested` | control-plane API, heartbeat scheduler | agent runtime adapter | `agent.wakeup-requested:{run_id}` |
| `agent.wakeup-completed` | control-plane agent runner | operator console | `agent.wakeup-completed:{run_id}` |
| `agent_run.started` / `agent_run.succeeded` / `agent_run.failed` | runtime plugin, agent runner | operator console, budget/audit views | `agent_run.{state}:{run_id}` |
| `approval.requested` / `approval.granted` / `approval.rejected` | approval gate, operator console | operator console, blocked workflow owner | `approval.{state}:{approval_id}` |
| `budget.usage-recorded` | LLM gateway, ToolRegistry budget guard | operator console, finance governance | `budget.usage-recorded:{usage_id}` |
| `audit.event-recorded` | control-plane repository | operator console, compliance export | `audit.event-recorded:{audit_event_id}` |

### 3.1 Requirement 域

#### `requirement.extracted`

```json
{
  "meeting_id": "string",
  "requirement_ids": ["string"],
  "count": "int",
  "requirements": [
    {
      "id": "string",
      "title": "string",
      "description": "string"
    }
  ]
}
```

#### `requirement.confirmed`

```json
{
  "requirement_id": "string",
  "title": "string",
  "priority": "string",         // e.g. "P0", "P1", "P2"
  "category": "string",
  "confirmed_by": "string",
  "confirmed_at": "datetime"    // ISO 8601
}
```

#### `requirement.rejected`

```json
{
  "requirement_id": "string",
  "title": "string",
  "reason": "string",
  "rejected_at": "datetime"
}
```

#### `requirement.changed`

```json
{
  "requirement_id": "string",
  "title": "string",
  "changed_fields": ["string"],  // 变更的字段名列表
  "changed_by": "string",
  "changed_at": "datetime"
}
```

#### `requirement.deleted`

```json
{
  "requirement_id": "string",
  "title": "string",
  "deleted_by": "string",
  "deleted_at": "datetime"
}
```

### 3.2 Sync 域

#### `sync.started`

```json
{
  "triggered_by": "string"      // "scheduler" | "manual" | "api" | "chat_tool"
}
```

#### `sync.completed`

```json
{
  "synced_count": "int",
  "errors": [
    {
      "item": "string",
      "message": "string"
    }
  ]
}
```

#### `sync.failed`

```json
{
  "error": "string"
}
```

#### `sync.trigger`

```json
{
  "triggered_by": "string"      // 触发来源标识
}
```

#### `sync.task-needs-decompose`

```json
{
  "wp_id": "string",
  "subject": "string",
  "description": "string",
  "wp_type": "string",
  "project_id": "string",
  "project_name": "string",
  "assignee": "string",
  "assignee_id": "string"
}
```

### 3.3 Report / Analysis 域

#### `report.daily-generated` / `report.weekly-generated`

```json
{
  "date": "string",             // "2026-03-07"
  "summary": "string"
}
```

#### `analysis.risk-detected`

```json
{
  "risks": [
    {
      "risk_id": "string",
      "level": "string",        // "high" | "medium" | "low"
      "description": "string"
    }
  ]
}
```

#### `analysis.quality-evaluated`

```json
{
  "evaluations": [
    {
      "item": "string",
      "score": "float",
      "details": "string"
    }
  ]
}
```

### 3.4 PM 域

#### `pm.alert-triggered`

```json
{
  "alert_count": "int",
  "alerts": [
    {
      "type": "string",
      "message": "string",
      "severity": "string"
    }
  ],
  "push_ok": "bool"
}
```

#### `pm.decompose-completed`

```json
{
  "wp_id": "string",
  "status": "string",
  "user_story_count": "int",
  "task_count": "int"
}
```

#### `pm.decomposition_failed`

```json
{
  "error": "string",
  "trace_id": "string",
  "requirement_title": "string"
}
```

#### `pm.approval_timeout`

```json
{
  "record_id": "string",
  "age_hours": "float"
}
```

### 3.5 Chat 域

#### `chat.pm-query`

```json
{
  "user_id": "string",
  "query": "string"
}
```

#### `chat.pm-response`

```json
{
  "user_id": "string",
  "response": {
    "answer": "string",
    "data": "object | null"
  }
}
```

---

## 4. 事件流程图

### 4.1 同步与任务分解流程

```
scheduler/API/chat_tool
        |
        v
  sync.started
        |
        v
  +-----------+     sync.completed      +----------------+
  | sync-agent| ----------------------> | pjm-agent       |
  |           |                         | analysis-agent |
  +-----------+                         +----------------+
        |
        | sync.task-needs-decompose
        v
  +-----------+     pm.decompose-completed
  | pjm-agent  | ----------------------------->  (完成)
  |           |
  |           |     pm.decomposition_failed
  |           | ----------------------------->  (失败告警)
  +-----------+
```

### 4.2 聊天查询流程

```
  用户消息
     |
     v
  +-----------+   chat.pm-query    +-----------+
  | chat-agent| -----------------> | pjm-agent  |
  +-----------+                    +-----------+
       ^                                |
       |       chat.pm-response         |
       +--------------------------------+
```

### 4.3 需求提取流程

```
  会议录音上传
       |
       v
  meeting.uploaded (待实现)
       |
       v
  +---------------------+   requirement.extracted
  | requirement-manager  | ----------------------->  (待确认列表)
  +---------------------+
       |
       +--- requirement.confirmed ---> (进入开发)
       |
       +--- requirement.rejected  ---> (归档)
```

---

## 5. 生产者/消费者关系矩阵

```
                  requirement  sync    pm     analysis  chat   channel
                  .* events    .* evt  .* evt .* evt    .* evt .* evt
                  ─────────    ──────  ────── ────────  ────── ──────
requirement-mgr   Pub          -       -      -         -      -
sync-agent        -            Pub     -      -         -      -
pjm-agent          -            Sub     Pub    Sub       Pub*   -
analysis-agent    -            Sub     -      Pub       -      -
chat-agent        -            Pub*    -      -         Pub/Sub -
channel_gateway   -            -       -      -         -      Pub

Pub  = 发布者
Sub  = 消费者
Pub* = 仅发布该域的部分事件
```

**详细订阅关系**：

| Agent | 发布事件 | 订阅事件 |
|-------|---------|---------|
| requirement-manager | `requirement.*` | `project.created`, `project.updated`, `sprint.started`, `sprint.completed`, `meeting.uploaded` |
| sync-agent | `sync.started`, `sync.completed`, `sync.failed`, `sync.task-needs-decompose` | (scheduler/API 触发，无事件订阅) |
| pjm-agent | `pm.*`, `chat.pm-response` | `sync.completed`, `sync.task-needs-decompose`, `analysis.risk-detected`, `chat.pm-query` |
| analysis-agent | `report.*`, `analysis.*` | `sync.completed` |
| chat-agent | `chat.pm-query`, `sync.trigger` | `chat.pm-response` |
| channel_gateway | `channel.*` | — |
| evolution-agent | `evolution.skill-proposed`, `evolution.pattern-proposed` | `evolution.cycle-triggered`, `evolution.human-feedback`, `evolution.pattern-approved` |

---

## 6. 进化系统事件

### 6.1 事件一览表

| 事件类型 | 发布者 | 消费者 | 说明 |
|---------|--------|--------|------|
| `execution.traced` | evolved-agent (wrapper) | evolution-agent | 执行追踪已记录 |
| `evolution.cycle-triggered` | scheduler / API | evolution-agent | 触发全局进化分析周期 |
| `evolution.skill-proposed` | evolution-agent | — (human review) | 技能优化提案 |
| `evolution.human-feedback` | gateway / admin UI | evolution-agent | 人工审批进化提案 |
| `evolution.pattern-proposed` | evolution-agent | — (human review) | 协作模式提案 (L3) |
| `evolution.pattern-approved` | gateway / admin UI | evolution-agent | 协作模式已审批 (L3) |
| `evolution.pattern-shadow-complete` | shadow-runner | evolution-agent | 影子运行完成 (L3) |

### 6.2 Payload 详细定义

#### `execution.traced`

```json
{
  "trace_id": "string",
  "agent_id": "string",
  "event_type": "string",
  "success": "bool",
  "duration_ms": "float",
  "skill_used": "string | null",
  "skill_version": "int | null",
  "llm_calls": [
    {
      "model_id": "string",
      "prompt_tokens": "int",
      "completion_tokens": "int",
      "latency_ms": "float",
      "cost_usd": "float"
    }
  ]
}
```

#### `evolution.cycle-triggered`

```json
{
  "days": "int"
}
```

#### `evolution.skill-proposed`

```json
{
  "agent_id": "string",
  "skill_id": "string",
  "current_version": "int",
  "proposed_version": "int",
  "changes": {
    "system_prompt": "string | null",
    "parameters": "dict | null",
    "few_shot_examples": "list | null"
  },
  "evidence": ["string"],
  "expected_improvement": "float"
}
```

#### `evolution.human-feedback`

```json
{
  "proposal_id": "string",
  "approved": "bool",
  "user_id": "string",
  "comment": "string | null"
}
```

#### `evolution.pattern-proposed`

```json
{
  "pattern_id": "string",
  "name": "string",
  "trigger_event": "string",
  "steps": [
    {
      "step_id": "string",
      "agent_id": "string",
      "action": "string",
      "input_from": "string | null",
      "output_to": "string | null"
    }
  ]
}
```

#### `evolution.pattern-approved`

```json
{
  "pattern_id": "string",
  "user_id": "string",
  "approved": "bool"
}
```

#### `evolution.pattern-shadow-complete`

```json
{
  "pattern_id": "string",
  "trigger_event_id": "string",
  "total_duration_ms": "int",
  "steps": [
    {
      "step_id": "string",
      "agent_id": "string",
      "success": "bool",
      "duration_ms": "int"
    }
  ]
}
```

### 6.3 进化系统事件流程图

```
scheduler / API
       |
       v
evolution.cycle-triggered
       |
       v
+------------------+   evolution.skill-proposed    +----------------+
| evolution-agent  | -----------------------------> | human review   |
|                  |                                +----------------+
|                  |   evolution.pattern-proposed          |
|                  | -----------------------------> (L3)   |
+------------------+                                      |
       ^                                                  |
       |         evolution.human-feedback                 |
       +--------------------------------------------------+
       ^
       |         evolution.pattern-approved (L3)
       +--------------------------------------------------+

EvolvedAgent wrapper (any agent):
  handle_event() ---> execution.traced ---> DB persistence
```

---

## 7. QA 验收事件

QA Agent 消费代码事件并产生验收结果事件。

| 事件类型 | 生产者 | 消费者 | Payload | 说明 |
|---------|--------|--------|---------|------|
| `code.committed` | CI Pipeline / GitLab Webhook | qa-agent | `{commit_sha, branch, files_changed, mr_iid?}` | 代码提交，触发 QA 验收 |
| `qa.acceptance_completed` | qa-agent | pjm-agent | `{run_id, level, status, summary, agent_name?, commit_sha?}` | 验收运行完成 |
| `qa.acceptance_failed` | qa-agent | pjm-agent | `{run_id, level, failures[], agent_name?, commit_sha?}` | 验收未通过，含失败详情 |

## 8. 预留事件（Reserved）

以下事件已在系统中定义但尚未实现，供未来扩展使用：

| 域 | 事件类型 | 用途 |
|----|---------|------|
| code | `code.reviewed` | 代码审查 |
| feature | `feature.completed` | 功能完成 |
| test | `test.passed`, `test.failed` | 测试结果 |
| deployment | `deployment.started`, `deployment.completed` | 部署流程 |
| device | `device.online`, `device.offline`, `device.alert` | 设备管理 |
| lead | `lead.qualified` | 线索管理 |
| deal | `deal.won` | 交易管理 |
| ticket | `ticket.created` | 工单管理 |
| approval | `approval.requested`, `approval.granted`, `approval.rejected` | 审批流程 |

## 9. 已订阅但未发布的事件

以下事件已被 Agent 订阅但目前无生产者，需在相关功能上线时补齐：

| 事件类型 | 订阅者 | 状态 |
|---------|--------|------|
| `project.created` | requirement-manager | 待实现 |
| `project.updated` | requirement-manager | 待实现 |
| `sprint.started` | requirement-manager | 待实现 |
| `sprint.completed` | requirement-manager | 待实现 |
| `meeting.uploaded` | requirement-manager | 待实现 |
