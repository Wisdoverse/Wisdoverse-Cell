# QA Agent — Wisdoverse Cell 第 7 个 Agent

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **Status**: Draft | **Author**: Human + Claude | **Date**: 2026-03-20

## Problem Statement

Wisdoverse Cell 的验收框架（`.acceptance/`）目前是 GitLab CI 中的被动脚本——只有人类提交 MR 时才触发。当 AI 工具团队（Claude Code / Codex / Gemini）开始并行开发 20 个新 agent 时，需要一个主动的、可被编排的验收 agent，在 EventBus 事件驱动下自动执行验收、报告结果、通知相关方，形成"开发→验收→反馈"的闭环。

没有 QA Agent，验收只能在 MR 阶段才介入，发现问题时代码已经写完，修复成本高。QA Agent 让验收前移到代码提交时刻。

## Goals

1. **事件驱动自动验收** — 收到 `code.committed` 事件后自动运行 L0/L1/L2 检查，无需人工触发
2. **三通道通知** — 验收结果同时发送到 EventBus（PJM Agent 消费）、飞书（人类通知）、GitLab MR（代码关联）
3. **复用已有框架** — 核心检查逻辑 100% 复用 `.acceptance/runner.py`，QA Agent 只做编排和通知
4. **标准 agent 架构** — 继承 BaseAgent、使用 create_agent_app、通过验收框架自身的 new-agent-checklist
5. **验收报告持久化** — 每次验收结果写入数据库，支持趋势分析

## Non-Goals

- **不替代 GitLab CI** — CI pipeline 中的 acceptance stage 保留，QA Agent 是补充而非替代
- **不自动修复代码** — V1 只报告和通知，不调用 AI 工具修复（P2 考虑）
- **不做运行时监控** — Prometheus/Grafana 负责运行时，QA Agent 只管代码质量准入
- **不做测试生成** — 不写测试代码，只评估已有测试的质量
- **不做跨 agent 集成测试** — V1 只验收单个 agent 的代码质量

## User Stories

### 作为 PJM Agent

- 作为 PJM Agent，我想在任务完成后触发 QA 验收，以便自动检查 AI 工具的产出质量
- 作为 PJM Agent，我想收到结构化的验收结果事件，以便更新任务状态（通过/需修复）

### 作为项目负责人

- 作为负责人，我想在飞书收到验收失败的通知（含具体失败项和文件位置），以便快速判断是否需要介入
- 作为负责人，我想看到历史验收数据的趋势（通过率、常见问题），以便调整 AI 工具的使用策略
- 作为负责人，我想在 GitLab MR 上直接看到验收报告，以便在 review 时参考

### 作为 AI 工具（Claude Code / Codex / Gemini）

- 作为 AI 工具，我想收到 JSON 格式的验收反馈，以便自动解析并修复问题后重新提交

## Requirements

### Must-Have (P0)

#### P0-1: Agent 基础架构

遵循 Wisdoverse Cell 标准 agent 架构：

- [ ] 继承 `BaseAgent`，实现 `handle_event()`, `startup()`, `shutdown()`
- [ ] 使用 `create_agent_app()` 创建 FastAPI 入口
- [ ] 独立 Dockerfile + Docker Compose service
- [ ] 数据库隔离（独立 PostgreSQL DB + Redis namespace）
- [ ] `/health`, `/health/ready`, `/metrics` endpoints
- [ ] 通过 `.acceptance/` 自身的 new-agent-checklist 验收

```
agents/qa_agent/
├── app/
│   ├── __init__.py
│   ├── main.py              # create_agent_app + scheduler
│   └── metrics.py           # Prometheus counters
├── service/
│   ├── __init__.py
│   └── agent.py             # QAAgent(BaseAgent)
├── core/
│   ├── __init__.py
│   ├── acceptance_runner.py  # 调用 .acceptance/runner.py
│   ├── notifier.py           # 飞书 + GitLab MR 通知
│   └── report_store.py       # 验收报告持久化
├── db/
│   ├── __init__.py
│   ├── database.py
│   └── repository.py
├── models/
│   ├── __init__.py
│   ├── qa.py                 # AcceptanceRun, AcceptanceResult tables
│   └── schemas.py            # Pydantic models
├── api/
│   ├── __init__.py
│   └── qa.py                 # REST endpoints
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── Dockerfile
└── requirements.txt
```

#### P0-2: 事件驱动验收

**订阅事件：**

| 事件 | 触发动作 |
|------|----------|
| `code.committed` | 对提交涉及的 agent 目录运行 L0/L1/L2 |
| `qa.run_requested` | PJM Agent 或人工请求的手动验收 |

**发布事件：**

| 事件 | 时机 |
|------|------|
| `qa.acceptance_completed` | 验收完成（含完整结果） |
| `qa.gate_failed` | L0 硬阻断失败（高优先级通知） |

**事件处理流程：**

```
code.committed 事件
    ↓
解析 payload: {agent_name, commit_sha, mr_iid?, files_changed}
    ↓
调用 .acceptance/runner.py (subprocess)
    --target agents/{agent_name}
    --level all
    --format json
    ↓
解析 JSON 报告
    ↓
并行执行:
├── 发布 qa.acceptance_completed 事件（含完整报告）
├── 持久化到 PostgreSQL
├── 如果有 mr_iid → GitLab MR comment
└── 如果 L0 FAIL 或 L1 有 high severity → 飞书通知
```

**验收标准：**
- Given `code.committed` 事件包含 `agent_name: "pjm_agent"`
- When QA Agent 收到事件
- Then 在 30 秒内完成验收并发布 `qa.acceptance_completed` 事件

#### P0-3: 三通道通知

**EventBus 通知（始终执行）：**

```python
Event.create(
    event_type=EventTypes.QA_ACCEPTANCE_COMPLETED,
    source_agent="qa-agent",
    payload={
        "agent_name": "pjm_agent",
        "commit_sha": "abc123",
        "mr_iid": 42,
        "summary": {"l0_gate": "PASS", "l1_check": "WARN", "l2_report": "INFO"},
        "l0_failures": 0,
        "l1_warnings": 3,
        "duration_seconds": 18.2,
        "report_id": "run_01JXYZ...",
    },
)
```

**飞书通知（L0 FAIL 或 L1 high severity 时）：**

- 使用 `shared/integrations/feishu/` 发送卡片消息
- 卡片包含：agent 名称、通过/失败状态、失败项列表（最多 5 个）、MR 链接
- 不通知 L2 REPORT（避免噪音）

**GitLab MR Comment（有 mr_iid 时）：**

- 使用 GitLab API 在 MR 上发布评论
- 内容复用 `.acceptance/runner.py` 的 Markdown 输出
- 如果已有 QA Agent 的评论，更新而非新建（避免刷屏）

#### P0-4: 验收报告持久化

**数据模型：**

```python
class AcceptanceRun(Base):
    __tablename__ = "qa_acceptance_runs"

    id: Mapped[str]                    # ulid
    agent_name: Mapped[str]            # e.g. "pjm_agent"
    commit_sha: Mapped[str | None]
    mr_iid: Mapped[int | None]
    trigger: Mapped[str]               # "event" | "manual" | "scheduled"
    l0_status: Mapped[str]             # "PASS" | "FAIL"
    l1_status: Mapped[str]             # "PASS" | "WARN"
    l0_failure_count: Mapped[int]
    l1_warning_count: Mapped[int]
    total_checks: Mapped[int]
    duration_seconds: Mapped[float]
    full_report: Mapped[dict]          # JSON, 完整 runner 输出
    created_at: Mapped[datetime]
```

#### P0-5: REST API

| Endpoint | 方法 | 描述 |
|----------|------|------|
| `/api/v1/qa/run` | POST | 手动触发验收 `{agent_name, level?}` |
| `/api/v1/qa/runs` | GET | 查询验收历史 `?agent_name=&limit=20` |
| `/api/v1/qa/runs/{id}` | GET | 查询单次验收详情 |
| `/api/v1/qa/stats` | GET | 验收统计 `?agent_name=&days=30` |

### Nice-to-Have (P1)

#### P1-1: 定时全量巡检

- 每天 UTC 02:00 对所有已注册 agent 运行 L0 检查
- 结果汇总为一份"每日质量报告"，通过飞书发送

#### P1-2: 验收趋势 API

- `/api/v1/qa/trends` 返回过去 N 天的通过率、常见失败类型、改进趋势
- 供未来 Dashboard 或 PJM Agent 报告使用

#### P1-3: 验收结果缓存

- 对同一 commit_sha + agent_name 的验收结果缓存 1 小时
- 避免重复验收浪费资源

### Future Considerations (P2)

#### P2-1: 自动修复闭环

- L0 失败时，生成修复指令并通过 AgentForge 调度 AI 工具修复
- 最多重试 2 次，之后升级到人类

#### P2-2: 跨 Agent 集成验收

- 验证新 agent 与现有 agent 的 EventBus 交互
- 端到端流程测试

#### P2-3: L3 自进化

- 根据历史验收数据自动调整阈值
- 学习哪些检查项的误报率高，自动降级或优化

## Success Metrics

### Leading Indicators（上线后 1-2 周）

| 指标 | 目标 | 测量 |
|------|------|------|
| 事件→验收完成延迟 | < 30s | `qa.acceptance_completed` 时间戳 - 触发事件时间戳 |
| 飞书通知送达率 | 100% L0 FAIL 通知到达 | 飞书消息记录 |
| GitLab MR 评论准确率 | > 95% 评论关联到正确 MR | 人工抽检 |
| 首个新 agent 通过验收 | 从开发到首次 L0 PASS < 3 天 | AcceptanceRun 表 |

### Lagging Indicators（上线后 1-3 月）

| 指标 | 目标 | 测量 |
|------|------|------|
| AI 产出的首次通过率提升 | 从 ~40% 提升到 > 60% | AcceptanceRun 趋势 |
| L0 违规进入 main 的次数 | 归零 | 季度审计 |
| 人工 review 时间 | 减少 50% | 负责人自评 |

## Open Questions

| # | 问题 | 负责人 | 阻断性 |
|---|------|--------|--------|
| 1 | `code.committed` 事件的 payload 需要包含哪些字段？目前 EventTypes 里有这个常量但未被使用 | Engineering | 阻断 |
| 2 | GitLab API token 从哪里注入？用现有的 CI token 还是独立的 bot token？ | Engineering | 非阻断（先用环境变量） |
| 3 | QA Agent 应该部署在哪个 Docker Compose profile？ | Engineering | 非阻断 |

## Timeline

**Phase 1（3 天）**：核心功能
- agent 骨架 + EventBus 集成 + 调用 .acceptance/runner.py
- 发布 qa.acceptance_completed 事件
- 数据库持久化

**Phase 2（2 天）**：通知通道
- 飞书卡片通知
- GitLab MR comment
- REST API

**Phase 3（持续）**：用自己验收自己
- QA Agent 的代码必须通过 `.acceptance/` 的 new-agent-checklist
- 这是对验收框架的终极验证

## Architecture

```
                    ┌──────────────┐
  code.committed ──→│   QA Agent   │──→ qa.acceptance_completed
  qa.run_requested→│              │──→ qa.gate_failed
                    │  ┌────────┐  │
                    │  │runner  │  │    ← subprocess 调用 .acceptance/runner.py
                    │  │.py     │  │
                    │  └────────┘  │
                    │              │──→ GitLab MR comment (API)
                    │              │──→ 飞书卡片通知
                    │              │──→ PostgreSQL (持久化)
                    └──────────────┘
```
