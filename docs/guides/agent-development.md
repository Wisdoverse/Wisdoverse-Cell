# Agent Development Guide

> Language note: English is the primary documentation language. This legacy document may still contain Chinese implementation details; when editing it, put the English explanation first.

> Wisdoverse Cell Agent 开发完整指南。面向需要新增 Agent 的开发者。

---

## 1. 概述

Wisdoverse Cell 是一个 AI Native OS 架构，由 2 名人类 + 26 个 Agent 组成。每个 Agent 是一个独立的 FastAPI 微服务，具备：

- **独立进程**：每个 Agent 运行在自己的容器中，拥有独立的端口、数据库用户和 Redis db
- **事件驱动**：Agent 之间通过 Redis Streams（EventBus）进行异步通信
- **统一接口**：所有 Agent 继承 `BaseAgent`，实现标准的 `handle_event()` / `handle_request()` 方法
- **LLM 统一网关**：所有 LLM 调用必须通过 `LLMGateway`，禁止直接 import anthropic

Agent 的核心职责是：**订阅事件 -> 处理业务逻辑 -> 发布新事件**。

---

## 2. 目录结构模板

新建 Agent 时，请严格遵循以下目录结构：

```
agents/my_agent/
├── __init__.py
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 入口，lifespan 管理
│   └── metrics.py           # Prometheus 自定义指标（可选）
├── api/
│   ├── __init__.py
│   ├── my_routes.py         # REST API 路由
│   └── schemas.py           # API 请求/响应 Pydantic 模型
├── core/
│   ├── __init__.py
│   └── my_service.py        # 业务逻辑（纯逻辑，不依赖框架）
├── service/
│   ├── __init__.py
│   └── agent.py             # BaseAgent 实现（事件处理入口）
├── models/
│   ├── __init__.py
│   └── schemas.py           # 内部数据模型 / Pydantic 模型
├── db/
│   ├── __init__.py
│   ├── database.py          # SQLAlchemy engine/session 管理
│   └── repository.py        # Repository pattern 数据库操作
├── tests/
│   ├── __init__.py
│   ├── test_agent.py        # Agent 基本行为测试
│   ├── test_service.py      # 业务逻辑测试
│   └── conftest.py          # pytest fixtures
└── Dockerfile               # 独立构建（可选，优先用 Dockerfile.agents）
```

关键原则：
- `service/agent.py` 只做**事件路由和编排**，复杂逻辑放 `core/`
- `db/` 使用 Repository pattern，不在业务层写 raw SQL
- `api/` 的 Pydantic 模型和 `models/` 的内部模型分开，不要混用

---

## 3. BaseAgent 实现

所有 Agent 必须继承 `shared.schemas.agent.BaseAgent`。

### 3.1 BaseAgent 接口

```python
# shared/schemas/agent.py 中的核心接口
class BaseAgent(ABC):
    def __init__(
        self,
        agent_id: str,              # kebab-case，如 "my-agent"
        agent_name: str,            # 显示名称，如 "My Agent"
        subscribed_events: list[str] | None = None,
        published_events: list[str] | None = None,
    ): ...

    @abstractmethod
    async def handle_event(self, event: Event) -> list[Event]: ...

    @abstractmethod
    async def handle_request(self, request: dict) -> dict: ...

    async def startup(self) -> None: ...
    async def shutdown(self) -> None: ...

    def create_event(self, event_type: str, payload: dict, trace_id: str | None = None) -> Event: ...
```

### 3.2 实现示例

以下是基于 `agents/pjm_agent/service/agent.py` 的真实模式：

```python
"""MyAgent - 示例 Agent 实现"""
import asyncio
from typing import Optional

from shared.config import settings as app_settings
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event, EventTypes
from shared.services.event_bus import EventBus, event_bus
from shared.services.llm_gateway import llm_gateway
from shared.utils.logger import get_logger

from ..core.my_service import MyService
from ..db.database import DatabaseManager, db_manager

logger = get_logger("my_agent.service")


class MyAgent(BaseAgent):
    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        bus: Optional[EventBus] = None,
    ):
        super().__init__(
            agent_id="my-agent",
            agent_name="My Agent",
            subscribed_events=[
                EventTypes.REQUIREMENT_CONFIRMED,
            ],
            published_events=[
                EventTypes.FEATURE_COMPLETED,
            ],
        )
        self._db_manager = db or db_manager
        self._event_bus = bus or event_bus
        self._service: MyService | None = None
        self._listener_tasks: list[asyncio.Task] = []

    async def startup(self):
        """Agent 启动：初始化数据库、连接 EventBus、启动事件监听"""
        logger.info("agent_starting", agent_id=self.agent_id)

        # 开发环境自动建表
        if app_settings.app_env == "development":
            await self._db_manager.create_tables()

        await self._event_bus.connect()
        self._service = MyService(llm_gateway)

        # 为每个订阅的事件类型启动独立的监听协程
        for event_type in self.subscribed_events:
            task = asyncio.create_task(self._event_loop(event_type))
            self._listener_tasks.append(task)

        logger.info("agent_started", agent_id=self.agent_id)

    async def shutdown(self):
        """Agent 关闭：取消监听、断开连接、释放资源"""
        logger.info("agent_stopping", agent_id=self.agent_id)
        for task in self._listener_tasks:
            task.cancel()
        for task in self._listener_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._event_bus.disconnect()
        await self._db_manager.close()
        logger.info("agent_stopped", agent_id=self.agent_id)

    async def handle_event(self, event: Event) -> list[Event]:
        """事件路由：根据 event_type 分发到不同的处理方法"""
        if event.event_type == EventTypes.REQUIREMENT_CONFIRMED:
            return await self._handle_requirement(event)
        logger.warning("unhandled_event", event_type=event.event_type)
        return []

    async def handle_request(self, request: dict) -> dict:
        """HTTP API 请求处理入口"""
        action = request.get("action")
        if action == "status":
            return {"status": "ok", "agent": self.agent_id}
        return {"error": "unknown_action"}

    async def _handle_requirement(self, event: Event) -> list[Event]:
        """处理需求确认事件"""
        result = await self._service.process(event.payload)
        return [
            self.create_event(
                event_type=EventTypes.FEATURE_COMPLETED,
                payload=result,
                trace_id=event.metadata.trace_id,
            )
        ]

    async def _event_loop(self, event_type: str):
        """事件监听循环"""
        async for event in self._event_bus.subscribe(
            [event_type], group=self.agent_id
        ):
            try:
                new_events = await self.handle_event(event)
                for evt in new_events:
                    await self._event_bus.publish(evt)
            except Exception as e:
                logger.error("event_handling_failed",
                    event_type=event_type, error=str(e))


# 模块级单例 + getter（供 API 层使用）
agent = MyAgent()

def get_agent() -> MyAgent:
    return agent
```

**注意事项**：
- `agent_id` 必须是 **kebab-case**（如 `my-agent`），不要用下划线
- 构造函数接受可选的 `db` 和 `bus` 参数，方便测试时注入 mock
- `startup()` 中连接外部依赖，`shutdown()` 中释放资源
- `handle_event()` 返回 `list[Event]`，由事件循环负责发布
- 使用 `self.create_event()` 创建事件，自动设置 `source_agent`

---

## 4. 事件注册

### 4.1 EventTypes 常量

所有事件类型定义在 `shared/schemas/event.py` 的 `EventTypes` 类中：

```python
class EventTypes:
    # 需求相关
    REQUIREMENT_EXTRACTED = "requirement.extracted"
    REQUIREMENT_CONFIRMED = "requirement.confirmed"
    REQUIREMENT_CHANGED   = "requirement.changed"

    # PM 相关
    SYNC_COMPLETED              = "sync.completed"
    SYNC_TASK_NEEDS_DECOMPOSE   = "sync.task-needs-decompose"
    PM_ALERT_TRIGGERED          = "pm.alert-triggered"
    PM_DECOMPOSE_COMPLETED      = "pm.decompose-completed"

    # 聊天相关
    CHAT_PM_QUERY    = "chat.pm-query"
    CHAT_PM_RESPONSE = "chat.pm-response"
    # ... 更多见 shared/schemas/event.py
```

### 4.2 事件命名规范

事件类型格式为 `{domain}.{action}`，遵循以下规则：

| 规则 | 正确 | 错误 |
|------|------|------|
| 小写 + 点分隔 | `requirement.confirmed` | `RequirementConfirmed` |
| 过去式表已完成 | `code.committed` | `code.commit` |
| 多词用连字符 | `analysis.risk-detected` | `analysis.risk_detected` |

### 4.3 新增事件类型

1. 在 `shared/schemas/event.py` 的 `EventTypes` 中添加常量
2. 在 Agent 的 `__init__` 中注册到 `subscribed_events` 或 `published_events`
3. 更新相关文档

### 4.4 Event 模型

```python
class Event(BaseModel):
    event_id: str        # 自动生成 "evt_{ulid}"
    event_type: str      # "{domain}.{action}"
    timestamp: datetime  # 自动生成 UTC 时间
    source_agent: str    # 发送方 agent_id
    payload: dict        # 业务数据
    metadata: EventMetadata  # trace_id, retry_count, correlation_id
```

事件是**不可变**的，**fire-and-forget**。使用 `trace_id` 关联同一业务流程中的多个事件。

---

## 5. REST API 开发

### 5.1 Router 定义

```python
# agents/my_agent/api/my_routes.py
from fastapi import APIRouter, HTTPException
from shared.utils.logger import get_logger
from ..service.agent import get_agent
from .schemas import MyResponse

router = APIRouter(prefix="/api/v1/my-agent", tags=["my-agent"])
logger = get_logger("my_agent.api")


@router.get("/status", response_model=MyResponse)
async def get_status():
    agent = get_agent()
    try:
        result = await agent.handle_request({"action": "status"})
        return MyResponse(**result)
    except Exception as e:
        logger.error("status_api_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal error")
```

### 5.2 FastAPI App 入口（使用 create_agent_app）

使用 `create_agent_app()` 工厂函数创建标准化的 FastAPI 应用。**不要手写 lifespan、middleware、health endpoints** — 框架全部处理。

```python
# agents/my_agent/app/main.py
from fastapi import Depends

from shared.app import create_agent_app
from shared.middleware.internal_auth import verify_internal_key

from ..api.my_routes import router as my_router
from ..service.agent import agent as _raw_agent

app = create_agent_app(
    _raw_agent,
    title="My Agent",
    description="My Agent 描述",
    routers=[(my_router, [Depends(verify_internal_key)])],
)
```

所有 Agent 间调用的 API **必须**加 `verify_internal_key` 依赖，通过 `X-Internal-Key` header 鉴权。

**create_agent_app 自动提供**：
- `/health` 和 `/health/ready` 健康检查端点
- Middleware stack（RequestTracing、APIKey、AccessLog、RateLimit、SecurityHeaders、CORS）
- Prometheus `/metrics` 端点（如果 `prometheus_fastapi_instrumentator` 可用）
- OpenTelemetry tracing
- Evolution 自进化包裹（EvolvedAgent + KillSwitch）
- 结构化日志

### 5.3 带定时任务的 Agent

如果 Agent 有 scheduler（如 PJM Agent 的定时告警），使用 `on_startup` / `on_shutdown` hooks：

```python
# agents/my_agent/app/main.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from shared.app import create_agent_app

scheduler = AsyncIOScheduler()

app = create_agent_app(
    _raw_agent,
    title="My Agent",
    routers=[(my_router, [Depends(verify_internal_key)])],
    on_startup=lambda runtime: _start_scheduler(runtime),
    on_shutdown=lambda _: _stop_scheduler(),
)

async def _my_scheduled_job():
    # 重要：使用 runtime.agent（经过 EvolvedAgent 包裹的版本）
    # 不要直接调用 _raw_agent，否则定时任务不会被追踪
    await app.state.runtime.agent.handle_request({"action": "my_action"})

async def _start_scheduler(runtime):
    scheduler.add_job(_my_scheduled_job, CronTrigger(hour=10), id="my_job", replace_existing=True)
    scheduler.start()

async def _stop_scheduler():
    scheduler.shutdown(wait=False)
```

> **注意**：Scheduler jobs 必须调用 `app.state.runtime.agent`（而非 `_raw_agent`），确保定时操作也经过 Evolution 追踪。

### 5.4 create_agent_app 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `agent` | BaseAgent | 必填 | Agent 实例 |
| `title` | str | agent_name | FastAPI 标题 |
| `description` | str | 自动生成 | FastAPI 描述 |
| `version` | str | "1.0.0" | API 版本 |
| `routers` | list | None | Router 列表或 (router, deps) 元组列表 |
| `on_startup` | async callable | None | 启动后回调，接收 runtime |
| `on_shutdown` | async callable | None | 关闭前回调，接收 runtime |
| `evolution_enabled` | bool | True | 是否启用自进化 |
| `evolution_excluded` | bool | False | 排除自进化（用于 Evolution Agent 自身） |
| `include_api_key_middleware` | bool | True | 是否包含 APIKey 中间件 |

### 5.5 Health Endpoints（自动提供）

`create_agent_app` 自动注册以下端点，**不需要手动编写**：

- `GET /health` — Liveness 探针：返回 `{"status": "alive", "agent": "<agent_id>"}`
- `GET /health/ready` — Readiness 探针：聚合 agent + 所有 plugin 的健康状态，503 表示降级

### 5.6 插件系统（RuntimePlugin）

AgentRuntime 支持插件扩展，遵循开闭原则：

```python
from shared.app import RuntimePlugin

class MyPlugin(RuntimePlugin):
    name = "my-plugin"

    def wrap_agent(self, agent):
        """包裹 Agent 添加横切关注点（如追踪、限流）"""
        return MyWrapper(agent)

    async def startup(self, runtime):
        """Agent 启动后执行"""
        await self.connect_to_service()

    async def shutdown(self, runtime):
        """Agent 关闭前执行（反序执行，依赖安全）"""
        await self.disconnect()

    async def health_check(self):
        """贡献健康检查数据"""
        return {"my_service": self._connected}
```

内置插件：
- `EvolutionPlugin` — EvolvedAgent 包裹 + KillSwitch（默认启用）

自定义插件注册（需要直接使用 AgentRuntime）：
```python
from shared.app import AgentRuntime, EvolutionPlugin

runtime = AgentRuntime(my_agent)
runtime.use(EvolutionPlugin())
runtime.use(MyCustomPlugin())
```

---

## 6. Agent 间通信

两种通信方式：**EventBus（异步）** 和 **HTTP AgentClient（同步）**。

### 6.1 选择规则

| 场景 | 使用方式 | 原因 |
|------|---------|------|
| 通知/广播（不需要返回值） | EventBus | 解耦，fire-and-forget |
| 状态变更通知 | EventBus | 多个 Agent 可能订阅 |
| 需要返回值的操作 | HTTP AgentClient | 请求-响应模式 |
| 审批/人工确认 | HTTP AgentClient | 需要明确的成功/失败 |
| 跨 Agent 查询数据 | HTTP AgentClient | 需要同步拿到结果 |

### 6.2 EventBus 使用

```python
# 发布事件
event = self.create_event(
    event_type=EventTypes.PM_ALERT_TRIGGERED,
    payload={"alert_id": "xxx", "severity": "high"},
    trace_id=original_event.metadata.trace_id,
)
await self._event_bus.publish(event)

# 订阅事件（通常在 startup 中启动）
async for event in self._event_bus.subscribe(
    ["sync.completed"], group=self.agent_id
):
    await self.handle_event(event)
```

EventBus 基于 Redis Streams，每个 consumer group（`group=agent_id`）独立消费，支持 ACK、重试和 replay。

### 6.3 HTTP AgentClient

```python
# shared/services/agent_client.py
from shared.services.agent_client import AgentClient

client = AgentClient(base_url="http://pjm-agent:8012")
result = await client.post("/api/v1/pm/config/refresh")
result = await client.get("/api/v1/pm/config")
```

AgentClient 自动在请求中添加 `X-Internal-Key` header。对于频繁使用的 Agent，创建 Typed Client：

```python
# shared/services/agent_client.py 中的 PMAgentClient 示例
class PMAgentClient:
    def __init__(self, base_url: str | None = None):
        url = base_url or settings.pjm_agent_url
        self._client = AgentClient(url)

    async def approve_decomposition(self, wp_id: int, operator: str) -> dict | None:
        try:
            return await self._client.post(
                f"/api/v1/pm/decompose/{wp_id}/approve",
                json={"operator": operator},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
```

---

## 7. 配置管理

### 7.1 全局 Settings

所有配置通过 `shared/config.py` 中的 `Settings` 类管理，基于 `pydantic-settings`：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 数据库
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "projectcell"
    postgres_user: str = "cell"
    postgres_password: str = ""

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # LLM
    anthropic_api_key: str = ""
    default_model: str = "claude-opus-4-6"

    # 应用
    app_env: str = "development"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
```

配置优先级：**环境变量 > `.env` 文件 > 默认值**

### 7.2 使用方式

```python
from shared.config import settings

# 直接使用
if settings.debug:
    logger.debug("debug_mode_enabled")

# 数据库 URL
engine = create_async_engine(settings.database_url)
```

### 7.3 新增配置项

1. 在 `Settings` 类中添加字段（带默认值）
2. 在 `docker-compose.yml` 中设置对应的环境变量
3. **严禁**使用 `class Config`，必须用 `model_config = SettingsConfigDict(...)`（Pydantic v2）
4. **严禁**使用 `datetime.utcnow()`，必须用 `datetime.now(UTC)`

---

## 8. 数据库隔离

每个 Agent 拥有独立的 PostgreSQL 用户和 Redis db，实现数据隔离。

### 8.1 PostgreSQL

在 `docker-compose.yml` 中为每个 Agent 配置独立用户：

```yaml
pjm-agent:
  environment:
    POSTGRES_USER: ${PM_AGENT_DB_USER:-pjm_agent}
    POSTGRES_PASSWORD: ${PM_AGENT_DB_PASSWORD:-pjm_agent_dev}
    POSTGRES_DB: ${POSTGRES_DB:-projectcell}  # 共享数据库名
```

- 每个 Agent 用自己的 schema 或表前缀
- 通过 PostgreSQL GRANT 控制权限，Agent 只能访问自己的表
- 生产环境必须为每个 Agent 创建独立的 DB 用户

### 8.2 Redis

```yaml
pjm-agent:
  environment:
    REDIS_DB: "2"  # 每个 Agent 分配不同的 db
```

当前 Redis db 分配约定：

| Redis DB | 用途 |
|----------|------|
| 0 | EventBus（所有 Agent 共享） |
| 1 | AI Core / Requirement Manager |
| 2 | PJM Agent |
| 3+ | 其他 Agent 按需分配 |

**注意**：EventBus 始终使用 db 0，无论 Agent 的 `redis_db` 设置为多少（见 `settings.redis_event_bus_url`）。

### 8.3 DatabaseManager 模式

```python
# agents/my_agent/db/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from shared.config import settings

engine = create_async_engine(settings.database_url, pool_size=settings.db_pool_size)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

---

## 9. LLM 调用

### 9.1 必须通过 LLMGateway

`shared/services/llm_gateway.py` 提供统一的 LLM 调用入口，所有 Agent **禁止直接** `import anthropic`。

LLMGateway 提供：
- 统一接口
- 成本追踪（Redis-based 每日/每月预算）
- 失败重试（指数退避）
- 断路器（防止雪崩）
- 调用记录持久化
- 超预算自动降级模型

### 9.2 使用方式

```python
from shared.services.llm_gateway import llm_gateway

# 在 Agent 中使用
result = await llm_gateway.chat(
    messages=[{"role": "user", "content": "..."}],
    model=settings.chat_model,  # 或 decompose_model, summary_model
)
```

### 9.3 模型选择

| 用途 | 配置项 | 推荐模型 | 成本 |
|------|--------|----------|------|
| 复杂推理/拆解 | `settings.decompose_model` | claude-opus-4 | $$$ |
| 对话/交互 | `settings.chat_model` | claude-sonnet-4 | $$ |
| 摘要/报告 | `settings.summary_model` | claude-haiku-4.5 | $ |

### 9.4 LLM 失败处理

**CPO 关键问题**：_"Graceful fallback if LLM fails?"_

每个调用 LLM 的地方都必须处理失败情况：

```python
try:
    result = await llm_gateway.chat(messages=messages, model=model)
except CircuitBreakerError:
    logger.warning("llm_circuit_open, using fallback")
    result = self._fallback_result()
except Exception as e:
    logger.error("llm_call_failed", error=str(e))
    result = self._fallback_result()
```

---

## 10. Docker 部署

### 10.1 推荐方式：multi-stage Dockerfile.agents

优先使用 `docker/Dockerfile.agents` 的 multi-target 构建：

```bash
docker build --target my-agent -f docker/Dockerfile.agents .
docker compose build my-agent
```

### 10.2 独立 Dockerfile 模板

如果需要独立 Dockerfile（参考 `agents/pjm_agent/Dockerfile`）：

```dockerfile
# Stage 1: Builder
FROM python:3.13-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim AS runtime

LABEL org.opencontainers.image.title="My Agent" \
      org.opencontainers.image.vendor="Wisdoverse Cell"

# 安全：非 root 用户
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 tini curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appgroup shared/ /app/shared/
COPY --chown=appuser:appgroup agents/my_agent/ /app/agents/my_agent/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    API_PORT=8020

USER appuser
EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail --silent http://localhost:8020/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", \
     "agents.my_agent.app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8020", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
```

### 10.3 docker-compose 服务定义

在 `docker-compose.yml` 中添加：

```yaml
my-agent:
  build:
    context: .
    dockerfile: docker/Dockerfile.agents
    target: my-agent
  image: ${REGISTRY:-}projectcell/my-agent:${VERSION:-latest}
  container_name: ${COMPOSE_PROJECT_NAME:-projectcell}-my-agent
  hostname: my-agent
  environment:
    POSTGRES_HOST: postgres
    POSTGRES_PORT: "5432"
    POSTGRES_DB: ${POSTGRES_DB:-projectcell}
    POSTGRES_USER: ${MY_AGENT_DB_USER:-my_agent}
    POSTGRES_PASSWORD: ${MY_AGENT_DB_PASSWORD:-my_agent_dev}
    REDIS_HOST: redis
    REDIS_PORT: "6379"
    REDIS_DB: "5"                    # 分配未使用的 db 编号
    ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
    INTERNAL_SERVICE_KEY: ${INTERNAL_SERVICE_KEY:-}
    APP_ENV: ${APP_ENV:-development}
  ports:
    - "${MY_AGENT_PORT:-8020}:8020"
  networks:
    - backend
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: "0.5"
  restart: unless-stopped
  labels:
    - "com.projectcell.service=my-agent"
    - "com.projectcell.tier=application"
```

---

## 11. 测试要求

### 11.1 测试结构

```
agents/my_agent/tests/
├── conftest.py            # fixtures: mock event_bus, mock db, mock llm
├── test_agent.py          # BaseAgent 行为测试
├── test_service.py        # 业务逻辑单元测试
├── test_api.py            # API 端点集成测试
└── test_event_handling.py # 事件处理测试
```

运行测试：

```bash
.venv/bin/python -m pytest agents/my_agent/tests/ -v
```

### 11.2 必须覆盖的测试场景

**Agent 基础测试**（参考 `shared/services/channel_gateway/tests/unit/test_agent.py`）：

```python
from shared.schemas.agent import BaseAgent
from ..service.agent import MyAgent

class TestMyAgentClass:
    def test_inherits_from_base_agent(self):
        agent = MyAgent()
        assert isinstance(agent, BaseAgent)

    def test_agent_id_is_kebab_case(self):
        agent = MyAgent()
        assert agent.agent_id == "my-agent"
        assert "-" in agent.agent_id

    def test_subscribed_events(self):
        agent = MyAgent()
        assert "requirement.confirmed" in agent.subscribed_events

    def test_published_events(self):
        agent = MyAgent()
        assert "feature.completed" in agent.published_events

    def test_accepts_custom_event_bus(self):
        from unittest.mock import MagicMock
        mock_bus = MagicMock()
        agent = MyAgent(bus=mock_bus)
        assert agent._event_bus is mock_bus

    def test_create_event_sets_source_agent(self):
        agent = MyAgent()
        event = agent.create_event(
            event_type="feature.completed",
            payload={"id": "123"},
        )
        assert event.source_agent == "my-agent"
        assert event.event_id.startswith("evt_")
```

**必须覆盖的场景清单**：

| 类别 | 测试项 |
|------|--------|
| Agent 元数据 | agent_id kebab-case, subscribed/published events |
| 依赖注入 | 可以注入 mock db, mock bus |
| 事件处理 | 每种 subscribed event 的 handle_event |
| 事件创建 | create_event 设置 source_agent, trace_id 传递 |
| API 端点 | 每个 endpoint 的 happy path + error path |
| LLM 失败 | LLM 调用失败时的 graceful fallback |
| handle_request | 每种 action 的处理 |

---

## 12. 检查清单

新 Agent 上线前，逐项确认：

### 架构

- [ ] 继承 `BaseAgent`，实现 `handle_event()` / `handle_request()`
- [ ] `agent_id` 使用 kebab-case（如 `my-agent`）
- [ ] `subscribed_events` 和 `published_events` 正确声明
- [ ] 新事件类型已添加到 `shared/schemas/event.py` 的 `EventTypes`
- [ ] 目录结构符合标准模板

### 代码质量

- [ ] 全部使用 async I/O，无阻塞调用
- [ ] Pydantic v2：`model_dump_json()` / `model_validate_json()`
- [ ] Pydantic v2：`model_config = ConfigDict()` 而非 `class Config`
- [ ] 日期时间：`datetime.now(UTC)` 而非 `datetime.utcnow()`
- [ ] 日志中**严禁**记录密钥、token 等敏感信息
- [ ] 运行 `code-simplifier` 清理代码

### 安全

- [ ] API 路由添加 `verify_internal_key` 依赖
- [ ] health endpoint **不需要**鉴权
- [ ] Dockerfile 使用非 root 用户（`appuser`）
- [ ] 未直接 `import anthropic`，通过 `llm_gateway` 调用

### 部署

- [ ] 独立 PostgreSQL 用户，权限最小化
- [ ] Redis db 编号不与其他 Agent 冲突
- [ ] `docker-compose.yml` 服务定义完整
- [ ] HEALTHCHECK 配置正确
- [ ] 资源限制（memory, cpus）已设置

### 测试

- [ ] Agent 元数据测试通过
- [ ] 事件处理测试覆盖所有 subscribed events
- [ ] API 端点测试覆盖 happy path + error path
- [ ] LLM 调用失败有 graceful fallback
- [ ] `pytest` 全部通过

### 文档

- [ ] 在 `docker-compose.yml` 中注册服务
- [ ] 环境变量在 `.env.example` 中有说明
- [ ] 如有新的 Agent 间依赖，更新相关 Agent 的配置

### Git 工作流

- [ ] 在 feature branch 上开发，**绝不**直接提交到 `main`
- [ ] 提交前运行完整测试
- [ ] MR 描述包含 checklist 完成状态
