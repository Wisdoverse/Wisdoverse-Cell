# Wisdoverse Cell API Reference

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **版本**: v2026.05 | **最后更新**: 2026-05-02

Wisdoverse Cell 由多个 Agent 组成，每个 Agent 独立部署并暴露 REST API。本文档覆盖所有 Agent 的全部端点。

---

## 目录

- [认证方式](#认证方式)
- [错误响应格式](#错误响应格式)
- [通用端点 (所有 Agent)](#通用端点-所有-agent)
- [Control Plane API](#control-plane-api)
- [PJM Agent (port 8012)](#pjm-agent-port-8012)
- [Chat Agent (port 8013)](#chat-agent-port-8013)
- [Analysis Agent (port 8011)](#analysis-agent-port-8011)
- [Sync Agent (port 8010)](#sync-agent-port-8010)
- [Requirement Manager (port 8000)](#requirement-manager-port-8000)
- [Go Gateway (port 8080)](#go-gateway-port-8080)
- [Evolution Agent (standalone service)](#evolution-agent-standalone-service)
- [QA Agent (port 8014)](#qa-agent-port-8014)
- [Dev Agent (port 8015)](#dev-agent-port-8015)
- [DSAR 合规端点 (所有 Agent)](#dsar-合规端点-所有-agent)
- [AgentClient 服务间调用模式](#agentclient-服务间调用模式)

---

## 认证方式

| 方式 | Header / 机制 | 适用场景 |
|------|---------------|----------|
| X-Internal-Key | `X-Internal-Key: <shared_secret>` | Agent 间服务调用、管理端点、DSAR 端点 |
| 飞书签名验证 | `X-Lark-Request-Timestamp` + `X-Lark-Request-Nonce` + `X-Lark-Signature` | 飞书 webhook 回调 |
| 无认证 | - | 健康检查 (`/health`, `/health/ready`) |

**X-Internal-Key 验证逻辑** (`shared/middleware/internal_auth.py`):
- 使用 `hmac.compare_digest` 进行恒时比较
- 如果服务端未配置 `internal_service_key`（开发模式），则跳过验证

---

## 错误响应格式

所有 Agent 遵循统一错误结构：

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "需求不存在",
    "trace_id": "trace_01HXYZ..."
  }
}
```

FastAPI 标准 `HTTPException` 返回：

```json
{
  "detail": "需求不存在"
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 / 业务逻辑拒绝 |
| 401 | 认证失败 (X-Internal-Key 无效) |
| 403 | 飞书签名验证失败 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |
| 502 | 上游服务失败 (如同步触发失败) |
| 503 | 服务未就绪 (就绪检查失败) |

---

## 通用端点 (所有 Agent)

所有 Agent (PM / Chat / Analysis / Sync / Requirement Manager) 均提供以下端点：

### `GET /health`

- **认证**: 无
- **说明**: 存活检查（Liveness Probe）
- **响应**:
```json
{
  "status": "alive",
  "agent": "pjm-agent"
}
```
- **示例**:
```bash
curl http://localhost:8012/health
```

### `GET /health/ready`

- **认证**: 无
- **说明**: 就绪检查（Readiness Probe），包含各依赖组件状态。返回 `200` 表示就绪，`503` 表示降级。
- **响应**:
```json
{
  "status": "ready",
  "checks": {
    "redis": true,
    "database": true,
    "scheduler": true
  }
}
```
- **示例**:
```bash
curl http://localhost:8012/health/ready
```

### `POST /agent/request`

- **Auth**: `X-Internal-Key`
- **Purpose**: Generic internal request boundary for independently deployed
  agents created with `create_agent_app()`. The control-plane runner uses this
  endpoint for `http` adapter wakeups instead of importing agent service code.
- **Request body**:
```json
{
  "action": "wakeup",
  "agent_id": "ops-runner",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_...",
  "input": {}
}
```
- **Response**: Agent-specific JSON returned by `BaseAgent.handle_request()`.

---

## Control Plane API

These endpoints are mounted under `/api/v1/control-plane` when
`CONTROL_PLANE_ENABLED=true`. They require `X-Internal-Key` when included from
`create_agent_app()`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/goals` | List durable company goals |
| `POST` | `/goals` | Create a goal |
| `GET` | `/goals/{goal_id}` | Read one goal |
| `PATCH` | `/goals/{goal_id}/status` | Update goal status and progress value |
| `GET` | `/work-items` | List durable work items |
| `POST` | `/work-items` | Create a work item linked to an optional goal |
| `GET` | `/work-items/{work_item_id}` | Read one work item |
| `PATCH` | `/work-items/{work_item_id}/status` | Update work item status and owner |
| `GET` | `/decisions` | List durable decisions |
| `POST` | `/decisions` | Create a decision linked to optional goal/work/run |
| `GET` | `/decisions/{decision_id}` | Read one decision |
| `PATCH` | `/decisions/{decision_id}/status` | Accept, reject, or supersede a decision |
| `GET` | `/artifacts` | List artifacts |
| `POST` | `/artifacts` | Create an artifact linked to optional goal/work/run |
| `GET` | `/artifacts/{artifact_id}` | Read one artifact |
| `GET` | `/runs` | List `AgentRun` records by company, status, agent, or limit |
| `GET` | `/runs/{run_id}` | Read one `AgentRun` |
| `GET` | `/agents` | List persisted `AgentRole` definitions |
| `POST` | `/agents` | Create a frontend/operator-defined `AgentRole` |
| `GET` | `/agents/{agent_id}` | Read one `AgentRole` |
| `PATCH` | `/agents/{agent_id}/status` | Pause, resume, or otherwise change role status |
| `POST` | `/agents/{agent_id}/wake` | Start a manual wakeup through the configured adapter |
| `POST` | `/scheduler/heartbeats/run-once` | Run due heartbeat wakeups for active opted-in agents |
| `GET` | `/approvals` | List approval requests |
| `POST` | `/approvals/{approval_id}/approve` | Approve one request |
| `POST` | `/approvals/{approval_id}/reject` | Reject one request |
| `GET` | `/budgets/usage` | List budget usage records |
| `GET` | `/audit-events` | List append-only audit events |
| `GET` | `/timeline` | Merge audit, approval, and budget evidence by trace or run |

### `POST /api/v1/control-plane/goals`

```json
{
  "title": "Ship SPEC control plane",
  "description": "Make company work visible and auditable",
  "status": "active",
  "owner_agent_id": "pjm-agent",
  "success_metric": "P0 operator surfaces available",
  "target_value": 100,
  "current_value": 25,
  "tags": ["spec", "p0"],
  "created_by": "human:operator"
}
```

### `POST /api/v1/control-plane/work-items`

```json
{
  "title": "Expose goal and work-item API",
  "description": "Create/list/get/status endpoints",
  "status": "ready",
  "priority": "high",
  "goal_id": "goal_...",
  "owner_agent_id": "dev-agent",
  "external_ref": "spec-goal-api",
  "created_by": "human:operator"
}
```

Work item creation validates that referenced goals and dependency work items
belong to the same company context.

### `POST /api/v1/control-plane/decisions`

```json
{
  "title": "Accept run output",
  "rationale": "QA evidence is sufficient and rollback is available",
  "status": "accepted",
  "run_id": "run_...",
  "work_item_id": "work_...",
  "goal_id": "goal_...",
  "selected_option": "accept",
  "decided_by": "human:operator",
  "created_by": "human:operator"
}
```

### `POST /api/v1/control-plane/artifacts`

```json
{
  "artifact_type": "run_walkthrough",
  "title": "Run walkthrough",
  "uri": "artifact://runs/run_...",
  "run_id": "run_...",
  "work_item_id": "work_...",
  "goal_id": "goal_...",
  "created_by_agent_id": "ops-runner",
  "created_by": "agent:ops-runner"
}
```

Decision and artifact creation validates that referenced runs, work items, and
goals belong to the same company context.

### `POST /api/v1/control-plane/agents`

```json
{
  "agent_id": "ops-runner",
  "display_name": "Ops Runner",
  "agent_kind": "organization_role",
  "interaction_mode": "routed",
  "role": "operator",
  "title": "Operations Agent",
  "domain": "operations",
  "reports_to_agent_id": "cto",
  "adapter_type": "http",
  "adapter_config": {
    "base_url": "http://ops-runner:8016",
    "path": "/agent/request",
    "heartbeat_enabled": true,
    "heartbeat_interval_seconds": 300
  },
  "context_sources": ["control_plane", "feishu"],
  "capabilities": ["incident triage"],
  "responsibilities": ["Run operational checks"],
  "created_by": "frontend"
}
```

`agent_kind` separates role agents from execution modules:

| Value | Meaning |
|-------|---------|
| `organization_role` | CEO/CTO/CPO/COO/PM-style operating role that owns intent, tradeoffs, and user-facing decisions |
| `capability_module` | Internal capability such as sync, QA, requirement extraction, analysis, or development execution |
| `integration_gateway` | User/channel/system boundary that routes messages into role agents or modules |
| `system_worker` | Scheduler, maintenance, or internal automation agent |

`interaction_mode` is `direct`, `routed`, `internal`, or `none`. Capability
modules and system workers cannot use `direct`; they should be invoked by role
agents, gateways, schedulers, or work items.

### `POST /api/v1/control-plane/agents/{agent_id}/wake`

```json
{
  "input": {"task": "check-release"},
  "actor_id": "human:operator",
  "trace_id": "trace_...",
  "goal_id": "goal_...",
  "work_item_id": "work_..."
}
```

Successful wakeups return the persisted `run` plus adapter `output`. Local
`process`, `codex_local`, and `claude_local` adapters fail closed unless
`CONTROL_PLANE_LOCAL_ADAPTER_ENABLED=true` and the exact local adapter key is in
`CONTROL_PLANE_LOCAL_ADAPTER_ALLOWLIST`. The default key is
`{adapter_type}:{agent_id}`, or `adapter_config.allowlist_key` when present.
The recommended production boundary is the `http` adapter.

### `POST /api/v1/control-plane/scheduler/heartbeats/run-once`

```json
{
  "company_id": "cmp_...",
  "limit": 500
}
```

This endpoint is intended for one production scheduler tick from cron, Celery,
Kubernetes CronJob, or another trusted operator process. It evaluates active
agent definitions whose `adapter_config.heartbeat_enabled` is `true`, respects
`heartbeat_interval_seconds` with a 60-second minimum, and writes normal
`AgentRun`, input event, output event, trace, and audit evidence. The response
lists each opted-in agent as `succeeded`, `skipped`, or `failed`.

---

## PJM Agent (port 8012)

PJM Agent 负责项目管理预警、报告触发、工作包拆解审批。

### `GET /api/v1/pm/config`

- **认证**: X-Internal-Key
- **说明**: 获取 PM 配置（成员、项目、规则）
- **请求参数**: 无
- **响应**:
```json
{
  "members": [{"id": 1, "name": "张三", "role": "dev"}],
  "projects": [{"id": 10, "name": "Core"}],
  "rules": {"overdue_threshold": "3d"}
}
```
- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/config
```

### `POST /api/v1/pm/config/refresh`

- **认证**: X-Internal-Key
- **说明**: 从 OpenProject 刷新配置缓存
- **请求 Body**: 无
- **响应**:
```json
{
  "status": "refreshed"
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/config/refresh
```

### `GET /api/v1/pm/alerts`

- **认证**: X-Internal-Key
- **说明**: 获取当前项目预警列表
- **请求参数**: 无
- **响应**:
```json
{
  "total": 2,
  "alerts": [
    {
      "type": "overdue",
      "task": "WP-123: 设计评审",
      "message": "超期 3 天",
      "severity": "high"
    }
  ]
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| total | int | 告警总数 |
| alerts[].type | string | 告警类型 |
| alerts[].task | string | 关联任务 |
| alerts[].message | string | 告警描述 |
| alerts[].severity | string | 严重程度 (high/medium/low) |

- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/alerts
```

### `POST /api/v1/pm/report/daily`

- **认证**: X-Internal-Key
- **说明**: 手动触发日报生成（通常由定时任务自动触发）
- **请求 Body**: 无
- **响应**:
```json
{
  "status": "ok",
  "message": "日报已发送"
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/report/daily
```

### `POST /api/v1/pm/report/weekly`

- **认证**: X-Internal-Key
- **说明**: 手动触发周报生成
- **请求 Body**: 无
- **响应**: 同日报
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/report/weekly
```

### `GET /api/v1/pm/decompose/{wp_id}`

- **认证**: X-Internal-Key
- **说明**: 查询工作包拆解状态

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| wp_id | int (path) | 是 | OpenProject 工作包 ID |

- **响应**:
```json
{
  "wp_id": 123,
  "project_id": 10,
  "status": "pending",
  "assignee_id": 5,
  "decompose_result": {"stories": [], "tasks": []},
  "created_at": "2026-03-07T10:00:00",
  "updated_at": "2026-03-07T10:05:00",
  "approved_by": null
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| wp_id | int | 工作包 ID |
| project_id | int | 项目 ID |
| status | string | 状态 (pending/approved/rejected/failed) |
| assignee_id | int? | 负责人 ID |
| decompose_result | dict? | AI 拆解结果 |
| approved_by | string? | 审批人 |

- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8012/api/v1/pm/decompose/123
```

### `POST /api/v1/pm/decompose/{wp_id}/approve`

- **认证**: X-Internal-Key
- **说明**: 审批通过拆解，将 User Story 和 Task 写入 OpenProject

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| wp_id | int (path) | 是 | 工作包 ID |

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| operator | string | 否 | 审批人标识，默认 `"api"` |

- **响应**:
```json
{
  "success": true,
  "wp_id": 123,
  "action": "approve",
  "message": "已写入 OP: 3 US, 8 Task",
  "subject": "用户管理模块",
  "story_count": 3,
  "task_count": 8
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"operator": "zhang.san"}' \
  http://localhost:8012/api/v1/pm/decompose/123/approve
```

### `POST /api/v1/pm/decompose/{wp_id}/reject`

- **认证**: X-Internal-Key
- **说明**: 拒绝拆解方案

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| operator | string | 否 | 拒绝人标识 |
| reason | string | 否 | 拒绝原因 |

- **响应**:
```json
{
  "success": true,
  "wp_id": 123,
  "action": "reject",
  "message": "已拒绝",
  "subject": "用户管理模块",
  "story_count": 0,
  "task_count": 0
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"operator": "zhang.san", "reason": "粒度太粗"}' \
  http://localhost:8012/api/v1/pm/decompose/123/reject
```

### `POST /api/v1/pm/decompose/{wp_id}/retry`

- **认证**: X-Internal-Key
- **说明**: 重试失败的拆解

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| wp_id | int (path) | 是 | 工作包 ID |

- **请求 Body**: 无
- **响应**: 返回拆解结果 dict，结构视拆解状态而定
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  http://localhost:8012/api/v1/pm/decompose/123/retry
```

---

## Chat Agent (port 8013)

Chat Agent 处理飞书消息交互、多维表格操作、日进展查询。

### `POST /webhook/feishu`

- **认证**: 飞书签名验证
- **说明**: 飞书事件回调入口（消息接收）。支持 challenge 验证和 `im.message.receive_v1` 事件处理。消息处理为异步（fire-and-forget），接口立即返回。

- **请求 Body**: 飞书标准 webhook 格式

```json
{
  "header": {
    "event_type": "im.message.receive_v1"
  },
  "event": {
    "message": {
      "message_id": "om_xxx",
      "message_type": "text",
      "chat_type": "p2p",
      "content": "{\"text\": \"查看今日任务\"}"
    },
    "sender": {
      "sender_id": {"open_id": "ou_xxx"}
    }
  }
}
```

- **Challenge 验证请求**:
```json
{"challenge": "xxx"}
```

- **响应**:
```json
{"code": 0}
```

Challenge 响应：
```json
{"challenge": "xxx"}
```

- **示例**:
```bash
curl -X POST http://localhost:8013/webhook/feishu \
  -H "Content-Type: application/json" \
  -H "X-Lark-Request-Timestamp: 1234567890" \
  -H "X-Lark-Request-Nonce: nonce123" \
  -H "X-Lark-Signature: sig_xxx" \
  -d '{"header":{"event_type":"im.message.receive_v1"},"event":{...}}'
```

### `GET /api/daily-progress`

- **认证**: X-Internal-Key
- **说明**: 查询日进展记录，PJM Agent 调用此接口生成报告

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| target_date | date (query) | 否 | 查询日期，默认今天。格式 `YYYY-MM-DD` |
| user_id | string (query) | 否 | 按用户过滤 |
| days | int (query) | 否 | 查询天数范围，默认 `1` |

- **响应**:
```json
{
  "entries": [
    {
      "id": 1,
      "user_id": "ou_xxx",
      "user_name": "张三",
      "date": "2026-03-07",
      "task_record_id": "recXXX",
      "task_title": "完成登录模块",
      "status": "done",
      "note": "已完成联调",
      "raw_reply": "今天完成了登录模块的联调"
    }
  ],
  "total": 1
}
```
- **示例**:
```bash
curl "http://localhost:8013/api/daily-progress?target_date=2026-03-07&days=3"
```

### `POST /api/bitable/confirm`

- **认证**: X-Internal-Key (Gateway 内部转发)
- **说明**: 确认多维表格更新操作。如提供 `action_id`，从 Redis 读取待执行数据（SEC-103 安全设计）。操作过期（30分钟）将返回过期卡片。

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| record_id | string | 否 | 记录 ID（`action_id` 存在时可省略） |
| fields | dict | 否 | 更新字段 |
| table_id | string | 否 | 表格 ID |
| user_id | string | 否 | 操作用户 |
| user_name | string | 否 | 用户名 |
| action_id | string | 否 | 操作 ID（从 Redis 获取完整数据） |

- **响应**: 飞书消息卡片 JSON (dict)
```json
{
  "header": {"title": {"content": "表格已更新"}},
  "elements": [...]
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"action_id": "act_xxx", "user_id": "ou_xxx"}' \
  http://localhost:8013/api/bitable/confirm
```

### `POST /api/bitable/reject`

- **认证**: X-Internal-Key (Gateway 内部转发)
- **说明**: 用户取消多维表格修改/创建操作

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action_type | string | 否 | 操作类型 (`"create"` / `"update"`) |
| user_id | string | 否 | 操作用户 |
| user_name | string | 否 | 用户名 |
| fields | dict | 否 | 原始字段 |
| table_id | string | 否 | 表格 ID |
| record_id | string | 否 | 记录 ID |

- **响应**: 飞书消息卡片 JSON (dict)
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"action_type": "update", "user_id": "ou_xxx"}' \
  http://localhost:8013/api/bitable/reject
```

### `POST /api/bitable/create`

- **认证**: X-Internal-Key (Gateway 内部转发)
- **说明**: 创建新的多维表格记录

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| fields | dict | 否 | 记录字段 |
| table_id | string | 否 | 目标表格 ID |
| user_id | string | 否 | 操作用户 |
| user_name | string | 否 | 用户名 |
| action_id | string | 否 | 操作 ID |

- **响应**: 飞书消息卡片 JSON (dict)
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"fields": {"标题": "新任务"}, "table_id": "tblXXX"}' \
  http://localhost:8013/api/bitable/create
```

---

## Analysis Agent (port 8011)

Analysis Agent 负责分析报告生成和风险检测。

### `POST /api/v1/analysis/daily`

- **认证**: X-Internal-Key
- **说明**: 手动触发日报生成
- **请求 Body**: 无
- **响应**:
```json
{
  "status": "ok",
  "content": "## 日报 2026-03-07\n...",
  "summary": "今日完成 5 项任务...",
  "generated_at": "2026-03-07T18:00:00Z"
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| status | string | 状态 |
| content | string | 报告完整内容 (Markdown) |
| summary | string | 摘要 |
| generated_at | datetime | 生成时间 |

- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8011/api/v1/analysis/daily
```

### `POST /api/v1/analysis/weekly`

- **认证**: X-Internal-Key
- **说明**: 手动触发周报生成
- **请求 Body**: 无
- **响应**: 结构同日报
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8011/api/v1/analysis/weekly
```

### `GET /api/v1/analysis/risks`

- **认证**: X-Internal-Key
- **说明**: 检查里程碑风险
- **请求参数**: 无
- **响应**:
```json
{
  "total": 1,
  "risks": [
    {
      "feature": "用户管理模块",
      "risk_level": "high",
      "days_remaining": 3,
      "progress": 40,
      "message": "进度落后，预计无法按时完成"
    }
  ]
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| total | int | 风险总数 |
| risks[].feature | string | 功能/里程碑名称 |
| risks[].risk_level | string | 风险等级 (high/medium/low) |
| risks[].days_remaining | int | 剩余天数 |
| risks[].progress | int | 当前进度百分比 |
| risks[].message | string | 风险描述 |

- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8011/api/v1/analysis/risks
```

---

## Sync Agent (port 8010)

Sync Agent 负责 OpenProject 与飞书多维表格之间的数据同步。

### `POST /api/v1/sync/trigger`

- **认证**: X-Internal-Key
- **说明**: 手动触发一次全量同步。成功返回 `200`，上游失败返回 `502`。
- **请求 Body**: 无
- **响应**:
```json
{
  "status": "completed",
  "total_processed": 42,
  "errors": [],
  "error": null
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| status | string | `"completed"` / `"failed"` |
| total_processed | int | 已处理记录数 |
| errors | list[string] | 具体错误列表 |
| error | string? | 整体错误信息 |

- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" http://localhost:8010/api/v1/sync/trigger
```

### `GET /api/v1/sync/status`

- **认证**: X-Internal-Key
- **说明**: 获取同步 Agent 状态
- **请求参数**: 无
- **响应**:
```json
{
  "status": "idle",
  "agent_id": "sync-agent"
}
```
- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8010/api/v1/sync/status
```

### `GET /api/v1/sync/mappings`

- **认证**: X-Internal-Key
- **说明**: 列出所有 OP 工作包与飞书记录的映射关系
- **请求参数**: 无
- **响应**:
```json
{
  "total": 42,
  "items": [
    {
      "id": 1,
      "op_work_package_id": 123,
      "feishu_record_id": "recXXX",
      "op_project_id": 10,
      "updated_at": "2026-03-07T10:00:00"
    }
  ]
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| items[].id | int | 映射记录 ID |
| items[].op_work_package_id | int | OpenProject 工作包 ID |
| items[].feishu_record_id | string? | 飞书多维表格记录 ID |
| items[].op_project_id | int? | OpenProject 项目 ID |
| items[].updated_at | datetime? | 最后更新时间 |

- **示例**:
```bash
curl -H "X-Internal-Key: $KEY" http://localhost:8010/api/v1/sync/mappings
```

---

## Requirement Manager (port 8000)

Requirement Manager 是最大的 Agent，拥有 55+ 端点。以下按功能模块分组，使用紧凑表格列出。

### 需求 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/requirements` | 需求列表（分页） |
| GET | `/api/v1/requirements/{id}` | 需求详情 |
| PUT | `/api/v1/requirements/{id}` | 更新需求 |
| DELETE | `/api/v1/requirements/{id}` | 删除需求 |

**`GET /api/v1/requirements` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态筛选: `pending` / `confirmed` / `changed` / `rejected` |
| category | string | 否 | 分类筛选 |
| priority | string | 否 | 优先级: `high` / `medium` / `low` |
| page | int | 否 | 页码，默认 `1` |
| page_size | int | 否 | 每页数量，默认 `20`，最大 `100` |

**`PUT /api/v1/requirements/{id}` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 否 | 标题 |
| description | string | 否 | 描述 |
| priority | string | 否 | 优先级 |
| category | string | 否 | 分类 |
| comment | string | 否 | 变更备注 (记入历史) |

**`DELETE /api/v1/requirements/{id}` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| deleted_by | string | 是 | 删除操作人 |

**需求响应结构 (RequirementOut)**:

```json
{
  "id": "req_01HXYZ",
  "title": "用户登录功能",
  "description": "...",
  "source_quote": "原始讨论内容",
  "status": "pending",
  "priority": "high",
  "category": "功能需求",
  "source_meeting_ids": ["mtg_01"],
  "confirmed_by": null,
  "confirmed_at": null,
  "open_questions": [],
  "history": [{"action": "created", "detail": "...", "by": "system", "at": "..."}],
  "created_at": "2026-03-07T10:00:00",
  "updated_at": "2026-03-07T10:00:00"
}
```

**示例**:
```bash
# 列出高优先级需求
curl "http://localhost:8000/api/v1/requirements?priority=high&page=1&page_size=10"

# 更新需求
curl -X PUT -H "Content-Type: application/json" \
  -d '{"priority": "high", "comment": "提升优先级"}' \
  http://localhost:8000/api/v1/requirements/req_01HXYZ

# 删除需求
curl -X DELETE -H "Content-Type: application/json" \
  -d '{"deleted_by": "admin"}' \
  http://localhost:8000/api/v1/requirements/req_01HXYZ
```

### 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/requirements/search` | 语义搜索（向量数据库） |
| GET | `/api/v1/requirements/{id}/similar` | 查找相似需求 |

**`GET /api/v1/requirements/search` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 搜索关键词（支持自然语言） |
| category | string | 否 | 分类过滤 |
| limit | int | 否 | 返回数量，默认 `20`，最大 `100` |
| min_similarity | float | 否 | 最小相似度阈值，默认 `0.5` |

**响应**:
```json
{
  "query": "离线功能",
  "total": 3,
  "items": [
    {"id": "req_01", "title": "离线缓存", "category": "功能", "similarity": 0.92}
  ]
}
```

**`GET /api/v1/requirements/{id}/similar` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| limit | int | 否 | 返回数量，默认 `5`，最大 `20` |
| min_similarity | float | 否 | 最小相似度，默认 `0.7` |

**示例**:
```bash
curl "http://localhost:8000/api/v1/requirements/search?q=用户登录&limit=5"
```

### 分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/requirements/{id}/analyze` | 分析已有需求 |
| POST | `/api/v1/requirements/analyze-text` | 分析文本（无需创建需求） |

**`POST /api/v1/requirements/{id}/analyze` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| use_llm | bool (query) | 否 | 使用 LLM 深度分析，默认 `false` |

**响应**: 包含分类建议、优先级建议、复杂度估算、依赖分析、风险评估。

**`POST /api/v1/requirements/analyze-text` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string (query) | 是 | 需求标题 |
| description | string (query) | 否 | 需求描述 |
| use_llm | bool (query) | 否 | 使用 LLM，默认 `false` |

**示例**:
```bash
curl -X POST "http://localhost:8000/api/v1/requirements/req_01/analyze?use_llm=true"
```

### 冲突检测

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/requirements/check-conflict` | 检查需求冲突/重复 |

**请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 需求标题 |
| description | string | 是 | 需求描述 |
| category | string | 否 | 需求分类 |
| exclude_ids | list[string] | 否 | 排除的需求 ID 列表 |

**响应**:
```json
{
  "relation": "duplicate",
  "confidence": 0.95,
  "explanation": "与 req_01 高度相似",
  "suggested_action": "merge",
  "related_requirement_id": "req_01",
  "merge_suggestion": "建议合并到已有需求"
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| relation | string | `new` / `duplicate` / `update` / `conflict` |
| confidence | float | 判断确信度 (0-1) |
| suggested_action | string | 建议操作 |

**示例**:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"title": "用户登录", "description": "支持手机号登录"}' \
  http://localhost:8000/api/v1/requirements/check-conflict
```

### 确认/拒绝 (Feedback)

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/v1/requirements/{id}/confirm` | 确认需求 |
| PUT | `/api/v1/requirements/{id}/reject` | 拒绝需求 |
| POST | `/api/v1/questions/{id}/answer` | 回答待确认问题 |
| GET | `/api/v1/questions/open` | 获取未回答问题列表 |

**`PUT .../confirm` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| confirmed_by | string | 是 | 确认人 |

**`PUT .../reject` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| reason | string | 是 | 拒绝原因 |
| rejected_by | string | 否 | 拒绝人，默认 `"system"` |

**`POST .../answer` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| answer | string | 是 | 回答内容 |
| answered_by | string | 否 | 回答人，默认 `"system"` |

**示例**:
```bash
# 确认需求
curl -X PUT -H "Content-Type: application/json" \
  -d '{"confirmed_by": "product_owner"}' \
  http://localhost:8000/api/v1/requirements/req_01/confirm

# 拒绝需求
curl -X PUT -H "Content-Type: application/json" \
  -d '{"reason": "超出范围", "rejected_by": "pm"}' \
  http://localhost:8000/api/v1/requirements/req_01/reject
```

### 批量操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/requirements/batch/confirm` | 批量确认 |
| POST | `/api/v1/requirements/batch/reject` | 批量拒绝 |

**`POST .../batch/confirm` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| requirement_ids | list[string] | 是 | 需求 ID 列表 |
| confirmed_by | string | 是 | 确认人 |

**`POST .../batch/reject` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| requirement_ids | list[string] | 是 | 需求 ID 列表 |
| reason | string | 是 | 拒绝原因 |
| rejected_by | string | 否 | 拒绝人，默认 `"system"` |

**响应** (两者相同):
```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"requirement_id": "req_01", "success": true, "error": null},
    {"requirement_id": "req_02", "success": true, "error": null},
    {"requirement_id": "req_99", "success": false, "error": "需求不存在"}
  ]
}
```

**示例**:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"requirement_ids": ["req_01", "req_02"], "confirmed_by": "pm"}' \
  http://localhost:8000/api/v1/requirements/batch/confirm
```

### 导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/export/prd` | 导出 PRD 文档 |
| GET | `/api/v1/export/prd/download` | 下载 PRD (Markdown 文件) |
| GET | `/api/v1/export/questions` | 导出问题清单 |
| GET | `/api/v1/export/questions/download` | 下载问题清单 (Markdown 文件) |

**`GET /api/v1/export/prd` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态筛选: `confirmed` / `pending` / `all` |
| format | string | 否 | 输出格式: `json` (默认) / `markdown` |
| project_name | string | 否 | 项目名称，默认 `"Wisdoverse Cell"` |
| version | string | 否 | 文档版本，默认 `"1.0"` |

**响应** (format=json):
```json
{
  "content": "# PRD...",
  "format": "markdown",
  "generated_at": "2026-03-07T18:00:00Z",
  "requirements_count": 15,
  "version": "1.0"
}
```

**`GET /api/v1/export/questions` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态筛选: `open` / `answered` / `all` |
| format | string | 否 | 输出格式: `json` / `markdown` |
| project_name | string | 否 | 项目名称 |

**示例**:
```bash
# 导出已确认需求的 PRD
curl "http://localhost:8000/api/v1/export/prd?status=confirmed&format=markdown" -o prd.md

# 下载问题清单
curl "http://localhost:8000/api/v1/export/questions/download" -o questions.md
```

### 会议 & 导入

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/meetings` | 会议列表 |
| POST | `/api/v1/ingest/upload` | 手动上传会议内容 |
| POST | `/api/v1/ingest/feishu` | 飞书会议 webhook |

**`GET /api/v1/meetings` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source | string | 否 | 来源筛选 |
| page | int | 否 | 页码，默认 `1` |
| page_size | int | 否 | 每页数量，默认 `20` |

**`POST /api/v1/ingest/upload` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | 是 | 会议内容 (至少 10 字符) |
| source | string | 否 | 来源，默认 `"upload"` |
| title | string | 否 | 标题 |
| meeting_date | string | 否 | 会议日期 (ISO 格式) |
| participants | list[string] | 否 | 参与者列表 |
| context | string | 否 | 上下文说明 |

**`POST /api/v1/ingest/feishu` Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| event_type | string | 是 | 事件类型 |
| summary | string | 是 | 会议纪要内容 |
| meeting_id | string | 否 | 飞书会议 ID (用于去重) |
| topic | string | 否 | 会议主题 |
| participants | list[string] | 否 | 参与者 |
| meeting_time | string | 否 | 会议时间 (ISO 格式) |

**导入响应**:
```json
{
  "status": "ok",
  "meeting_id": "mtg_01HXYZ",
  "requirements_extracted": 5,
  "questions_generated": 3
}
```

**示例**:
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"content": "讨论了用户登录功能，需要支持手机号和邮箱登录...", "source": "wechat"}' \
  http://localhost:8000/api/v1/ingest/upload
```

### 消息搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/messages/search` | 搜索消息（支持中文全文检索） |
| GET | `/api/v1/messages/session/{session_id}` | 获取会话所有消息 |

**`GET /api/v1/messages/search` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 否 | 全文搜索关键词 |
| chat_id | string | 否 | 按 chat_id 过滤 |
| sender_id | string | 否 | 按发送者 open_id 过滤 |
| start_time | datetime | 否 | 起始时间 |
| end_time | datetime | 否 | 结束时间 |
| page | int | 否 | 页码，默认 `1` |
| page_size | int | 否 | 每页数量，默认 `20`，最大 `100` |

**示例**:
```bash
curl "http://localhost:8000/api/v1/messages/search?keyword=登录&page=1"
```

### 管理 (Admin)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/llm-usage` | LLM 使用量统计 |
| GET | `/api/v1/admin/circuit-breaker` | 断路器状态 |
| POST | `/api/v1/admin/circuit-breaker/reset` | 重置断路器 |

**`GET /api/v1/admin/llm-usage` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期 `YYYY-MM-DD`，默认今天 |
| agent_id | string | 否 | 按 Agent 过滤 |

**响应**:
```json
{
  "date": "2026-03-07",
  "total_calls": 150,
  "success_calls": 145,
  "failed_calls": 5,
  "total_input_tokens": 50000,
  "total_output_tokens": 30000,
  "total_cost_usd": 2.5,
  "avg_latency_ms": 1200,
  "by_agent": {"requirement-manager": {"calls": 100}},
  "by_task_type": {"extraction": {"calls": 80}}
}
```

**`GET /api/v1/admin/circuit-breaker` 响应**:
```json
{
  "state": "closed",
  "failures": 0,
  "failure_threshold": 5,
  "recovery_timeout": 60,
  "last_failure_time": null
}
```

**示例**:
```bash
# 查看 LLM 用量
curl "http://localhost:8000/api/v1/admin/llm-usage?date=2026-03-07"

# 重置断路器
curl -X POST http://localhost:8000/api/v1/admin/circuit-breaker/reset
```

### 历史与上下文

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/requirements/{id}/history` | 变更历史 |
| GET | `/api/v1/requirements/{id}/diff` | 变更 diff |
| GET | `/api/v1/requirements/{id}/context` | 需求上下文（源消息） |

**`GET .../diff` 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| from_index | int | 否 | 起始变更索引，默认 `0` |
| to_index | int | 否 | 结束变更索引，`-1` 表示最新 |

**示例**:
```bash
# 查看变更历史
curl http://localhost:8000/api/v1/requirements/req_01/history

# 查看上下文消息
curl http://localhost:8000/api/v1/requirements/req_01/context
```

### 统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/stats` | 基础统计 |
| GET | `/api/v1/stats/enhanced` | 增强统计（含趋势） |

**`GET /api/v1/stats` 响应**:
```json
{
  "requirements_by_status": {"pending": 10, "confirmed": 25},
  "total_meetings": 8,
  "unprocessed_meetings": 2,
  "vector_store_count": 35
}
```

**`GET /api/v1/stats/enhanced` 额外字段**:
```json
{
  "requirements_by_priority": {"high": 5, "medium": 15, "low": 15},
  "requirements_by_category": {"功能需求": 20, "非功能需求": 15},
  "weekly_trend": [{"date": "2026-03-01", "count": 3}],
  "today_count": 2
}
```

---

## Go Gateway (port 8080)

Go Gateway 是系统唯一的公网入口，使用 Gin 框架，提供请求转发、限流、断路器保护。

### `GET /health`

- **认证**: 无
- **说明**: Gateway 存活检查
- **响应**:
```json
{"status": "healthy"}
```
- **示例**:
```bash
curl http://localhost:8080/health
```

### `GET /ready`

- **认证**: 无
- **说明**: Gateway 就绪检查（含下游服务探测）
- **响应**:
```json
{
  "status": "ready",
  "version": "v1.0.0"
}
```
- **示例**:
```bash
curl http://localhost:8080/ready
```

### `POST /api/feishu/webhook`

- **认证**: 飞书签名验证
- **说明**: 飞书 webhook 统一入口。处理三类请求：
  1. **URL 验证** (`url_verification`): 直接返回 challenge
  2. **消息事件** (`event_callback` + `im.message.receive_v1`): 转发至 Chat Agent
  3. **卡片回调** (`card.action.trigger`): 按 action_type 路由到对应 Agent（confirm/reject bitable、approve/reject decomposition 等）

- **请求 Body**: 飞书标准 webhook 格式（同 Chat Agent `/webhook/feishu`）
- **响应**: 视场景而定（challenge 回复、卡片 JSON、空响应）
- **示例**:
```bash
curl -X POST http://localhost:8080/api/feishu/webhook \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "xxx"}'
```

### `GET /api/wecom/webhook`

- **认证**: 企业微信签名验证
- **说明**: 企业微信 URL 验证（echostr 回传）
- **示例**:
```bash
curl "http://localhost:8080/api/wecom/webhook?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx"
```

### `POST /api/wecom/webhook`

- **认证**: 企业微信签名验证
- **说明**: 企业微信消息回调。支持文本消息处理和技能匹配（需求查询、确认等）。
- **请求 Body**: 企业微信加密 XML 格式
- **响应**: XML 回复或空响应

---

## Evolution Agent (standalone service)

Evolution Agent 负责全局跨 Agent 追踪分析和架构优化建议。**注意：此 Agent 不参与自我进化（`evolution_excluded=True`）。**

### `GET /health`

- **认证**: 无
- **说明**: 存活检查（Liveness Probe）
- **响应**:
```json
{
  "status": "alive",
  "agent": "evolution-agent"
}
```
- **示例**:
```bash
curl http://localhost:<port>/health
```

### `GET /health/ready`

- **认证**: 无
- **说明**: 就绪检查（Readiness Probe），包含进化系统依赖状态
- **响应**:
```json
{
  "status": "ready",
  "checks": {
    "agent_started": true,
    "evolution_redis": true
  }
}
```
- **示例**:
```bash
curl http://localhost:<port>/health/ready
```

### `POST /analyze`

- **认证**: X-Internal-Key
- **说明**: 手动触发全局分析周期。扫描最近 N 天的执行追踪数据，通过 `GlobalAnalyzer` 生成跨 Agent 的技能优化提案。

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| days | int (query) | 否 | 分析的天数范围，默认 `7` |

- **响应**:
```json
{
  "proposals": [
    {
      "agent_id": "pjm-agent",
      "skill_id": "decomposition",
      "suggestion": "优化拆解提示词以提高任务粒度准确性",
      "evidence": ["trace_01HXYZ", "trace_01HABC"]
    }
  ]
}
```

| 响应字段 | 类型 | 说明 |
|----------|------|------|
| proposals | list | 优化提案列表 |
| proposals[].agent_id | string | 目标 Agent |
| proposals[].skill_id | string | 目标技能 |
| proposals[].suggestion | string | 优化建议描述 |
| proposals[].evidence | list[string] | 支持证据（trace ID 列表） |

- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  "http://localhost:<port>/analyze?days=14"
```

---

## QA Agent (port 8014)

QA Agent 负责自动化代码质量验收。接收 `code.committed` 事件后自动运行 L0/L1/L2 检查。

### `POST /api/v1/qa/run`

- **认证**: X-Internal-Key
- **说明**: 手动触发 QA 验收运行

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| agent_name | string | 否 | 目标 Agent 名称 |
| level | string | 否 | 验收级别: `L0`, `L1`, `L2`，默认 `L0` |
| commit_sha | string | 否 | 目标 commit SHA |
| files_changed | list[string] | 否 | 变更文件列表 |
| mr_iid | int | 否 | GitLab MR IID |
| requested_by | string | 否 | 触发人标识 |
| reason | string | 否 | 触发原因 |

- **响应**:
```json
{
  "run_id": "uuid",
  "status": "passed",
  "summary": "L0 验收通过"
}
```

### `GET /api/v1/qa/runs`

- **认证**: X-Internal-Key
- **说明**: 查询验收运行历史

| 查询参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| limit | int | 否 | 返回数量，默认 20 |
| agent_name | string | 否 | 按 Agent 筛选 |

### `GET /api/v1/qa/runs/{run_id}`

- **认证**: X-Internal-Key
- **说明**: 查询单次验收运行详情

### `GET /api/v1/qa/stats`

- **认证**: X-Internal-Key
- **说明**: 获取验收统计（通过率、平均耗时等）

---

## Dev Agent (port 8015)

Dev Agent bridges PJM work with AgentForge delivery workflows. All endpoints
require `X-Internal-Key` and are mounted under `/api/v1/dev`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/tasks` | List active workflows |
| `GET` | `/tasks/failed` | List failed workflows |
| `GET` | `/tasks/{wp_id}` | Read task/workflow status by OpenProject work-package ID |
| `POST` | `/tasks/{task_id}/retry` | Retry a failed or retryable task |
| `POST` | `/tasks/{task_id}/cancel` | Cancel a running workflow |
| `POST` | `/tasks/{task_id}/approve` | Approve a workflow waiting on human review |

High-risk development work should also create control-plane approval evidence
before external mutation or MR-producing actions.

---

## DSAR 合规端点 (所有 Agent)

所有 Agent 均挂载 DSAR (Data Subject Access Request) 路由，用于 GDPR Art. 17/20 及 PIPL Art. 47 合规。

### `POST /api/dsar/export`

- **认证**: X-Internal-Key (必须)
- **说明**: 导出指定用户的全部数据（数据可携带权）

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 open_id |

- **响应**:
```json
{
  "user_id": "ou_xxx",
  "action": "export",
  "affected_tables": {"daily_progress": 15, "chat_messages": 42},
  "redis_keys_affected": 0,
  "status": "completed",
  "errors": [],
  "timestamp": "2026-03-07T10:00:00Z"
}
```
- **示例**:
```bash
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ou_xxx"}' \
  http://localhost:8013/api/dsar/export
```

### `POST /api/dsar/delete`

- **认证**: X-Internal-Key (必须)
- **说明**: 删除指定用户的全部数据。默认 dry-run 模式（仅返回计数，不实际删除）。

| 请求参数 | 类型 | 必填 | 说明 |
|----------|------|------|------|
| confirm | bool (query) | 否 | `true` 实际删除，`false`(默认) dry-run |

- **请求 Body**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | string | 是 | 用户 open_id |

- **响应**:
```json
{
  "user_id": "ou_xxx",
  "action": "delete_dry_run",
  "affected_tables": {"daily_progress": 15},
  "redis_keys_affected": 3,
  "status": "completed",
  "errors": [],
  "timestamp": "2026-03-07T10:00:00Z"
}
```
- **示例**:
```bash
# Dry-run（预览影响范围）
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ou_xxx"}' \
  http://localhost:8013/api/dsar/delete

# 实际删除
curl -X POST -H "X-Internal-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "ou_xxx"}' \
  "http://localhost:8013/api/dsar/delete?confirm=true"
```

---

## AgentClient 服务间调用模式

Agent 之间通过 HTTP REST 相互调用，使用 `shared/services/agent_client.py` 中的 `AgentClient` 基类。

### 基础用法

```python
from shared.services.agent_client import AgentClient

client = AgentClient(base_url="http://pjm-agent:8012", timeout=12.0)

# GET 请求
result = await client.get("/api/v1/pm/alerts")

# POST 请求
result = await client.post("/api/v1/pm/decompose/123/approve", json={"operator": "bot"})
```

### 认证

`AgentClient` 自动附加 `X-Internal-Key` header（从 `settings.internal_service_key` 读取）：

```python
def _headers(self) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.internal_service_key:
        headers["X-Internal-Key"] = settings.internal_service_key
    return headers
```

### 类型化客户端

对于频繁调用的 Agent，提供类型化封装。以 `PMAgentClient` 为例：

```python
from shared.services.agent_client import PMAgentClient

pm = PMAgentClient()  # 使用 settings.pjm_agent_url

# 审批通过拆解
result = await pm.approve_decomposition(wp_id=123, operator="zhang.san")
# result: {"success": true, "wp_id": 123, ...} 或 None (404)

# 拒绝拆解
result = await pm.reject_decomposition(wp_id=123, operator="li.si", reason="粒度太粗")

# 重试拆解
result = await pm.retry_decomposition(wp_id=123)

# 查询拆解状态
result = await pm.get_decomposition(wp_id=123)
```

### 错误处理

- 404 响应自动捕获并返回 `None`
- 其他 HTTP 错误抛出 `httpx.HTTPStatusError`
- 底层使用 `httpx.AsyncClient`，支持连接超时控制

### 端口注册表

| Agent | 默认端口 | 环境变量 |
|-------|----------|----------|
| Requirement Manager | 8000 | `REQUIREMENT_MANAGER_URL` |
| Sync Agent | 8010 | `SYNC_AGENT_URL` |
| Analysis Agent | 8011 | `ANALYSIS_AGENT_URL` |
| PJM Agent | 8012 | `PM_AGENT_URL` |
| Chat Agent | 8013 | `CHAT_AGENT_URL` |
| Go Gateway | 8080 | `GATEWAY_URL` |
