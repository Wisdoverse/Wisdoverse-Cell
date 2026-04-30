# Dev Agent Design Spec

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **Status**: Draft v3 (post Round 1-8 review) | **Author**: Human + Claude | **Date**: 2026-03-23

## Problem Statement

PJM Agent 能够将 Feature/Epic 分解为可执行的 User Story 和 Task，但分解完成后没有能力将任务派发给 AI 工具执行实现。当前流程在"分解 → 审批 → 写回 OP"后就断裂了，缺少"OP 任务 → 代码产出 → MR → 验收 → 完成"的闭环。

项目已有 AgentForge Orchestrator 平台（`/api/v1/workflows`）和 AI 团队工作流模板（`agent-development.json`），但缺少一个 Agent 来桥接 PJM 任务管理与 AgentForge 代码执行。

## Goals

1. **通用研发调度** — 支持任意类型的 PJM 任务（新功能、bugfix、重构、文档等），不限定工作流模板
2. **动态工作流生成** — 用 LLM 分析 Task 内容，自动生成多步工作流（规划→实现→review→验收）
3. **风险分级自动化** — 低风险任务全自动闭环，高风险任务人工审批，按风险等级渐进放权
4. **智能工具分配** — 规则引擎 + 配置覆盖决定每步用哪个 AI 工具（Claude Code / Gemini / Codex）
5. **标准 agent 架构** — 继承 BaseAgent、使用 create_agent_app、通过验收框架

## Non-Goals

- **不替代 AgentForge** — dev_agent 是编排层，不直接执行代码
- **不自主决定做什么** — 只响应 PJM 派发的任务，不自行发现需求
- **不做 CI/CD** — GitLab CI 负责流水线，dev_agent 只创建 MR
- **不做代码托管** — 代码在 GitLab，AgentForge workspace 是临时执行环境
- **不自动合入 MR** — dev_agent 只创建 MR，永远不自动 merge（GitLab branch protection 强制人类 Approve）

## Architecture

### 定位：Thin Orchestrator

dev_agent 是"薄编排层"，自身不执行研发工作。核心价值是把 PJM 任务翻译为 AgentForge 工作流并跟踪全生命周期。

**Agent ID**: `dev-agent`（kebab-case，遵循项目约定）

### 事件流

```
PJM Agent                     dev_agent                        AgentForge
───────────                   ─────────                        ──────────
OPWriter.write() ──→ pm.tasks-ready-for-dev ──→ handle_event()
                                              │
                                         InputSanitizer
                                         (PromptSafetyScanner + 输入校验)
                                              │
                                         TaskRiskAssessor
                                         (风险分级: LOW/MEDIUM/HIGH/CRITICAL)
                                              │ [CRITICAL → 直接拒绝，通知人工]
                                              │ [HIGH → 工作流生成后需人工审批]
                                              │
                                         WorkflowPlanner
                                         (LLM: Task → 工作流JSON)
                                              │
                                         WorkflowValidator
                                         (DAG 校验 + 路径白名单 + 二次安全扫描)
                                              │
                                         ToolRouter
                                         (规则+配置: 分配AI工具)
                                              │
                                         [HIGH风险? → 飞书审批卡片 → 人工确认]
                                              │
                                         ForgeClient ──────→ POST /api/v1/workflows
                                              │                POST /api/v1/workflows/:id/run
                                              │
                                         ReconciliationLoop ←── GET /api/v1/workflows/:id/status
                                              │
                                         ResultCollector
                                         ├─→ SecurityScanner (pip-audit, detect-secrets)
                                         ├─→ GitLab MR (API, 无 merge 权限)
                                         ├─→ EventBus: dev.mr-created → QA Agent
                                         └─→ OP 工单状态更新 (via sync-agent event)
```

### 事件契约

**需要注册到 `shared/schemas/event.py` EventTypes 的新事件**：

| 事件 | 方向 | 描述 | payload 关键字段 |
|------|------|------|-----------------|
| `pm.tasks-ready-for-dev` | PJM → dev | 任务已审批写入 OP，可以开始研发 | `wp_id`, `tasks: [{id, title, description, estimated_hours, parent_story, related_files}]` |
| `dev.workflow-created` | dev → EventBus | 工作流已创建，开始执行 | `task_id`, `workflow_id`, `node_count` |
| `dev.workflow-completed` | dev → EventBus | 工作流执行完成 | `task_id`, `workflow_id`, `duration_s` |
| `dev.mr-created` | dev → 飞书通知 | MR 已创建，通知人类 | `mr_url`, `wp_id`, `branch`, `risk_level` |
| `qa.acceptance-completed` | QA → dev | 验收结果回传 | `run_id`, `agent_name`, `summary: {l0_gate, ...}`, `findings` |
| `dev.task-completed` | dev → PJM(EventBus) | 任务全流程完成 | `wp_id`, `mr_url`, `duration_s` |
| `dev.task-failed` | dev → 飞书(直接) | 任务失败，需人工介入 | `wp_id`, `error`, `failed_node`, `runbook_url` |

**注意**：
- 使用 `pm.tasks-ready-for-dev` 替代直接监听 `pm.decompose-completed`，因为后者的 payload 不含完整 WBS 结构。**需修改 PJM Agent**：在 `decomposition_orchestrator.py` 的 `approve_decomposition()` 中，OPWriter 写入 OP 成功后发布此事件，payload 从 `decompose_result` 中提取完整 task 列表。
- `dev.retry-triggered` 为内部状态转换，不发布到 EventBus，仅记录在 `dev_agent_workflow_logs`。
- dev_agent 触发 QA 验收时复用已有的 `EventTypes.QA_RUN_REQUESTED`，**payload 必须符合 `QARunRequestedPayload` 契约**（必填 `agent_name`, 可选 `level`, `commit_sha`, `mr_iid`, `gitlab_project_id`, `requested_by`）。
- `dev.mr-created` 不作为 QA 触发事件，仅用于飞书通知。
- 所有新事件的 payload schema 须在 `shared/schemas/event_payloads.py` 中注册对应 Pydantic model，并加入 `EVENT_PAYLOAD_MODELS` 映射。
- `qa.acceptance-completed` 已存在于 EventTypes（`QA_ACCEPTANCE_COMPLETED`），dev_agent 直接消费。**注意**：QA 返回的 payload 不含 `wp_id`，dev_agent 需通过 `dev_agent_tasks` 表中的 `mr_iid → wp_id` 映射关联回任务。
- 需要新增的 EventTypes 枚举值：`PM_TASKS_READY_FOR_DEV`, `DEV_WORKFLOW_CREATED`, `DEV_WORKFLOW_COMPLETED`, `DEV_MR_CREATED`, `DEV_TASK_COMPLETED`, `DEV_TASK_FAILED`。
- **飞书通知由 dev_agent 直接调用 `shared/integrations/feishu/` 发送**，不依赖 sync_agent（sync_agent 不消费 EventBus 事件，是定时触发模型）。

### 幂等性保障

所有事件处理必须是幂等的（EventBus 提供 at-least-once 语义）：

1. **`pm.tasks-ready-for-dev` 去重**：`dev_agent_tasks.wp_id` 有 UNIQUE 约束，`handle_event()` 使用 `INSERT ... ON CONFLICT (wp_id) DO NOTHING`，已存在且非 failed 状态的任务跳过。
2. **GitLab MR 去重**：创建 MR 前检查同名分支是否已有 open MR，有则跳过。
3. **QA 结果去重**：`qa.acceptance-completed` 只在 `status=reviewing` 时处理，其他状态忽略（状态机守卫）。
4. **AgentForge 工作流去重**：workflow name 含 `wp_id`，天然幂等键。

### 任务风险分级 + Human-in-the-Loop

遵循 CLAUDE.md 和 PRD 的 HITL 原则，dev_agent 不做全自动闭环，而是按风险分级决定自动化程度：

| 风险级别 | 判定条件 | 人工介入点 |
|---------|---------|-----------|
| **LOW** | 文档、测试、配置、单文件 bugfix | 无额外审批，MR 仍需人类 Approve 后 merge |
| **MEDIUM** | 单 agent 功能实现、多文件修改 | MR 创建后需人工 Approve（默认行为） |
| **HIGH** | 跨 agent 交互、`shared/` 修改、安全相关、数据库 migration | 工作流规划后需人工审批才能执行 |
| **CRITICAL** | 架构变更、infra 修改、密钥/权限相关 | 禁止自动化，标记后转人工处理 |

**关键约束**：
- dev_agent 的 GitLab Token 使用 Project Access Token，scope 限定为 MR 创建，**无 merge 权限**
- GitLab `main` 分支 branch protection 要求 >= 1 人类 Approve
- HIGH 风险任务使用 ForgeClient 的 `signal()` 接口等待人工审批（飞书审批卡片）

## Directory Structure

```
agents/dev_agent/
├── __init__.py
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                # create_agent_app + ReconciliationLoop
│   └── metrics.py             # Prometheus 指标定义
├── service/
│   ├── __init__.py
│   └── agent.py               # DevAgent(BaseAgent) — handle_event + handle_request
├── core/
│   ├── __init__.py
│   ├── input_sanitizer.py     # PromptSafetyScanner 集成 + 输入净化
│   ├── risk_assessor.py       # 任务风险分级 (LOW/MEDIUM/HIGH/CRITICAL)
│   ├── workflow_planner.py    # LLM 驱动：Task → 动态工作流 JSON
│   ├── workflow_validator.py  # DAG 校验 + 路径白名单 + 二次安全扫描
│   ├── tool_router.py         # 规则引擎 + 配置覆盖：决定每步用哪个 AI 工具
│   ├── forge_client.py        # AgentForge Orchestrator API 客户端
│   ├── result_collector.py    # 工作流完成后：创建 MR + 发事件 + 更新状态
│   ├── security_scanner.py    # pip-audit + detect-secrets 扫描
│   └── prompts.py             # WorkflowPlanner 的 system prompt
├── db/
│   ├── __init__.py
│   ├── database.py            # AsyncSession
│   └── repository.py          # DevTaskRepository
├── models/
│   ├── __init__.py
│   ├── base.py                # ORM Base
│   ├── dev.py                 # ORM: dev_agent_tasks, dev_agent_workflow_logs
│   └── schemas.py             # Pydantic: WorkflowPlan, TaskAssignment, ToolRule
├── api/
│   ├── __init__.py
│   └── dev.py                 # REST: /api/v1/dev/tasks, /api/v1/dev/workflows/:id/status
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_agent.py              # handle_event 正常流 + 重复事件 + 未知事件
    │   ├── test_input_sanitizer.py    # prompt 注入检测
    │   ├── test_risk_assessor.py      # 风险分级逻辑
    │   ├── test_workflow_planner.py   # LLM 输出解析 + malformed JSON 处理
    │   ├── test_workflow_validator.py # DAG 校验 + 路径白名单
    │   ├── test_tool_router.py        # 规则匹配 + 冲突解决
    │   ├── test_result_collector.py   # 收尾流程 + 部分失败
    │   └── test_idempotency.py        # 重复事件 + 并发处理
    └── integration/
        ├── __init__.py
        ├── test_forge_client.py       # AgentForge API 集成
        └── test_e2e_flow.py           # 端到端流程

## Core Modules

### InputSanitizer

所有来自 PJM 的 Task 输入在进入 WorkflowPlanner 之前必须经过安全净化：

```python
class InputSanitizer:
    def __init__(self, safety_scanner: PromptSafetyScanner):
        self.scanner = safety_scanner  # 复用 shared/evolution/prompt_safety_scanner.py

    async def sanitize(self, task: TaskInput) -> SanitizedTask:
        """
        1. 长度限制: title <= 200 chars, description <= 5000 chars
        2. PromptSafetyScanner.scan() 检测 prompt 注入
        3. 字符过滤: 拒绝 shell metacharacters ($(), ``, |, >, ;) 在非代码上下文中
        4. 返回 SanitizedTask 或抛出 InputRejectedError
        """
```

### TaskRiskAssessor

根据任务内容自动评估风险等级：

```python
class TaskRiskAssessor:
    def assess(self, task: SanitizedTask) -> RiskLevel:
        """
        规则引擎判定:
        - CRITICAL: description 含 "migration", "infra", "permission", "secret"
        - HIGH: related_files 含 "shared/", 跨 agent, security 关键词
        - MEDIUM: 多文件修改, 新功能实现
        - LOW: 文档, 测试, 配置, 单文件 bugfix
        """
```

### WorkflowPlanner

LLM 驱动，把 PJM Task 转化为 AgentForge 可执行的工作流 JSON。

**输入**：
- PJM Task 信息（标题、描述、估时、所属 User Story）— 经过 InputSanitizer 净化
- 代码库上下文（相关文件路径、现有 agent 结构 — 通过 `git ls-files` + grep 获取，排除 `.aiignore` 中的敏感文件）
- 已有工作流模板作为 few-shot 参考（`agent-development.json`）

**输出**：与 AgentForge `agent-development.json` 同构的 JSON：

```json
{
  "name": "dev-task-wp-1234",
  "description": "给 chat_agent 添加多轮对话记忆功能",
  "nodes": [
    {
      "name": "plan",
      "type": "agent_task",
      "dependsOn": [],
      "config": { "cliTool": "codex", "prompt": "...", "tags": ["plan"] }
    },
    {
      "name": "impl-memory-store",
      "type": "agent_task",
      "dependsOn": ["plan"],
      "config": { "cliTool": "claude", "prompt": "...", "tags": ["implement", "core"] }
    }
  ]
}
```

**LLM System Prompt 约束**：
1. 每个 node 的 prompt 必须引用具体文件路径，不能抽象描述
2. 必须包含 `review` 和 `acceptance` 节点（质量门禁）
3. 可并行的 node 用相同的 `dependsOn` 表达
4. 单个 node 的工作量 ≤ 4 小时
5. prompt 中必须引用 `CLAUDE.md` 编码规范

**LLM 输出鲁棒性**：
1. JSON 提取层：strip markdown fences → `json.loads` → fallback 正则提取第一个 `{...}` 块
2. DAG 校验：拓扑排序检测循环依赖
3. LLM 调用超时 60s，最多重试 2 次
4. 生成的 node prompt 经过 PromptSafetyScanner 二次扫描

**LLM 调用失败 Fallback**：
- 根据任务 tags 匹配预定义模板（`new-agent-template.json`、`bugfix-template.json` 等）
- 无匹配模板时标记为 `planning_failed`，通知人工

### WorkflowValidator

对 WorkflowPlanner 输出进行安全和结构校验：

```python
class WorkflowValidator:
    async def validate(self, plan: WorkflowPlan) -> ValidationResult:
        """
        1. Pydantic schema 校验（结构完整性）
        2. DAG 校验（拓扑排序，检测循环依赖）
        3. 路径白名单：node prompt 中引用的文件路径必须在 agents/ 或 shared/ 下
        4. 必须包含 review + acceptance 节点
        5. 单 node 估时 <= 4 小时
        6. PromptSafetyScanner 对每个 node prompt 做二次扫描
        """
```

### ToolRouter

两层决策机制：

**Layer 1 — 规则引擎（默认，OR 语义，first-match-wins）**：

```python
class ToolRule(BaseModel):
    match_tags: list[str]           # 任意 tag 命中即匹配 (OR)
    tool: Literal["claude", "gemini", "codex"]
    priority: int = 0               # 高优先级先匹配

DEFAULT_RULES = [
    ToolRule(match_tags=["plan", "review", "architecture"], tool="codex", priority=10),
    ToolRule(match_tags=["implement", "fix", "refactor", "core"], tool="claude", priority=5),
    ToolRule(match_tags=["models", "api", "tests", "docs", "config"], tool="gemini", priority=5),
    ToolRule(match_tags=["acceptance", "packaging"], tool="claude", priority=5),
]
```

**Layer 2 — 配置覆盖**：

从飞书 Bitable 或 OP 自定义字段读取覆盖规则。

**优先级**：配置覆盖 > 规则引擎（按 priority 排序，first-match-wins）> 默认(claude)

**工具健康感知**：主工具 API 不可用时（CircuitBreaker OPEN），自动 fallback 到备选工具（codex → claude → gemini 链）。

### ForgeClient

封装 AgentForge Orchestrator HTTP API：

```python
class ForgeClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=30, write=10),
            limits=httpx.Limits(max_connections=10),
        )
        self._circuit_breaker = CircuitBreaker(...)

    async def create_workflow(self, plan: WorkflowPlan) -> str:
        """POST /api/v1/workflows → workflow_id"""

    async def run_workflow(self, workflow_id: str) -> None:
        """POST /api/v1/workflows/:id/run"""

    async def get_status(self, workflow_id: str) -> WorkflowStatus:
        """GET /api/v1/workflows/:id/status"""

    async def signal(self, workflow_id: str, node_id: str, decision: str) -> None:
        """POST /api/v1/workflows/:id/signal（HIGH 风险任务人工审批）"""
```

**注意**：AgentForge Orchestrator 当前不支持 webhook 回调，因此采用轮询方式。设计抽象为 `WorkflowStatusWatcher` 接口，未来可替换为 webhook 实现。

**HTTP 容错**：
- 请求超时：connect=5s, read=30s, write=10s
- 响应体限制 10MB
- 5xx 错误重试 2 次，指数退避
- 4xx 错误不重试
- CircuitBreaker 保护

### ReconciliationLoop（替代 StatusPoller）

采用 Kubernetes 控制器风格的 reconciliation 模式，单个全局 APScheduler job 定时扫描所有活跃任务：

```python
async def reconcile():
    """每 30 秒触发一次，扫描所有 status IN ('executing', 'reviewing') 的任务"""
    tasks = await repo.list_active_tasks()
    for task in tasks:
        elapsed = now() - task.workflow_started_at
        if elapsed < 10min and (now() - task.last_polled_at) < 30s:
            continue  # 未到轮询时间
        if elapsed < 2h and (now() - task.last_polled_at) < 2min:
            continue
        if elapsed < 6h and (now() - task.last_polled_at) < 5min:
            continue
        if elapsed >= 6h:
            await mark_timeout(task)
            continue
        # 执行轮询
        status = await forge_client.get_status(task.workflow_id)
        await repo.update_last_polled(task.id)
        if status.completed:
            await result_collector.handle_completion(task, status)
```

**重启恢复**：agent 启动时扫描 `dev_agent_tasks` 中 `status IN ('executing', 'reviewing')` 的记录，根据 `workflow_started_at` 自动恢复到正确的轮询间隔阶段。

**部署竞争防护**：使用 PostgreSQL advisory lock 确保同一时刻只有一个实例执行 reconciliation：

```sql
SELECT pg_try_advisory_lock(hashtext('dev_agent_reconcile'))
```

**AgentForge 恢复后限流**：CircuitBreaker 从 OPEN → CLOSED 后，前 5 分钟每分钟最多启动 1 个新工作流，5-15 分钟每分钟最多 2 个，15 分钟后恢复正常并发。

### ResultCollector

工作流完成后执行状态机驱动的收尾流程：

**状态机**：`executing → security_scanning → mr_creating → mr_created → qa_triggered → reviewing → [completed|failed]`

每步完成后更新 `dev_agent_tasks.status`，失败时记录失败步骤，ReconciliationLoop 自动检测卡住的任务并重试对应步骤。

**Step 0 — 安全扫描**：
- `pip-audit` 扫描新引入依赖的已知 CVE
- `detect-secrets` 检测代码中的硬编码密钥
- 安全问题自动阻断 MR 创建，标记失败

**Step 1 — 创建 GitLab MR**：

```python
mr = gitlab_client.create_mr(
    source_branch=f"dev/wp-{wp_id}",
    target_branch="main",
    title=f"[DevAgent] {task_title}",
    description=f"由 dev_agent 自动生成\n\n"
                f"- OP 工单: #{wp_id}\n"
                f"- 工作流: {workflow_id}\n"
                f"- AI 工具: {tools_used}\n"
                f"- 风险等级: {risk_level}\n\n"
                f"## 安全审查 Checklist\n"
                f"- [ ] 新依赖审查\n"
                f"- [ ] 安全相关文件变更审查\n"
                f"- [ ] Secret/凭证泄露检查\n",
)
```

GitLab MR 创建有独立的 CircuitBreaker + 3 次指数退避重试。

**Step 2 — 触发 QA 验收**（符合 `QARunRequestedPayload` 契约）：

```python
await event_bus.publish(Event(
    event_type=EventTypes.QA_RUN_REQUESTED,
    payload={
        "agent_name": target_agent_name,  # 被验收 agent 名，如 "chat-agent"
        "level": "all",
        "commit_sha": commit_sha,
        "mr_iid": mr.iid,
        "gitlab_project_id": settings.gitlab_project_id,
        "requested_by": "dev-agent",
        "reason": f"Auto-triggered for WP#{wp_id}",
    },
))
# 在 dev_agent_tasks 中记录 mr_iid，用于 QA 结果回传时关联 wp_id
```

**Step 3 — 根据 QA 结果回写状态**：

| QA 结果 | 动作 |
|---------|------|
| L0 PASS + L1/L2 无 critical | 更新 OP 工单状态 + 飞书通知成功（MR 仍需人类 Approve 后 merge） |
| L0 FAIL | 自动触发一次修复工作流（限 1 次重试）→ 再次提 MR → 再次 QA |
| 修复后仍 FAIL | 标记失败 + 飞书通知需人工介入（含 runbook 链接） |

## Configuration

需要在 `shared/config.py` 中添加的配置项：

```python
# AgentForge Orchestrator
agentforge_api_url: str = "http://localhost:4010"
agentforge_token: SecretStr = SecretStr("")  # Pydantic SecretStr，防止 repr/str 泄露

# GitLab API (ResultCollector 创建 MR, 无 merge 权限)
gitlab_api_url: str = ""
gitlab_token: SecretStr = SecretStr("")      # Project Access Token, scope=api (MR only)
gitlab_project_id: int = 0

# 工作流并发控制
dev_max_concurrent_workflows: int = 5
dev_workflow_timeout_hours: int = 6

# LLM 成本控制
dev_llm_daily_token_limit: int = 500_000
dev_llm_per_task_token_limit: int = 20_000
```

**环境变量**：`AGENTFORGE_API_URL`, `AGENTFORGE_TOKEN`, `GITLAB_API_URL`, `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `DEV_MAX_CONCURRENT_WORKFLOWS`, `DEV_LLM_DAILY_TOKEN_LIMIT`

**Secret 管理**：
- Token 使用 Pydantic `SecretStr`，防止 `repr()` / `str()` / 日志泄露
- ForgeClient 和 GitLabClient 添加 log redaction middleware，过滤 `Authorization` header
- 禁止 token 出现在 Event payload 和 `workflow_json` JSONB 中 — 序列化前 token scrubbing
- GitLab Token 使用 Project Access Token（非 Personal），scope 仅 MR 操作
- Token rotation 策略：建议 90 天轮换

### handle_request Actions

DevAgent 支持的 request actions（供 API 层和调度器调用）：

| Action | 描述 |
|--------|------|
| `get_task_status` | 查询指定 wp_id 的研发状态 |
| `list_active_workflows` | 列出当前正在执行的工作流 |
| `retry_task` | 手动重试失败的任务 |
| `cancel_workflow` | 取消正在执行的工作流 |
| `approve_workflow` | 人工审批 HIGH 风险任务的工作流 |

## Database Schema

```sql
-- 跟踪每个 PJM Task 的研发状态
CREATE TABLE dev_agent_tasks (
    id                  TEXT PRIMARY KEY,            -- ULID
    wp_id               INTEGER NOT NULL UNIQUE,     -- OpenProject work package ID (幂等键)
    task_title          TEXT,
    risk_level          TEXT DEFAULT 'MEDIUM'         -- LOW|MEDIUM|HIGH|CRITICAL
                        CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    status              TEXT DEFAULT 'pending'
                        CHECK (status IN (
                            'pending','planning',
                            'awaiting_approval',
                            'executing','security_scanning',
                            'mr_creating','mr_created',
                            'qa_triggered','reviewing',
                            'completed','failed','expired'
                        )),
    workflow_id         TEXT,                         -- AgentForge workflow ID
    mr_iid              INTEGER,                     -- GitLab MR internal ID (QA 结果回传关联键)
    mr_url              TEXT,                         -- GitLab MR URL
    retry_count         INTEGER DEFAULT 0,
    error_message       TEXT,
    failed_step         TEXT,                         -- 失败的步骤名（用于定向重试）
    workflow_started_at TIMESTAMP,                    -- 工作流开始执行时间（轮询阶段计算基准）
    last_polled_at      TIMESTAMP,                   -- 最近一次轮询时间
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW(),
    completed_at        TIMESTAMP
);

CREATE INDEX idx_dev_tasks_status ON dev_agent_tasks(status, created_at);
CREATE INDEX idx_dev_tasks_workflow_id ON dev_agent_tasks(workflow_id);

-- 工作流执行历史 + LLM 审计日志
CREATE TABLE dev_agent_workflow_logs (
    id                  TEXT PRIMARY KEY,             -- ULID
    task_id             TEXT REFERENCES dev_agent_tasks(id),
    workflow_json       JSONB,                        -- 动态生成的完整工作流（token scrubbed）
    llm_request_prompt  TEXT,                         -- WorkflowPlanner LLM 输入（审计用）
    llm_response_raw    TEXT,                         -- WorkflowPlanner LLM 原始输出（审计用）
    tool_routing_json   JSONB,                        -- ToolRouter 决策记录
    node_results        JSONB,                        -- 每个 node 的执行结果（实时更新）
    total_duration_s    INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);
```

**数据保留策略**：
- `dev_agent_workflow_logs` 保留 90 天（满足 SOC2 审计要求）
- 超过 90 天归档到对象存储（如需 L1 自进化分析）
- `dev_agent_tasks` 中 `failed`/`expired` 状态超过 7 天自动归档

**积压任务 TTL**：
- `pending` 超过 24 小时 → 自动标记 `expired` + 通知
- 提供 `/api/v1/dev/tasks/failed` 接口供 oncall 批量重试或关闭

## Concurrency Control

当 PJM 同时分解多个任务时，dev_agent 需要控制并发：

- **最大并发工作流数**：`dev_max_concurrent_workflows`（默认 5），超出后新任务排队等待
- **队列策略**：FIFO，持久化在 `dev_agent_tasks` 表中（status=pending）
- **原子出队**：使用 `SELECT ... WHERE status='pending' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED`，在同一事务中更新 status 为 `planning`，避免竞态条件
- **AgentForge 恢复后限流**：避免积压任务同时涌入造成惊群效应

## SLO & Alerting

| SLO | 目标 | 告警阈值 |
|-----|------|---------|
| 任务成功率（30 天滚动） | >= 90% | error budget 消耗 > 50% warn, > 80% page |
| 端到端耗时 P95 | < 4 小时 | P95 > 4h 连续 30 分钟 |
| 轮询延迟 P99（任务完成到感知） | < 10 分钟 | P99 > 10min |
| 队列深度 | < 20 | > 20 持续 10 分钟 |

## Metrics (Prometheus)

### 业务指标

| 指标 | 类型 | 描述 |
|------|------|------|
| `dev_workflows_created_total` | Counter | 创建的工作流总数 |
| `dev_tasks_completed_total` | Counter | 成功完成的任务数 |
| `dev_tasks_failed_total{reason}` | Counter | 失败的任务数（按故障原因分标签） |
| `dev_task_duration_seconds` | Histogram | 任务从创建到完成的耗时 |
| `dev_retry_count_total` | Counter | 自动重试次数 |
| `dev_active_workflows` | Gauge | 当前正在执行的工作流数 |
| `dev_pending_tasks_count` | Gauge | 排队等待的任务数 |

### 基础设施指标

| 指标 | 类型 | 描述 |
|------|------|------|
| `dev_llm_call_duration_seconds` | Histogram | WorkflowPlanner LLM 调用延迟 |
| `dev_llm_call_errors_total` | Counter | LLM 调用失败次数 |
| `dev_llm_tokens_used_total` | Counter | LLM token 消耗总量 |
| `dev_forge_api_latency_seconds` | Histogram | ForgeClient API 调用延迟 |
| `dev_forge_poll_errors_total` | Counter | 轮询失败次数 |
| `dev_mr_creation_errors_total` | Counter | MR 创建失败次数 |
| `dev_circuit_breaker_state{target}` | Gauge | 断路器状态 (0=closed, 1=open, 2=half_open) |

## Evolution (L1)

dev_agent 注册一个 Skill seed：

| Skill | ID | Purpose | Model |
|-------|----|---------|-------|
| Workflow Planning | `dev-agent:workflow-plan` | Task → 动态工作流 | claude-opus-4 |

通过 L1 自进化，WorkflowPlanner 的 system prompt 可根据历史执行结果自动优化（如：某类任务发现缺少 review 步骤导致失败率高，自动在 prompt 中强化 review 约束）。

## Security

### Prompt 注入防御

1. **输入净化**：Task title/description 经 `InputSanitizer` + `PromptSafetyScanner` 检查
2. **输出校验**：LLM 生成的每个 node prompt 经二次 `PromptSafetyScanner` 扫描
3. **路径白名单**：node prompt 中引用的文件路径必须在 `agents/` 或 `shared/` 下
4. **输入长度限制**：title <= 200 chars, description <= 5000 chars

### 供应链安全

1. **依赖扫描**：MR 创建前运行 `pip-audit` + `safety check`
2. **Secret 检测**：`detect-secrets` 扫描生成代码中的硬编码密钥
3. **人类审查**：所有 MR 必须人类 Approve 后才能 merge（branch protection）

### 数据保护

1. **`.aiignore` 机制**：排除 `.env*`, `*secret*`, `*credential*`, `*key*` 等敏感文件不被发送至 LLM
2. **日志脱敏**：ForgeClient/GitLabClient 的 Authorization header 在日志中 redacted
3. **LLM 审计**：所有 LLM input/output 记录到 `dev_agent_workflow_logs`，保留 90 天

### 权限最小化

1. dev_agent GitLab Token: Project Access Token, 仅 MR 创建权限，无 merge 权限
2. AgentForge Token: 仅 workflow CRUD 权限
3. EventBus: 仅发布 `dev.*` 事件，消费 `pm.tasks-ready-for-dev` 和 `qa.acceptance-completed`

## State Transition Matrix

合法状态迁移路径（禁止其他方向的迁移）：

```
pending ──→ planning ──→ awaiting_approval ──→ executing
  │                           │ (rejected)        │
  │                           ▼                   ▼
  │                         failed          security_scanning
  │                                               │
  ▼ (24h TTL)                                     ▼
expired                                     mr_creating
                                                  │
                                                  ▼
                                            mr_created ──→ qa_triggered ──→ reviewing
                                                                              │
                                                          ┌──────────────────┤
                                                          ▼                  ▼
                                                      completed           failed
                                                                     (retry_count<1? → planning)
```

**异常路径**：
- 任何状态 → `failed`（超时、外部错误、安全扫描失败等）
- `failed` + `retry_count < 1` → `planning`（限 1 次自动重试）
- `pending` + 超过 24h → `expired`
- `awaiting_approval` + 被拒绝 → `failed`

## Health Check

```
GET /healthz          — Liveness: 进程存活（always 200 unless deadlocked）
GET /readyz           — Readiness: DB 连接可用 + EventBus 可订阅
                        503 if DB/EventBus unavailable → K8s 停止路由流量
```

## Observability

### 结构化日志

使用 `structlog` JSON 格式，所有日志携带 `trace_id`：

```json
{"timestamp": "...", "level": "info", "event": "workflow_created", "trace_id": "...", "wp_id": 1234, "workflow_id": "..."}
```

Authorization header 等敏感信息在日志中自动 redacted。

### Distributed Tracing

集成 OpenTelemetry SDK，trace 覆盖：
- `handle_event` → `InputSanitizer` → `WorkflowPlanner`(LLM call) → `ForgeClient` → `ResultCollector`
- 跨 agent 链路通过 Event 的 `trace_id` 串联（PJM → dev → QA → dev）

## Graceful Shutdown

1. shutdown 时取消所有进行中的 HTTP 请求（`httpx.AsyncClient.aclose()`）
2. `executing` 状态的任务保持不变（ReconciliationLoop 重启后自动恢复轮询，不需要额外状态）
3. APScheduler 优雅停止，等待当前 reconcile cycle 完成

## Database Migration

所有新表通过 Alembic migration 创建，遵循现有 agent 的迁移模式。ORM 定义在 `models/dev.py`，SQL schema 仅为说明性示例。

## Success Metrics (KPI)

| KPI | 基线 | 目标 | 数据来源 |
|-----|------|------|---------|
| 端到端交付时间 | 人工基线（先测量） | 减少 60% | `dev_agent_tasks.created_at → completed_at` |
| MR 首次通过率 | 0% (新系统) | > 50% in 30 days | QA acceptance_runs |
| 人工介入率 | 100% (当前) | < 30% | `dev.task-failed` / 总任务数 |
| 代码质量分数 | 人工基线 | 持平或更优 | QA L1/L2 报告趋势 |

## Risk & Mitigation

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| Prompt 注入导致恶意代码 | H | InputSanitizer + PromptSafetyScanner + 二次扫描 + 人类 Approve MR |
| LLM 生成的工作流质量不稳定 | H | Pydantic + DAG 校验 + review/acceptance 硬约束 + fallback 模板 |
| AgentForge 平台不可用 | M | CircuitBreaker + 持久化队列 + 恢复后限流 |
| 自动修复循环 | H | 重试限制 1 次，超过后人工介入 |
| 工具分配不合理 | L | 规则引擎 + 配置覆盖 + 健康感知 failover + L1 自进化 |
| MR 冲突 | M | 独立分支 `dev/wp-{id}`，冲突时标记失败通知人工 |
| Secret 泄露 | H | SecretStr + log redaction + token scrubbing + 最小权限 |
| 成本失控 | M | daily/per-task token limit + 成本指标监控 |
| 轮询状态丢失（重启） | M | DB 持久化 + advisory lock + reconciliation 模式 |
| 级联故障 | M | 独立 CircuitBreaker per 外部依赖 + 队列深度告警 |

## Runbook

每个 `dev.task-failed` 告警包含 runbook 链接：

1. **查看工作流日志**：`SELECT * FROM dev_agent_workflow_logs WHERE task_id = ?`
2. **手动重试**：`POST /api/v1/dev/tasks/{id}/retry`
3. **取消卡住的工作流**：`POST /api/v1/dev/workflows/{id}/cancel`
4. **AgentForge 不可用诊断**：检查 `dev_circuit_breaker_state{target="agentforge"}` 指标
5. **断路器手动复位**：`POST /api/v1/dev/circuit-breaker/reset`

## Cross-Agent Changes Required

dev_agent 的实现需要修改以下现有模块：

### 1. PJM Agent（必须，impl-contracts 阶段）

- **`agents/pjm_agent/core/decomposition_orchestrator.py`**：`approve_decomposition()` 中 OPWriter 写入成功后，新增发布 `pm.tasks-ready-for-dev` 事件。payload 从 `decompose_result` 中提取完整 task 列表（title, description, estimated_hours, related_files）。
- **`agents/pjm_agent/service/agent.py`**：`published_events` 中添加 `EventTypes.PM_TASKS_READY_FOR_DEV`。

### 2. shared/schemas（必须，impl-contracts 阶段）

- **`shared/schemas/event.py`**：新增 6 个 EventTypes 常量。
- **`shared/schemas/event_payloads.py`**：新增 6 个 Pydantic payload model + 注册到 `EVENT_PAYLOAD_MODELS`。

### 3. shared/config.py（必须）

新增 AgentForge / GitLab / 并发 / LLM 成本相关配置项。

### 4. Docker 基础设施（必须，packaging 阶段）

- **端口分配**：dev_agent 使用 `8015`（现有：8000-ai-core, 8010-sync, 8011-analysis, 8012-pjm, 8013-chat, 8014-qa）
- **Redis DB**：dev_agent 使用 DB `6`（现有：0-5 已分配）
- **docker-compose.yml**：新增 dev-agent service
- **Prometheus**：新增 scrape job

### 5. 不需修改的模块

- **QA Agent**：已支持 `QA_RUN_REQUESTED`，dev_agent 需适配其 payload 契约（`QARunRequestedPayload`），无需修改 QA 代码。
- **sync_agent**：dev_agent 直接调用 `shared/integrations/feishu/` 发送飞书通知，不依赖 sync_agent。

## MVP Rollout Strategy

渐进式上线，建立信任后逐步放权：

1. **Week 1-2**：仅处理 LOW 风险任务（文档、测试），所有 MR 人工 review
2. **Week 3-4**：开放 MEDIUM 风险任务，收集 MR 首次通过率数据
3. **Month 2+**：根据数据决定是否开放 HIGH 风险任务的自动化执行（保留人工审批）
4. **CRITICAL 任务永不自动化**
