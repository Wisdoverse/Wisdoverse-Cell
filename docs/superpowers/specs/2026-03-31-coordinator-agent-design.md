# Coordinator Agent Design Spec

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> Wisdoverse Cell AI 原生运营公司的全局编排引擎

## 1. 定位

Coordinator Agent 是 Wisdoverse Cell 的 **CEO 角色** — 拥有全局视野，理解所有 Agent 的状态和输出，做出跨 Agent 的智能决策，生成完整指令驱动工作流。

**核心原则**（借鉴 Claude Code Coordinator Mode）：
- 综合分析后再发指令，不做 passthrough
- 每条指令自包含所有上下文（对独立 Agent）
- 不猜测 Worker 结果，只等通知
- 能自己处理的不委派

## 2. 组织架构

```
人类（飞书/企微）
    ↕
channel_gateway（消息路由）
    ↕
chat_agent（意图理解 + 简单查询直接回 + 复杂指令升级）
    ↕ 仅复杂指令
┌─ Coordinator Agent（CEO）──────────────────────────────┐
│                                                        │
│  requirement_mgr (PM)  ←→  PJM 组（直接协作）           │
│  需求/PRD/产品决策          pjm_agent   任务拆解/审批   │
│                            sync_agent   飞书同步        │
│                            analysis_agt 风险/数据分析   │
│                                                        │
│  dev_agent（执行·开发）    qa_agent（执行·验收）          │
│                                                        │
│  evolution_agent（观察全局，优化系统）                    │
└────────────────────────────────────────────────────────┘
```

### 角色关系

| 角色 | 类比 | 与 Coordinator 的关系 |
|------|------|----------------------|
| chat_agent | 前台 | Coordinator **前面**，做意图翻译 |
| requirement_manager (PM) | 产品经理 | Coordinator 下，直接接受战略指令 |
| PJM 组 | PMO 项目管理办公室 | Coordinator 下，接受指令执行 |
| dev_agent | 工程团队 | Coordinator 下，纯执行者 |
| qa_agent | QA 团队 | Coordinator 下，纯执行者 |
| evolution_agent | 内部效能团队 | Coordinator 下，观察并优化 |
| channel_gateway | 基础设施 | 不在编排范围内 |

### 协作模式

- **PM ↔ PJM 组**：直接协作通道。PM 产出 PRD 后直接交 PJM 拆任务，不需要经过 Coordinator。Coordinator 监听，异常/冲突时介入仲裁。
- **Coordinator → PJM 组**：增量指令 + 共享 Scratchpad。PJM 组有自主判断力。
- **Coordinator → 独立 Agent**（dev/qa）：完整自包含指令。执行者拿到指令即可工作。

## 3. 核心设计决策

| 维度 | 决策 | 理由 |
|------|------|------|
| 智能程度 | 智能指挥官 | 综合分析各 Agent 结果，生成下一步完整指令，有判断力 |
| 组织关系 | 所有 Agent 之上 | CEO 角色，全局视野 |
| 运行模式 | 事件驱动（AgentRuntime 内） | 通过 handle_event() 接收所有输入，兼容 EvolutionPlugin 等 runtime 插件 |
| 上下文来源 | 全局 Scratchpad + 自动压缩 | Scratchpad 主存 + 定期压缩旧内容 |
| 指令方式 | 混合 | PJM 组增量指令，独立 Agent 完整自包含指令 |
| 人类交互 | 不直面人类 | chat_agent 做翻译层，Coordinator 是内部角色 |
| 状态管理 | 有持久化状态 | 工作流、Agent 状态、决策队列持久化到磁盘/DB |
| chat_agent 角色 | 保持现有能力 | 简单查询直接处理，复杂指令升级给 Coordinator |

## 4. Coordinator 运行模型

### 基于 AgentRuntime 的事件驱动架构

Coordinator 是标准的 `BaseAgent`，通过 `create_agent_app()` 启动，运行在 `AgentRuntime` 内。
这确保 `EvolutionPlugin` 等 runtime 插件能观察 Coordinator 的所有行为。

**不使用自定义轮询循环**。所有输入统一通过 `handle_event()` 进入，由 EventBus 驱动。

```python
class CoordinatorAgent(BaseAgent):
    """
    全局编排引擎。事件驱动，通过 handle_event() 接收所有输入。
    所有事件类型统一在 subscribed_events 中声明，
    EventBus 投递到 handle_event()，保证单一入口、无重复处理。
    """

    def __init__(self):
        super().__init__(
            agent_id="coordinator",
            agent_name="Coordinator",
            subscribed_events=[
                # chat_agent 升级的指令
                EventTypes.COORDINATOR_COMMAND,
                # Agent 任务完成通知（统一通道，替代 legacy 终态事件）
                EventTypes.TASK_NOTIFICATION,
                # Agent 实时进度上报
                EventTypes.TASK_PROGRESS,
                # PM ↔ PJM 协作事件（监听用，异常时介入）
                EventTypes.PM_PRD_READY,
                EventTypes.PM_DECOMPOSE_COMPLETED,
                EventTypes.PM_DECOMPOSITION_FAILED,
                # 系统告警
                EventTypes.ANALYSIS_RISK_DETECTED,
            ],
            published_events=[
                EventTypes.COORDINATOR_RESPONSE,
                EventTypes.COORDINATOR_DISPATCH,
            ],
        )
        self._scratchpad = Scratchpad()
        self._state_store = CoordinatorStateStore()

    async def handle_event(self, event: Event) -> list[Event]:
        """单一事件入口。所有输入都是 Event，无二次收集。"""

        # 1. 分类事件
        classified = self._classify_event(event)

        # 2. 读取当前状态
        scratchpad = await self._scratchpad.read_incremental()
        agent_states = await self._state_store.get_agent_states()
        pending = await self._state_store.get_pending_decisions()

        # 3. LLM 综合决策
        context = self._build_context(
            scratchpad=scratchpad,
            agent_states=agent_states,
            incoming=classified,
            pending_decisions=pending,
        )
        decisions = await self._think(context)

        # 4. 转换决策为 Event 列表（通过 EventBus 分发）
        outgoing_events = []
        for decision in decisions:
            outgoing_events.append(self._decision_to_event(decision))

        # 5. 更新状态
        await self._scratchpad.update(decisions)
        await self._state_store.persist(decisions)

        # 6. 压缩检查（fire-and-forget，不阻塞 handle_event）
        if self._scratchpad.should_compact():
            asyncio.create_task(self._scratchpad.compact())

        return outgoing_events
```

### 事件分类

```python
def _classify_event(self, event: Event) -> ClassifiedEvent:
    """将 EventBus 事件分类为 Coordinator 内部类型"""
    if event.event_type == EventTypes.COORDINATOR_COMMAND:
        return ClassifiedEvent(kind="command", data=CoordinatorCommand(**event.payload))
    elif event.event_type == EventTypes.TASK_NOTIFICATION:
        return ClassifiedEvent(kind="notification", data=TaskNotification(**event.payload))
    else:
        return ClassifiedEvent(kind="event", data=event)
```

### 指令分发（通过现有事件契约）

Coordinator **不发明新的通信通道**。它通过发布现有的 EventTypes 来驱动 Worker Agent：

```python
def _decision_to_event(self, decision: Decision) -> Event:
    """将决策转换为目标 Agent 能理解的 Event。

    关键原则：使用现有事件类型和 payload 契约，不发明新 schema。
    Coordinator 附加的额外字段（instruction, workflow_id）作为可选扩展，
    Agent 有则用，无则走原逻辑。
    """
    target = decision.target_agent

    # 对 requirement_manager：发 coordinator.dispatch，
    # RM 需要新增订阅此事件类型
    if target == "requirement-manager":
        return Event.create(
            event_type=EventTypes.COORDINATOR_DISPATCH,
            source_agent="coordinator",
            payload={
                "target_agent": target,
                "task_id": decision.task_id,
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    # 对 dev_agent：通过现有 pm.tasks-ready-for-dev 事件
    # 必须包含 dev_agent 期望的 wp_id + tasks[] 契约字段
    if target == "dev-agent":
        return Event.create(
            event_type=EventTypes.PM_TASKS_READY_FOR_DEV,
            source_agent="coordinator",
            payload={
                # 现有契约必填字段
                "wp_id": decision.context.get("wp_id"),
                "tasks": decision.context.get("tasks", []),
                # Coordinator 扩展（可选，dev_agent 有则用）
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    # 对 qa_agent：通过现有 qa.run-requested 事件
    # 必须兼容 QARunRequestedPayload 的 required 字段
    if target == "qa-agent":
        return Event.create(
            event_type=EventTypes.QA_RUN_REQUESTED,
            source_agent="coordinator",
            payload={
                # 现有契约必填字段（来自 QARunRequestedPayload）
                "agent_name": decision.context.get("agent_name"),
                "commit_sha": decision.context.get("commit_sha"),
                "mr_iid": decision.context.get("mr_iid"),
                "gitlab_project_id": decision.context.get("gitlab_project_id"),
                "files_changed": decision.context.get("files_changed", []),
                "requested_by": "coordinator",
                # Coordinator 扩展（可选）
                "instruction": decision.instruction,
                "workflow_id": decision.workflow_id,
            },
        )

    # 对 chat_agent：回传结果
    if target == "chat-agent":
        return Event.create(
            event_type=EventTypes.COORDINATOR_RESPONSE,
            source_agent="coordinator",
            payload=CoordinatorResponse(
                command_id=decision.command_id,
                status=decision.status,
                summary=decision.summary,
            ).model_dump(),
        )

    # 对 PJM 组：增量指令
    return Event.create(
        event_type=EventTypes.COORDINATOR_DISPATCH,
        source_agent="coordinator",
        payload={
            "target_agent": target,
            "task_id": decision.task_id,
            "instruction": decision.instruction,
            "scratchpad_ref": decision.scratchpad_ref,
        },
    )
```

### _think(context) 决策引擎

调用 LLM（Claude）进行综合分析，输入为结构化上下文，输出为决策列表。每个决策包含：
- `target_agent`: 目标 Agent ID
- `action`: 指令类型（dispatch_task / continue_task / escalate / wait）
- `instruction`: 完整指令内容
- `priority`: 优先级
- `reasoning`: 决策理由（用于 Scratchpad 记录和 evolution_agent 分析）

## 5. 全局 Scratchpad

### 结构

```
scratchpad/
  global_status.md              # 全局项目状态摘要（Coordinator 每轮更新）
  workflows/
    {workflow_id}.md            # 每个活跃工作流的进展记录
  agents/
    {agent_id}_output.md        # 各 Agent 最新关键输出
  decisions/
    pending.md                  # 待决策队列
    log.md                      # 决策历史（定期压缩）
```

### 读写规则

| 角色 | 读 | 写 |
|------|----|----|
| Coordinator | 全部 | 全部 |
| PJM 组 | `global_status.md` + 自己的 `agents/` | 自己的 `agents/{id}_output.md` |
| 独立 Agent | 不读（指令已自包含） | 自己的 `agents/{id}_output.md` |
| evolution_agent | 全部（只读分析） | `agents/evolution_output.md` |

### 压缩策略（借鉴 Claude Code 三层 Compaction）

| 层级 | 触发条件 | 操作 |
|------|---------|------|
| L1 Micro | Agent output > 阈值 | 清除旧 output，保留最新 |
| L2 Memory | Scratchpad token 增量 > 5000 | 提取关键信息到 `global_status.md` |
| L3 Full | Scratchpad 总量 > 上限 | LLM 生成全局摘要，替换旧内容 |

## 6. Task Notification 协议

Agent 完成任务后通过 EventBus 发送结构化通知（借鉴 Claude Code `<task-notification>`）：

```python
class TaskNotification(BaseModel):
    """Agent → Coordinator 的任务完成通知"""
    task_id: str                    # 工作流内唯一
    agent_id: str                   # 执行 Agent
    status: Literal["completed", "failed", "blocked"]
    summary: str                    # 人类可读摘要
    result: dict | None = None      # 结构化结果
    usage: TaskUsage | None = None  # token/耗时统计
    error: str | None = None        # 失败原因

class TaskUsage(BaseModel):
    duration_ms: int
    llm_tokens: int = 0
    tool_calls: int = 0
```

Coordinator 收到通知后进入 Synthesis 步骤 — 综合分析结果，决定下一步。

### TaskNotification 与 Legacy 事件的迁移策略

现有 Agent 已经发布 legacy 终态事件（`dev.task-completed`, `qa.acceptance-completed` 等），
其他 Agent 和外部系统可能依赖这些事件。迁移分两阶段避免重复处理：

**阶段 1（共存期）**：Agent 同时发布 legacy 事件 + `task.notification`。
但 **Coordinator 只订阅 `task.notification`**，不订阅 legacy 终态事件（`dev.task-*`, `qa.*`）。
Legacy 事件继续被其他消费者（如 pjm_agent 监听 `dev.task-completed` 更新看板）正常消费。
这样不会重复触发 Coordinator synthesis。

**阶段 2（收敛期）**：其他消费者逐步迁移到 `task.notification`，legacy 终态事件废弃。

关键：**Coordinator 的 subscribed_events 不包含 legacy 终态事件**（见 §4），
所以即使 Agent 同时发两种事件，Coordinator 也只收到一次。

## 7. chat_agent 升级判断

chat_agent 在以下情况升级给 Coordinator：

```python
ESCALATION_TRIGGERS = [
    "涉及需求→开发→QA 全链路",
    "需要多个 Agent 协作",
    "战略级指令（暂停/启动/优先级调整）",
    "chat_agent 自身判断无法处理",
    "人类明确要求（@coordinator）",
]
```

升级时 chat_agent 发送结构化指令：

```python
class CoordinatorCommand(BaseModel):
    """chat_agent → Coordinator 的升级指令"""
    command_id: str
    intent: str                     # 提炼后的意图
    original_message: str           # 人类原始消息
    user_id: str
    user_name: str
    context: dict = {}              # 对话上下文摘要
    priority: Literal["normal", "high", "urgent"] = "normal"
```

Coordinator 处理完成后回传结果给 chat_agent：

```python
class CoordinatorResponse(BaseModel):
    """Coordinator → chat_agent 的处理结果"""
    command_id: str
    status: Literal["completed", "in_progress", "failed"]
    summary: str                    # 给人类看的摘要
    details: dict = {}              # 详细信息
    follow_up: str | None = None    # 后续动作提示
```

## 8. 持久化状态

Coordinator 维护以下持久化状态（PostgreSQL）：

```python
class WorkflowState(BaseModel):
    """活跃工作流"""
    workflow_id: str
    type: str                       # e.g., "requirement_to_deploy"
    status: Literal["active", "paused", "completed", "failed"]
    current_phase: str              # e.g., "development", "qa_review"
    agents_involved: list[str]
    created_at: datetime
    updated_at: datetime
    context: dict                   # 工作流上下文

class AgentState(BaseModel):
    """Agent 运行状态"""
    agent_id: str
    status: Literal["idle", "working", "blocked", "error"]
    current_task: str | None = None
    last_output_at: datetime | None = None
    error: str | None = None

class DecisionRecord(BaseModel):
    """决策记录"""
    decision_id: str
    workflow_id: str | None = None
    reasoning: str                  # LLM 的决策理由
    action: str                     # 执行的动作
    target_agent: str
    created_at: datetime
    outcome: str | None = None      # 事后验证
```

## 9. Continue vs Spawn 判断

借鉴 Claude Code 的决策矩阵，Coordinator 判断对同一 Agent 是继续还是新建任务：

| 场景 | 决策 | 理由 |
|------|------|------|
| 上一步研究的文件正好要改 | Continue | 上下文重叠高 |
| 研究范围广，实现范围窄 | Spawn fresh | 上下文干扰 |
| 纠正上一步的失败 | Continue | 保留错误上下文有助修正 |
| 验证别人写的代码 | Spawn fresh | 避免确认偏误 |
| 完全无关的新任务 | Spawn fresh | 无上下文重叠 |

## 10. 典型工作流示例

### 需求→开发→QA 全链路

```
1. 人类："我们需要给飞书消息加一个 @mention 解析功能"
   └→ chat_agent 判断：跨 Agent 全链路 → 升级
   └→ 发布 Event(coordinator.command, payload=CoordinatorCommand(...))

2. Coordinator.handle_event() 收到 coordinator.command
   └→ _think(): "这是新功能需求，先交给 PM 定义"
   └→ 返回 Event(coordinator.dispatch, target=requirement-manager,
       instruction="用户需要飞书消息 @mention 解析功能。
        请产出 PRD，包含：功能范围、技术约束、验收标准。")

3. requirement_manager.handle_event() 收到 coordinator.dispatch
   └→ 执行需求分析，产出 PRD
   └→ 发布 Event(task.notification, status="completed", result={prd: ...})
   └→ 写入 scratchpad/agents/requirement-manager_output.md

4. Coordinator.handle_event() 收到 task.notification（PRD 完成）
   └→ Synthesis：读取 PRD，综合分析
   └→ 返回 Event(pm.prd_ready) → PM 和 PJM 直接协作拆任务
   └→ 注意：此时 NOT 发送 pm.tasks-ready-for-dev，等待 PJM 拆解完成

5. PJM 拆解完成
   └→ pjm_agent 发布 Event(pm.decompose-completed, payload={wp_id, tasks[]})

6. Coordinator.handle_event() 收到 pm.decompose-completed
   └→ Synthesis：读取拆解后的 tasks，结合 PRD 生成完整开发指令
   └→ 返回 Event(pm.tasks-ready-for-dev, payload={
       wp_id: ..., tasks: [...],  # 现有契约必填
       instruction: "实现飞书 @mention 解析。PRD 要点：[完整摘要]。
        涉及文件：shared/integrations/feishu/...
        验收标准：[列表]。完成后 commit 并报告。"
   })

7. dev_agent.handle_event() 收到 pm.tasks-ready-for-dev
   └→ payload 包含 wp_id + tasks[]（现有契约）+ instruction（Coordinator 扩展）
   └→ 执行开发
   └→ 发布 Event(task.notification, status="completed")

8. Coordinator.handle_event() 收到 task.notification（开发完成）
   └→ Synthesis: "开发完成，需要 QA 验证"
   └→ 返回 Event(qa.run-requested, payload={
       agent_name: "dev-agent",     # 现有契约必填
       commit_sha: "abc1234",       # 现有契约必填
       mr_iid: 42,                  # 现有契约
       files_changed: [...],        # 现有契约
       requested_by: "coordinator",
       instruction: "验收飞书 @mention 解析功能。
        验收标准：[从 PRD 提取]。测试范围：[具体用例]。"
   })

9. qa_agent.handle_event() 收到 qa.run-requested
   └→ payload 兼容 QARunRequestedPayload（agent_name, commit_sha 等齐全）
   └→ 执行验收
   └→ 发布 Event(task.notification, status="completed" | "failed")

10. Coordinator.handle_event() 收到 task.notification
    └→ 如果通过：返回 Event(coordinator.response) → chat_agent 通知人类
    └→ 如果失败：Synthesis 分析原因 → 返回 Event 打回 dev_agent 或调整需求
```

## 11. Agent Progress Tracking（借鉴 Claude Code `AgentProgress`）

### 实时进度上报

Agent 执行过程中定期发送进度事件，Coordinator 不只等最终结果，还能实时掌握各 Agent 状态。

```python
class AgentProgress(BaseModel):
    """Agent → Coordinator 的实时进度上报"""
    task_id: str
    agent_id: str
    tool_use_count: int             # 已调用工具次数
    llm_token_count: int            # 已消耗 token
    last_activity: ToolActivity | None = None  # 当前正在做什么
    recent_activities: list[ToolActivity] = []  # 最近 5 次操作

class ToolActivity(BaseModel):
    tool_name: str                  # e.g., "llm_call", "feishu_api", "git_commit"
    description: str | None = None  # e.g., "调用 Claude 分析 PRD"
    is_read: bool = False           # 只读操作
    is_write: bool = False          # 写操作
```

### 上报机制

通过 EventBus 发布 `task.progress` 事件，触发条件（不阻塞 Agent 主流程）：
- 每 N 次工具调用（默认 5 次）
- 每 M 秒（默认 30 秒）
- 以上取先到者

### Coordinator 使用进度的方式

- **超时检测**：Agent 超过预期时间未汇报进度 → 标记为 blocked
- **资源感知**：LLM token 消耗过高 → Coordinator 可以决定终止或降级
- **状态展示**：Coordinator 更新 Scratchpad 中的 `agents/{id}_output.md` 实时状态
- **Synthesis 输入**：进度信息作为 _think() 的上下文之一，辅助决策

### 在 BaseAgent 统一实现

```python
class BaseAgent:
    async def _report_progress(self, task_id: str, activity: ToolActivity):
        """统一进度上报，子类无需关心"""
        self._progress_tracker.record(activity)
        if self._progress_tracker.should_report():
            await self._event_bus.publish(Event.create(
                event_type=EventTypes.TASK_PROGRESS,
                source_agent=self.agent_id,
                payload=self._progress_tracker.snapshot(task_id).model_dump(),
            ))
```

## 12. Agent Memory 三级作用域（借鉴 Claude Code `agentMemory`）

### 三级记忆系统

每个 Agent 拥有跨会话的持久记忆，分三个作用域：

| 作用域 | 路径 | 共享范围 | 用途 |
|--------|------|----------|------|
| `global` | `data/agent-memory/global/` | 所有 Agent 共享 | 全局知识（项目约定、架构决策） |
| `agent` | `data/agent-memory/{agent_id}/` | 单个 Agent | Agent 专属经验（常见错误模式、优化策略） |
| `workflow` | `data/agent-memory/workflows/{workflow_id}/` | 工作流参与者 | 工作流上下文（PRD、设计决策、变更历史） |

### 记忆入口

每个作用域有一个 `MEMORY.md` 索引文件 + 多个详情文件：

```
data/agent-memory/
  global/
    MEMORY.md                       # 全局知识索引
    architecture_decisions.md       # 架构决策记录
    known_issues.md                 # 已知问题
  dev-agent/
    MEMORY.md                       # dev_agent 专属索引
    coding_patterns.md              # 编码模式偏好
    common_errors.md                # 常见错误及修复
  workflows/
    wf_001/
      MEMORY.md                     # 工作流记忆
      prd.md                        # PRD 内容
      design_decisions.md           # 设计决策
```

### 记忆读写规则

```python
class AgentMemory:
    """Agent 记忆管理器，注入到 BaseAgent"""

    def __init__(self, agent_id: str):
        self._agent_id = agent_id

    async def load_context(self, workflow_id: str | None = None) -> str:
        """加载记忆作为 LLM 上下文前缀"""
        parts = []
        # 1. 全局记忆（始终加载）
        parts.append(await self._read_scope("global"))
        # 2. Agent 专属记忆
        parts.append(await self._read_scope(self._agent_id))
        # 3. 工作流记忆（如果在工作流中）
        if workflow_id:
            parts.append(await self._read_scope(f"workflows/{workflow_id}"))
        return "\n---\n".join(p for p in parts if p)

    async def save(self, scope: str, key: str, content: str, *, workflow_id: str | None = None):
        """写入记忆（权限隔离：Agent 只能写自己的 scope 或当前工作流）

        Args:
            scope: "global" | agent_id | "workflows/{workflow_id}"
            key: 文件名（不含路径）
            content: 内容
            workflow_id: 当前工作流 ID（用于权限校验）
        """
        allowed_scopes = {self._agent_id}
        if workflow_id:
            allowed_scopes.add(f"workflows/{workflow_id}")
        if scope not in allowed_scopes:
            raise PermissionError(f"Agent {self._agent_id} cannot write to scope {scope}")
        await self._write_file(scope, key, content)
```

### Coordinator 的特殊权限

Coordinator 拥有全作用域读写权限（CEO 角色）：
- 读：全部三级
- 写：全部三级（包括 global 和其他 Agent 的 scope）
- 创建工作流记忆：新工作流启动时创建 `workflows/{id}/`

## 13. Forked Agent 隔离（借鉴 Claude Code `forkedAgent`）

### 问题

Scratchpad L3 Full Compact 需要调用 LLM 生成摘要。如果在 Coordinator 的 `handle_event()` 内同步执行，会阻塞事件处理。

### 方案：隔离 Fork

```python
class Scratchpad:
    async def compact(self):
        """L3 压缩：在隔离上下文中执行，不阻塞主循环"""
        result = await self._run_forked(
            task_type="scratchpad_compact",
            prompt=self._build_compact_prompt(),
            # 隔离策略
            can_write=[f"data/scratchpad/global_status.md"],  # 只能写摘要文件
            can_read=["data/scratchpad/**"],                  # 可以读全部
            share_prompt_cache=True,                          # 共享 LLM prompt cache 省 token
        )
        await self._apply_compact_result(result)
```

### Fork 隔离原则（来自 Claude Code `createSubagentContext`）

| 维度 | 隔离策略 |
|------|---------|
| LLM prompt cache | **共享**（相同 system prompt → cache hit，省 token） |
| 文件状态 | **clone**（fork 修改不影响主上下文） |
| 写权限 | **白名单**（只能写指定文件，防止越界） |
| 事件发布 | **禁止**（fork 不能发 Event，防止副作用） |
| 状态回写 | **显式 merge**（fork 完成后主上下文选择性采纳结果） |

### 适用场景

| 场景 | Fork 配置 |
|------|----------|
| Scratchpad L3 压缩 | can_write=[global_status.md], share_cache=True |
| Agent Memory 提取 | can_write=[agent memory 文件], share_cache=True |
| 决策方案评估 | can_write=[], can_read=[scratchpad/**], share_cache=True（只读分析） |

### 实现位置

```python
# shared/infra/forked_agent.py
async def run_forked(
    llm_gateway: LLMGateway,
    prompt: str,
    system_prompt: str,
    can_read: list[str],
    can_write: list[str],
    share_prompt_cache: bool = True,
    task_type: str = "forked",
) -> ForkedResult:
    """在隔离上下文中执行 LLM 任务"""
    ...
```

## 14. Permission 隔离（借鉴 Claude Code `ToolPermissionContext`）

### Agent 能力分级

Coordinator dispatch 指令时，可以限制目标 Agent 的能力范围：

```python
class DispatchPermissions(BaseModel):
    """Coordinator 分配给 Agent 的能力权限"""
    allowed_tools: list[str] | None = None     # None = 全部允许
    denied_tools: list[str] = []               # 明确禁止的工具
    allowed_events: list[str] | None = None    # 允许发布的事件类型
    max_llm_tokens: int | None = None          # token 上限
    max_duration_ms: int | None = None         # 时间上限
    human_approval_required: bool = False       # 需要人类审批
```

### 场景示例

| 场景 | 权限配置 |
|------|---------|
| dev_agent 写代码 | `allowed_tools=["git_*", "file_*", "llm_call"]`, `max_llm_tokens=50000` |
| qa_agent 只读验收 | `allowed_tools=["test_*", "file_read", "llm_call"]`, `denied_tools=["file_write", "git_push"]` |
| analysis_agent 风险分析 | `allowed_tools=["db_query", "llm_call"]`, `max_duration_ms=60000` |
| 高危操作（删除/部署） | `human_approval_required=True` |

### 与 CLAUDE.md Human-in-the-Loop 对齐

CLAUDE.md 已定义四类需要人类审批的操作：Finance / Legal / Customer / Technical。
Permission 隔离在此基础上增加 **Coordinator 级别的动态权限** — 同一个 Agent 在不同工作流中可以拿到不同权限。

### 实现方式

权限随 `coordinator.dispatch` 事件的 payload 下发：

```python
def _decision_to_event(self, decision: Decision) -> Event:
    payload = {
        "target_agent": decision.target_agent,
        "task_id": decision.task_id,
        "instruction": decision.instruction,
        # 权限限制
        "permissions": decision.permissions.model_dump() if decision.permissions else None,
    }
    ...
```

Agent 在 `handle_event()` 中读取 permissions，作为**局部变量**传递给任务执行上下文，
**不修改 self 状态**（Agent 实例是长驻的，mutate self 会泄漏到后续事件）：

```python
async def handle_event(self, event: Event) -> list[Event]:
    # 从 payload 读取权限（可选字段）
    raw_perms = event.payload.get("permissions")
    # 作为局部变量，仅作用于本次任务执行
    task_permissions = DispatchPermissions(**raw_perms) if raw_perms else None

    # 传递给任务执行上下文，而非 self._apply_permissions()
    return await self._execute_task(event, permissions=task_permissions)

async def _execute_task(self, event: Event, permissions: DispatchPermissions | None):
    """权限作为参数传入，不修改 Agent 实例状态"""
    if permissions and permissions.max_llm_tokens:
        # 限制本次 LLM 调用的 token 上限
        ...
    if permissions and permissions.human_approval_required:
        # 本次任务需要人类审批
        ...
    ...
```

## 15. 统一 Tool Registry（借鉴 Claude Code `Tool<Input,Output>` + `buildTool()`）

### 问题

当前各 Agent 的外部能力（飞书 API、企微 API、LLM 调用、Git 操作、向量搜索）分散在各自的 `core/tools.py` 中，
没有统一接口。Coordinator 无法动态感知和分配 Agent 能力。

### Tool 统一接口

```python
# shared/infra/tool_registry.py

class ToolMeta(BaseModel):
    """工具元数据"""
    name: str
    description: str
    is_read_only: bool = False          # 默认 fail-closed（非只读）
    is_concurrency_safe: bool = False   # 默认 fail-closed（不并发安全）
    is_destructive: bool = False        # 删除/发送/部署等不可逆操作
    should_defer: bool = False          # 延迟加载（减少冷启动）
    requires_approval: bool = False     # 需要人类审批

class Tool(ABC):
    """所有外部能力的统一接口"""
    meta: ToolMeta

    @abstractmethod
    async def execute(self, input: dict, context: ToolContext) -> ToolResult:
        """执行工具"""
        ...

    async def check_permissions(self, input: dict, context: ToolContext) -> PermissionResult:
        """权限检查，默认允许"""
        return PermissionResult(allowed=True)
```

### buildTool() — Fail-Closed 默认值工厂

```python
def build_tool(
    name: str,
    description: str,
    handler: Callable,
    *,
    is_read_only: bool = False,         # 默认：有副作用
    is_concurrency_safe: bool = False,  # 默认：不并发安全
    is_destructive: bool = False,
    should_defer: bool = False,
    requires_approval: bool = False,
) -> Tool:
    """工厂函数，注入 fail-closed 默认值"""
    ...
```

### Tool Registry

```python
class ToolRegistry:
    """全局工具注册表，Coordinator 可查询"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.meta.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_for_agent(self, agent_id: str, permissions: DispatchPermissions | None = None) -> list[Tool]:
        """根据权限过滤，返回 Agent 可用的工具列表"""
        tools = list(self._tools.values())
        if permissions:
            if permissions.allowed_tools is not None:
                tools = [t for t in tools if t.meta.name in permissions.allowed_tools]
            tools = [t for t in tools if t.meta.name not in permissions.denied_tools]
        return tools

    def get_read_only(self) -> list[Tool]:
        """返回所有只读工具（用于 QA 验收等场景）"""
        return [t for t in self._tools.values() if t.meta.is_read_only]

    def get_deferred(self) -> list[str]:
        """返回需要延迟加载的工具名（减少冷启动）"""
        return [t.meta.name for t in self._tools.values() if t.meta.should_defer]
```

### 迁移计划

现有 `chat_agent/core/tools.py` 中的 15 个工具逐步迁移到统一 Registry：
- **第一步**：在 `shared/infra/tool_registry.py` 定义接口和 Registry
- **第二步**：将通用工具（飞书 API、OP API、LLM 调用）迁移到 `shared/infra/tools/`
- **第三步**：各 Agent 通过 `runtime.tool_registry` 获取工具，不直接 import adapter
- **第四步**：Coordinator 通过 Registry 感知全局能力，按 permissions 分配

## 16. 与现有架构的兼容

### 不变的

- `BaseAgent` + `handle_event()` 接口
- `create_agent_app()` FastAPI 入口
- EventBus（Redis）通信
- 所有现有 Agent 的内部逻辑

### 需要新增的

| 组件 | 说明 |
|------|------|
| `agents/coordinator/` | 新 Agent 目录，遵循标准结构 |
| `shared/schemas/coordinator.py` | TaskNotification, CoordinatorCommand, CoordinatorResponse, AgentProgress, DispatchPermissions |
| `shared/infra/scratchpad.py` | Scratchpad 读写 + 三层压缩 |
| `shared/infra/agent_memory.py` | 三级作用域记忆管理器 |
| `shared/infra/forked_agent.py` | 隔离 Fork 执行引擎 |
| `shared/infra/tool_registry.py` | Tool 统一接口 + Registry + buildTool() |
| `shared/infra/tools/` | 通用工具实现（飞书/OP/LLM/Git） |
| EventBus 事件类型 | `coordinator.command`, `coordinator.response`, `coordinator.dispatch`, `task.notification`, `task.progress` |

### 现有 Agent 需要改动的

| Agent | 改动 | 量级 |
|-------|------|------|
| chat_agent | 增加升级判断逻辑 + 发送 `coordinator.command` + 订阅 `coordinator.response` | 小 |
| BaseAgent | TaskNotification 发送 + Scratchpad 写入 + Progress 上报 + AgentMemory 注入（统一在基类加） | 中 |
| requirement_manager | 新增订阅 `coordinator.dispatch`，`handle_event()` 增加分支处理 Coordinator 指令 | 小 |
| dev_agent | `handle_event()` 中 `pm.tasks-ready-for-dev` 分支兼容 Coordinator payload（已有 instruction 字段则用，否则走原逻辑） | 小 |
| qa_agent | `handle_event()` 中 `qa.run-requested` 分支兼容 Coordinator payload（同上） | 小 |
| pjm_agent / sync_agent / analysis_agent | 新增订阅 `coordinator.dispatch`，处理增量指令 | 小 |

## 17. 技术栈

- **运行时**：FastAPI + `create_agent_app()`，遵循现有模式
- **LLM**：Claude API（通过 `shared/infra/llm_gateway`）
- **状态存储**：PostgreSQL（工作流/Agent 状态/决策记录）
- **Scratchpad**：文件系统（`data/scratchpad/`），与 Coordinator 同机部署
- **通信**：EventBus（Redis）
- **压缩**：LLM 调用（通过 llm_gateway，独立 task_type）

## 18. 非目标（YAGNI）

- Coordinator 不直接面对人类
- 不替代任何现有 Agent 的内部逻辑
- 不做实时流式响应（Coordinator 是后台角色）
- 第一版不做 evolution_agent 对 Coordinator 自身的优化
- 第一版 Scratchpad 用文件系统，不做分布式存储
- 第一版 Tool Registry 只迁移 Coordinator 需要感知的工具，chat_agent 的 15 个工具保持原样
- Agent Memory 的 global scope 第一版只有 Coordinator 写入，其他 Agent 只读
- Forked Agent 第一版只用于 Scratchpad 压缩，不用于通用 Agent 派生
