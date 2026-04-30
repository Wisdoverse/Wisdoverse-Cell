# Wisdoverse Cell 产品需求文档 (PRD)

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> **版本**: v1.0
> **创建日期**: 2026-01-23
> **状态**: 开发中
> **产品负责人**: Wisdoverse Cell Team
> **文档类型**: 产品全景 PRD
> **适用于**: 顶尖 AI 研发团队

---

## 目录

1. [产品愿景](#1-产品愿景)
2. [产品定位](#2-产品定位)
3. [用户画像](#3-用户画像)
4. [功能全景](#4-功能全景)
5. [Agent 架构](#5-agent-架构)
6. [技术规格](#6-技术规格)
7. [数据架构](#7-数据架构)
8. [API 规格](#8-api-规格)
9. [质量要求](#9-质量要求)
10. [运营要求](#10-运营要求)
11. [路线图](#11-路线图)
12. [风险管理](#12-风险管理)
13. [附录](#13-附录)

---

## 1. 产品愿景

### 1.1 愿景声明

> **用 2 个人 + 26 个 AI Agent，创造 10 人团队的生产力。**

Wisdoverse Cell 是一个实验性的 **AI Native 操作系统**，探索人类与 AI Agent 协作的新范式。我们相信未来的公司不是"用 AI 辅助人"，而是"AI 执行 + 人类决策"的全新形态。

### 1.2 演进路径

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Co-pilot  │ →  │    Agent    │ →  │Orchestrator │ →  │ DAO of      │
│   (辅助)    │    │   (自主)    │    │   (编排)    │    │ Agents      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
    2024-2025         2025-2026          2026-2027          2027+
                     ◄── 当前阶段 ──►
```

| 阶段 | 特征 | 人类角色 | AI 角色 |
|------|------|----------|---------|
| Co-pilot | AI 建议，人类执行 | 执行者 | 助手 |
| **Agent** | AI 执行，人类审批 | **审批者** | **执行者** |
| Orchestrator | AI 编排多 Agent | 监督者 | 编排者 |
| DAO | 链上治理，完全自主 | 股东 | 运营者 |

### 1.3 核心价值

| 价值 | 描述 | 量化目标 |
|------|------|----------|
| **效率** | 重复性工作自动化 | 人工投入减少 80% |
| **质量** | 标准化流程，减少人为错误 | 错误率降低 90% |
| **响应** | 7×24 无人值守 | 响应时间 < 5分钟 |
| **成本** | 用 AI 替代低杠杆工作 | 人力成本降低 70% |

---

## 2. 产品定位

### 2.1 市场定位

```
                    高自动化程度
                         ▲
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         │   传统 RPA    │  Wisdoverse Cell │
         │   (规则驱动)   │   (AI Native) │
         │               │      ★        │
低智能 ──┼───────────────┼───────────────┼── 高智能
         │               │               │
         │   手工流程    │   AI Copilot  │
         │               │   (辅助模式)   │
         │               │               │
         └───────────────┼───────────────┘
                         │
                    低自动化程度
```

### 2.2 差异化优势

| 维度 | 传统方案 | Wisdoverse Cell |
|------|----------|--------------|
| 决策能力 | 规则匹配 | LLM 推理 |
| 适应性 | 需重新编程 | 自然语言指令 |
| 集成方式 | API 对接 | Event 驱动 |
| 人机协作 | 串行审批 | 并行 + 检查点 |
| 可观测性 | 日志为主 | Event Sourcing |

### 2.3 目标客户

**Phase 1 (内部验证)**:
- 本公司各部门（市场、销售、研发、交付、支持、运营）

**Phase 2 (商业化)**:
- 中小企业 (50-500人)
- 需要快速响应、成本敏感
- 已有数字化基础设施

---

## 3. 用户画像

### 3.1 核心用户

#### P1: CEO/创始人 (决策者)
- **痛点**: 团队扩张慢，人力成本高，管理复杂度上升
- **诉求**: 用最少的人实现最大的产出
- **使用场景**: 查看业务仪表盘，审批关键决策

#### P2: 部门负责人 (管理者)
- **痛点**: 重复性工作占用大量时间，难以聚焦高价值事项
- **诉求**: Agent 处理日常事务，自己专注战略
- **使用场景**: 配置 Agent 规则，审批重要输出

#### P3: 一线员工 (协作者)
- **痛点**: 繁琐的录入、整理、报告工作
- **诉求**: 简单交互，快速获得结果
- **使用场景**: 通过飞书与 Agent 对话，确认输出

### 3.2 Human-in-the-Loop 检查点

| 类别 | 需人工审批 | 示例 |
|------|------------|------|
| 💰 财务 | 定价、付款、采购 | Agent 生成报价，人工确认 |
| 📜 法务 | 合同签署 | Agent 起草，人工审核签字 |
| 🤝 客户 | 高意向跟进、投诉处理 | Agent 初筛，人工接手重要客户 |
| 🔧 技术 | 架构变更、需求确认、上线 | Agent 提取需求，人工确认后执行 |

---

## 4. 功能全景

### 4.1 功能矩阵

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            Wisdoverse Cell 功能全景                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                         核心基础设施层                                │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │ │
│  │  │ Event Bus  │  │LLM Gateway │  │ Vector DB  │  │ PostgreSQL │     │ │
│  │  │  (Redis)   │  │  (Claude)  │  │  (Milvus)  │  │   (asyncpg)│     │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                    ▲                                       │
│  ┌──────────────────────────────────┴───────────────────────────────────┐ │
│  │                          共享服务层                                   │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │ │
│  │  │ BaseAgent  │  │Notification│  │  Feishu    │  │  Circuit   │     │ │
│  │  │ Framework  │  │  Service   │  │  Gateway   │  │  Breaker   │     │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                    ▲                                       │
│  ┌──────────────────────────────────┴───────────────────────────────────┐ │
│  │                          Agent 层 (26个)                              │ │
│  │                                                                       │ │
│  │  市场(3)   销售(4)   研发(5)   交付(4)   支持(4)   运营(6)           │ │
│  │  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐              │ │
│  │  │Lead │  │Comm │  │Req★ │  │Deploy│  │Monitor│ │Feedback│          │ │
│  │  │Score│  │Demo │  │HW   │  │SaaS │  │Trouble│ │Compete│           │ │
│  │  │Content││Prop │  │SW   │  │Train│  │Success│ │Product│           │ │
│  │  └─────┘  │Contract│Test │  │Accept│ │Ticket│  │Finance│           │ │
│  │           └─────┘  │Doc  │  └─────┘  └─────┘  │Analytic│           │ │
│  │                    └─────┘                    │Knowledge│          │ │
│  │                                               └─────┘              │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                    ▲                                       │
│  ┌──────────────────────────────────┴───────────────────────────────────┐ │
│  │                          接入层                                       │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │ │
│  │  │  飞书 Bot  │  │  Web API   │  │  Webhook   │  │   CLI      │     │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                              ★ = 当前实现
```

### 4.2 功能完成状态

| 模块 | 功能 | 状态 | 完成度 |
|------|------|:----:|:------:|
| **基础设施** | Event Bus (Redis) | ✅ | 100% |
| | LLM Gateway (Claude) | ✅ | 100% |
| | Vector Store (Milvus) | ✅ | 100% |
| | Database (PostgreSQL) | ✅ | 100% |
| **共享服务** | BaseAgent Framework | ✅ | 100% |
| | Notification Service | ✅ | 100% |
| | Feishu Gateway | ✅ | 100% |
| | Circuit Breaker | ✅ | 100% |
| **Agent** | Requirement Manager | ✅ | 90% |
| | 其他 25 个 Agent | ⏳ | 0% |
| **接入** | Web API | ✅ | 100% |
| | 飞书 Bot | ✅ | 100% |
| | Webhook | ✅ | 100% |

**总体进度**:
```
基础设施    ████████████████████ 100%
共享服务    ████████████████████ 100%
Agent 层    ██░░░░░░░░░░░░░░░░░░  10% (1/26)
接入层      ████████████████████ 100%
────────────────────────────────────────
整体进度    ███████░░░░░░░░░░░░░  35%
```

---

## 5. Agent 架构

### 5.1 Agent 抽象模型

```python
class BaseAgent(ABC):
    """
    所有 Agent 的基类

    生命周期:
    1. startup() - 初始化资源
    2. handle_event() / handle_request() - 处理业务
    3. shutdown() - 清理资源
    """

    @abstractmethod
    async def handle_event(self, event: Event) -> list[Event]:
        """处理入站事件，返回出站事件"""
        pass

    @abstractmethod
    async def handle_request(self, request: dict) -> dict:
        """处理 API 请求"""
        pass

    async def startup(self):
        """初始化 DB、Cache、LLM 连接"""
        pass

    async def shutdown(self):
        """释放资源"""
        pass

    def create_event(self, event_type: str, payload: dict) -> Event:
        """创建出站事件的便捷方法"""
        pass
```

### 5.2 Agent 通信模型

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Event Bus (Redis)                              │
│                                                                          │
│  Queue: projectcell:events:requirement.extracted                        │
│  Queue: projectcell:events:requirement.confirmed                        │
│  Queue: projectcell:events:code.committed                               │
│  Queue: projectcell:events:test.passed                                  │
│  ...                                                                     │
└─────────────────────────────────────────────────────────────────────────┘
       ▲                    ▲                    ▲                    ▲
       │ publish            │ subscribe          │ publish            │
       │                    │                    │                    │
┌──────┴──────┐      ┌──────┴──────┐      ┌──────┴──────┐      ┌──────┴──────┐
│ Requirement │      │   Software  │      │    Test     │      │  Deployment │
│   Manager   │─────▶│     Dev     │─────▶│    Agent    │─────▶│    Agent    │
│    Agent    │      │    Agent    │      │             │      │             │
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
```

### 5.3 Event 规范

```python
Event(
    event_id="evt_01HXYZ...",           # ULID 格式
    event_type="requirement.extracted", # {domain}.{action}
    timestamp=datetime.now(UTC),        # 时区感知
    source_agent="requirement-manager", # kebab-case
    payload=RequirementExtractedPayload(...),
    metadata=EventMetadata(
        trace_id="trace_xxx",           # 事件链追踪
        retry_count=0,
        correlation_id="corr_xxx"       # 请求-响应关联
    )
)
```

**预定义事件类型**:

| 领域 | 事件 | 描述 |
|------|------|------|
| requirement | extracted | 需求已提取 |
| | confirmed | 需求已确认 |
| | rejected | 需求已拒绝 |
| | changed | 需求已变更 |
| | deleted | 需求已删除 |
| code | committed | 代码已提交 |
| | reviewed | 代码已评审 |
| feature | completed | 功能已完成 |
| test | passed | 测试通过 |
| | failed | 测试失败 |
| deployment | started | 部署开始 |
| | completed | 部署完成 |
| approval | requested | 请求审批 |
| | granted | 审批通过 |
| | rejected | 审批拒绝 |

### 5.4 26 Agent 规划

#### 市场部 (3 Agents)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Lead Miner | 挖掘潜在客户 | 行业数据、网站 | 线索列表 |
| Lead Scorer | 评估线索质量 | 线索信息 | 评分、优先级 |
| Content Creator | 生成营销内容 | 产品信息、热点 | 文章、海报 |

#### 销售部 (4 Agents)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Communicator | 客户沟通 | 客户消息 | 回复、跟进 |
| Demo Preparer | 准备演示 | 客户需求 | Demo 脚本 |
| Proposal Generator | 生成方案 | 需求、产品 | 商务方案 |
| Contract Assistant | 合同辅助 | 商务条款 | 合同草案 |

#### 研发部 (5 Agents)

| Agent | 职责 | 输入 | 输出 | 状态 |
|-------|------|------|------|:----:|
| **Requirement Manager** | 需求管理 | 会议记录 | 结构化需求 | ✅ |
| Hardware Developer | 硬件开发 | 硬件需求 | 设计文档 | ⏳ |
| Software Developer | 软件开发 | 软件需求 | 代码 | ⏳ |
| Test Engineer | 测试 | 代码、用例 | 测试报告 | ⏳ |
| Tech Writer | 文档 | 产品、代码 | 用户手册 | ⏳ |

#### 交付部 (4 Agents)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Hardware Deployer | 硬件部署 | 订单、设备 | 部署报告 |
| SaaS Configurator | SaaS 配置 | 客户需求 | 配置完成 |
| Trainer | 培训 | 产品、客户 | 培训材料 |
| Acceptance Manager | 验收 | 交付物 | 验收报告 |

#### 支持部 (4 Agents)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Device Monitor | 设备监控 | 设备数据 | 告警、报告 |
| Troubleshooter | 故障排查 | 故障描述 | 解决方案 |
| Customer Success | 客户成功 | 使用数据 | 优化建议 |
| Ticket Handler | 工单处理 | 工单 | 响应、闭单 |

#### 运营部 (6 Agents)

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Feedback Collector | 反馈收集 | 多渠道反馈 | 整理后的反馈 |
| Competitor Watcher | 竞品监控 | 公开信息 | 竞品分析 |
| Product Analyst | 产品分析 | 使用数据 | 产品洞察 |
| Finance Assistant | 财务辅助 | 财务数据 | 报表、预警 |
| Analytics Engine | 数据分析 | 业务数据 | 仪表盘 |
| Knowledge Manager | 知识管理 | 文档、对话 | 知识库 |

---

## 6. 技术规格

### 6.1 技术栈

| 层级 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **语言** | Python | 3.13+ | 主开发语言 |
| **框架** | FastAPI | 0.115+ | Web 框架 |
| **ORM** | SQLAlchemy | 2.0+ | 数据库访问 |
| **验证** | Pydantic | 2.0+ | 数据验证 |
| **数据库** | PostgreSQL | 17+ | 业务数据 |
| **缓存** | Redis | 7+ | Event Bus |
| **向量库** | Milvus | 2.5+ | 语义搜索 |
| **LLM** | Claude API | Sonnet 4 | AI 推理 |
| **HTTP** | httpx | 0.28+ | 异步 HTTP |
| **测试** | pytest | 8+ | 自动化测试 |

### 6.2 架构原则

| 原则 | 描述 | 实践 |
|------|------|------|
| **Event-Driven** | 事件驱动，解耦 Agent | Redis Event Bus |
| **Async I/O** | 全异步，无阻塞 | asyncpg, aioredis |
| **Repository Pattern** | 数据访问隔离 | *Repository 类 |
| **Dependency Injection** | 依赖注入 | 构造函数注入 |
| **Circuit Breaker** | 熔断保护 | LLM Gateway |
| **Event Sourcing** | 事件溯源 | 不可变事件日志 |
| **Graceful Degradation** | 优雅降级 | 非关键服务可禁用 |

### 6.3 LLM Gateway 规格

```python
class LLMGateway:
    """
    Claude API 网关

    特性:
    - 指数退避重试 (1s → 2s → 4s)
    - 断路器 (5次失败 → 60s恢复)
    - 成本追踪 (Token、USD)
    - 预算控制 (日/月限额)
    """

    # 重试配置
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1  # 秒
    MAX_BACKOFF = 10     # 秒
    BACKOFF_MULTIPLIER = 2

    # 断路器配置
    FAILURE_THRESHOLD = 5
    RECOVERY_TIMEOUT = 60  # 秒

    # 可重试错误
    RETRYABLE_ERRORS = [429, 500, 502, 503, 529]
```

### 6.4 Event Bus 规格

```python
class EventBus:
    """
    Redis 事件总线

    实现:
    - LPUSH/BRPOP FIFO 队列
    - 队列命名: projectcell:events:{event_type}
    - 非阻塞异步生成器
    """

    async def publish(self, event: Event) -> None:
        """发布事件到队列"""

    async def subscribe(self, event_types: list[str]) -> AsyncGenerator[Event]:
        """订阅事件流"""

    async def get_queue_length(self, event_type: str) -> int:
        """监控队列长度"""
```

---

## 7. 数据架构

### 7.1 ER 图

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     Meeting     │       │   Requirement   │       │  OpenQuestion   │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ id (PK)         │
│ title           │       │ meeting_id (FK) │──┐    │ requirement_id  │──┐
│ source          │◀──────│ title           │  │    │ question        │  │
│ content         │       │ description     │  │    │ context         │  │
│ participants    │       │ priority        │  │    │ answer          │  │
│ processed       │       │ status          │  │    │ answered_by     │  │
│ metadata        │       │ category        │  │    │ answered_at     │  │
│ created_at      │       │ confirmed_by    │  │    │ created_at      │  │
│ source_id       │       │ confirmed_at    │  │    └─────────────────┘  │
└─────────────────┘       │ rejected_reason │  │                         │
                          │ created_at      │  │                         │
                          │ updated_at      │  └─────────────────────────┘
                          └─────────────────┘

┌─────────────────┐
│    LLMUsage     │
├─────────────────┤
│ id (PK)         │
│ agent_id        │
│ task_type       │
│ model           │
│ input_tokens    │
│ output_tokens   │
│ cost_usd        │
│ latency_ms      │
│ success         │
│ error_message   │
│ created_at      │
└─────────────────┘
```

### 7.2 数据流

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   飞书      │    │  Webhook    │    │   Agent     │    │  PostgreSQL │
│   会议      │───▶│  /ingest    │───▶│  提取处理   │───▶│   持久化    │
└─────────────┘    └─────────────┘    └──────┬──────┘    └─────────────┘
                                             │
                                             ▼
                                      ┌─────────────┐
                                      │   Milvus    │
                                      │  向量索引   │
                                      └─────────────┘
```

### 7.3 向量存储设计

| 属性 | 值 |
|------|-----|
| Collection | `requirements` |
| Embedding | text-embedding (默认) |
| Metadata | meeting_id, priority, category |
| 距离度量 | Cosine Similarity |
| 持久化 | 本地文件系统 / Docker Volume |

---

## 8. API 规格

### 8.1 需求管理 API

#### 获取需求列表
```
GET /api/requirements

Query Parameters:
- status: pending | confirmed | rejected
- category: 功能 | 性能 | 硬件 | 集成 | UI | 安全 | 其他
- priority: HIGH | MEDIUM | LOW
- page: int (default 1)
- page_size: int (default 20)

Response 200:
{
  "items": [Requirement],
  "total": int,
  "page": int,
  "page_size": int
}
```

#### 确认需求
```
POST /api/requirements/{id}/confirm

Request Body:
{
  "confirmed_by": "张三"
}

Response 200:
{
  "id": "req_xxx",
  "status": "CONFIRMED",
  "confirmed_by": "张三",
  "confirmed_at": "2026-01-23T10:00:00Z"
}
```

#### 语义搜索
```
GET /api/requirements/search

Query Parameters:
- query: string (required)
- top_k: int (default 5)

Response 200:
{
  "results": [
    {
      "requirement": Requirement,
      "score": 0.95
    }
  ]
}
```

### 8.2 导入 API

#### 上传会议记录
```
POST /api/ingest/upload

Request Body:
{
  "title": "产品需求会议",
  "content": "会议纪要内容...",
  "source": "manual",
  "participants": ["张三", "李四"]
}

Response 200:
{
  "meeting_id": "mtg_xxx",
  "requirements_extracted": 3,
  "questions_generated": 1
}
```

#### 飞书 Webhook
```
POST /api/ingest/feishu

(飞书事件格式)

Response 200:
{
  "code": 0
}
```

### 8.3 导出 API

#### 生成 PRD
```
GET /api/export/prd

Query Parameters:
- format: markdown | html | pdf

Response 200:
{
  "content": "# PRD 文档...",
  "generated_at": "2026-01-23T10:00:00Z"
}
```

### 8.4 管理 API

#### LLM 使用统计
```
GET /api/admin/llm-usage

Query Parameters:
- date: YYYY-MM-DD
- agent_id: string (optional)

Response 200:
{
  "date": "2026-01-23",
  "total_calls": 42,
  "success_calls": 40,
  "failed_calls": 2,
  "total_input_tokens": 50000,
  "total_output_tokens": 15000,
  "total_cost_usd": 0.23,
  "by_agent": {...},
  "by_task_type": {...}
}
```

---

## 9. 质量要求

### 9.1 性能指标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| API 响应时间 (P95) | < 500ms | 不含 LLM 调用 |
| LLM 调用时间 (P95) | < 5s | 单次调用 |
| 需求提取时间 | < 30s | 端到端 |
| 系统可用性 | > 99.5% | 月度 SLA |
| Event 处理延迟 | < 1s | 队列到处理 |

### 9.2 可靠性要求

| 要求 | 实现 |
|------|------|
| LLM 调用失败 | 指数退避重试 (3次) |
| 服务过载 | 断路器熔断 |
| 数据库故障 | 优雅降级，返回缓存 |
| 消息丢失 | Redis 持久化，确认机制 |
| 成本失控 | 日/月预算硬限制 |

### 9.3 安全要求

| 要求 | 实现 |
|------|------|
| API 认证 | Bearer Token |
| 飞书签名 | SHA256 验证 |
| 敏感数据 | 不记录日志 |
| 环境变量 | 不提交 .env |
| 依赖安全 | 定期扫描 |

### 9.4 测试要求

| 测试类型 | 覆盖率目标 | 执行频率 |
|----------|:----------:|----------|
| 单元测试 | > 80% | 每次提交 |
| 集成测试 | > 60% | 每次提交 |
| 契约测试 | 100% Event | 每次提交 |
| E2E 冒烟 | 核心路径 | 每次提交 |
| E2E 完整 | 全流程 | 里程碑 |

---

## 10. 运营要求

### 10.1 部署架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         生产环境                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Nginx     │  │   FastAPI   │  │   FastAPI   │             │
│  │   LB/SSL    │──│   Pod 1     │  │   Pod 2     │  (可扩展)  │
│  └─────────────┘  └──────┬──────┘  └──────┬──────┘             │
│                          │                │                     │
│  ┌───────────────────────┴────────────────┴───────────────────┐│
│  │                    Kubernetes / Docker Compose              ││
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   ││
│  │  │PostgreSQL│  │  Redis   │  │  Milvus  │  │ Prometheus│   ││
│  │  │  (HA)    │  │ (Cluster)│  │          │  │  Grafana  │   ││
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 监控指标

| 类别 | 指标 | 告警阈值 |
|------|------|----------|
| **系统** | CPU 使用率 | > 80% |
| | 内存使用率 | > 85% |
| | 磁盘使用率 | > 90% |
| **应用** | API 错误率 | > 1% |
| | P95 延迟 | > 1s |
| | Event 队列积压 | > 1000 |
| **LLM** | 调用失败率 | > 5% |
| | 日成本 | > 预算 80% |
| | 断路器状态 | Open |
| **业务** | 需求提取失败 | > 10% |
| | 确认率 | < 50% (7天) |

### 10.3 运维命令

```bash
# 启动服务
python -m agents.requirement_manager.app.main

# 运行测试
.venv/bin/python -m pytest

# 数据库迁移
alembic upgrade head

# 健康检查
curl http://localhost:8000/api/feishu/health
curl http://localhost:8000/api/admin/circuit-breaker

# 查看 LLM 使用
curl http://localhost:8000/api/admin/llm-usage?date=2026-01-23
```

---

## 11. 路线图

### 11.1 里程碑计划

```
2026 Q1                    2026 Q2                    2026 Q3
   │                          │                          │
   ▼                          ▼                          ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ M1: 基础设施     │   │ M3: 研发 Agent  │   │ M5: 销售 Agent  │
│ ✅ Event Bus     │   │ ⏳ SW Developer  │   │ ⏳ Communicator  │
│ ✅ LLM Gateway   │   │ ⏳ Test Engineer │   │ ⏳ Demo Prep     │
│ ✅ BaseAgent     │   │ ⏳ Tech Writer   │   │ ⏳ Proposal Gen  │
└──────────────────┘   └──────────────────┘   └──────────────────┘
         │                      │                      │
         ▼                      ▼                      ▼
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ M2: Req Manager  │   │ M4: 交付 Agent  │   │ M6: 支持 Agent  │
│ ✅ 需求提取      │   │ ⏳ Deployer      │   │ ⏳ Monitor       │
│ ✅ 飞书集成      │   │ ⏳ Configurator  │   │ ⏳ Troubleshoot  │
│ ⏳ 优化完善      │   │ ⏳ Trainer       │   │ ⏳ Ticket        │
└──────────────────┘   └──────────────────┘   └──────────────────┘
```

### 11.2 版本规划

| 版本 | 目标 | 时间 | 状态 |
|------|------|------|:----:|
| v0.1 | 基础设施 MVP | 2026-01 | ✅ |
| v0.2 | Requirement Manager MVP | 2026-01 | ✅ |
| v0.3 | 飞书深度集成 | 2026-01 | ✅ |
| v0.4 | RM 优化 + 分析 | 2026-02 | ⏳ |
| v0.5 | Software Dev Agent | 2026-03 | 📋 |
| v0.6 | Test Agent | 2026-04 | 📋 |
| v1.0 | 研发流程闭环 | 2026-06 | 📋 |

### 11.3 当前迭代 (v0.4)

| 任务 | 优先级 | 状态 |
|------|:------:|:----:|
| /list 命令实现 | P1 | ⏳ |
| /export PRD 导出 | P1 | ⏳ |
| 日历事件订阅 | P2 | 📋 |
| 批量操作卡片 | P2 | 📋 |
| LLM 成本仪表盘 | P2 | 📋 |
| 需求变更追踪 | P3 | 📋 |

---

## 12. 风险管理

### 12.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|:----:|:----:|----------|
| Claude API 不可用 | 高 | 低 | 断路器 + 备用 LLM |
| 向量库性能瓶颈 | 中 | 中 | 分片 + 索引优化 |
| Event 队列积压 | 高 | 低 | 监控告警 + 自动扩容 |
| 成本超支 | 高 | 中 | 硬限额 + 实时监控 |

### 12.2 产品风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|:----:|:----:|----------|
| 提取准确率不足 | 高 | 中 | 迭代 Prompt + 人工校正 |
| 用户不信任 AI | 高 | 中 | Human-in-the-Loop |
| 飞书 API 变更 | 中 | 低 | 抽象层 + 版本锁定 |
| Agent 协作冲突 | 中 | 中 | 明确职责边界 |

### 12.3 运营风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|:----:|:----:|----------|
| 数据泄露 | 高 | 低 | 加密 + 权限控制 |
| 服务中断 | 高 | 低 | 高可用 + 自动恢复 |
| 团队流失 | 中 | 中 | 文档完善 + 知识转移 |

---

## 13. 附录

### 附录 A: 术语表

| 术语 | 定义 |
|------|------|
| Agent | 自主执行特定任务的 AI 程序 |
| Event | 系统中发生的不可变事实记录 |
| Event Bus | 事件传递的消息队列 |
| Human-in-the-Loop | 需要人工参与的决策点 |
| LLM | Large Language Model，大语言模型 |
| PRD | Product Requirements Document |
| RAG | Retrieval-Augmented Generation |
| ULID | Universally Unique Lexicographically Sortable Identifier |

### 附录 B: 参考文档

| 文档 | 位置 |
|------|------|
| 架构总览 | `docs/overview/architecture.md` |
| 需求管理 Agent PRD | `docs/specs/requirement-manager-agent-prd.md` |
| 飞书集成 PRD | `docs/specs/feishu-integration-prd.md` |
| Agent 开发指南 | `docs/guides/agent-development.md` |
| 运维手册 | `docs/guides/operations.md` |

### 附录 C: 配置清单

```bash
# === 数据库 ===
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=projectcell
POSTGRES_USER=postgres
POSTGRES_PASSWORD=***

# === 缓存 ===
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# === 向量库 ===
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=

# === LLM ===
ANTHROPIC_API_KEY=***
DEFAULT_MODEL=claude-sonnet-4-20250514
LLM_DAILY_BUDGET_USD=10.0
LLM_MONTHLY_BUDGET_USD=200.0

# === 飞书 ===
FEISHU_ENABLED=true
FEISHU_APP_ID=cli_***
FEISHU_APP_SECRET=***
FEISHU_ENCRYPT_KEY=***
FEISHU_VERIFY_SIGNATURE=true

# === 应用 ===
APP_ENV=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000
```

---

## 变更历史

| 日期 | 版本 | 变更内容 | 变更人 |
|------|------|---------|--------|
| 2026-01-23 | v1.0 | 初始 PRD | Claude |

---

*本文档由顶尖 AI 研发团队标准编写，适用于 Wisdoverse Cell 全景产品规划。*
