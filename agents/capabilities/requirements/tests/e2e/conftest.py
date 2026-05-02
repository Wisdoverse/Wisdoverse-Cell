"""
E2E 测试 Fixtures

提供:
- 测试数据库（PostgreSQL）
- 测试 Redis（事件总线）
- FastAPI 测试客户端
- Mock/Real LLM 切换

设计原则:
- 每个测试函数使用独立的 DB session 和 EventBus（function scope）
- Agent 生命周期由测试管理，不触发 FastAPI lifespan
- 所有非关键外部依赖在测试中被隔离
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中（必须在其他导入之前）
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import logging
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# 测试环境配置（在导入 app 之前设置）
# 本地开发使用非标准端口避免与生产冲突，CI 使用标准端口
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "projectcell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6380")
os.environ.setdefault("MILVUS_URI", "http://localhost:19531")
os.environ["FEISHU_ENABLED"] = "false"  # 测试时禁用飞书通知

# 读取实际配置值（CI 会覆盖默认值）
_POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
_POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5433")
_POSTGRES_DB = os.environ.get("POSTGRES_DB", "projectcell_test")
_POSTGRES_USER = os.environ.get("POSTGRES_USER", "test")
_POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "test")
_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6380")
_MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19531")

from agents.capabilities.requirements.app.main import app
from agents.capabilities.requirements.db.database import DatabaseManager
from agents.capabilities.requirements.db.vector_store import VectorStore
from agents.capabilities.requirements.service.agent import RequirementManagerAgent
from shared.infra.event_bus import EventBus
from shared.infra.llm_gateway import llm_gateway as _llm_gw_instance
from shared.infra.milvus_store import MilvusVectorStore
from shared.schemas.event import Event

logger = logging.getLogger(__name__)

# Fixtures 目录
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"

# E2E smoke 测试默认超时（秒）
E2E_TIMEOUT = 30


# ============ 数据库 Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[DatabaseManager, None]:
    """测试数据库，每个测试前清空"""
    db = DatabaseManager(
        database_url=f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{_POSTGRES_HOST}:{_POSTGRES_PORT}/{_POSTGRES_DB}"
    )

    # 重建表
    await db.drop_tables()
    await db.create_tables()

    yield db

    # 清理
    await db.drop_tables()
    await db.close()


# ============ Redis Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_event_bus() -> AsyncGenerator[EventBus, None]:
    """测试事件总线"""
    bus = EventBus(
        redis_url=f"redis://{_REDIS_HOST}:{_REDIS_PORT}/0",
        queue_prefix="projectcell_test:events"
    )
    await bus.connect()

    # 清空测试队列
    if bus._redis:
        keys = await bus._redis.keys("projectcell_test:events:*")
        if keys:
            await bus._redis.delete(*keys)

    yield bus

    # 清理
    if bus._redis:
        keys = await bus._redis.keys("projectcell_test:events:*")
        if keys:
            await bus._redis.delete(*keys)
    await bus.disconnect()


@pytest_asyncio.fixture(scope="function")
async def get_published_events(test_event_bus: EventBus):
    """Retrieve events published during a test for assertion.

    **Why this is needed**: The EventBus uses Redis Streams with consumer
    groups.  This fixture creates a ``_test_observer`` consumer group on
    every requirement-domain stream so it can read back published events
    via ``XREADGROUP``.

    The ``_test_observer`` group name is reserved for testing and will
    not collide with any agent consumer group.
    """
    _test_group = "_test_observer"

    # All requirement-domain event types (superset of what any agent
    # may publish).  Registering extra types is harmless — it just
    # creates an empty stream that is cleaned up on teardown.
    _observed_types = [
        "requirement.extracted",
        "requirement.confirmed",
        "requirement.rejected",
        "requirement.deleted",
    ]
    for et in _observed_types:
        stream_key = test_event_bus._get_stream_key(et)
        await test_event_bus._ensure_consumer_group(stream_key, _test_group)

    async def _get_events(event_type: str) -> list[Event]:
        """Drain all events of *event_type* from the observer consumer group.

        Uses non-blocking ``XREADGROUP`` (block=0, count=100) so tests
        never hang waiting for events that were not published.
        """
        if test_event_bus._redis is None:
            raise RuntimeError(
                f"Cannot retrieve events for '{event_type}': "
                "Redis connection is not available."
            )
        events: list[Event] = []
        stream_key = test_event_bus._get_stream_key(event_type)
        consumer = test_event_bus._consumer_name()

        results = await test_event_bus._redis.xreadgroup(
            groupname=_test_group,
            consumername=consumer,
            streams={stream_key: ">"},
            count=100,
            block=0,
        )

        if results:
            for _skey, messages in results:
                for message_id, fields in messages:
                    data = fields.get("data", "")
                    event = Event.model_validate_json(data)
                    events.append(event)
                    await test_event_bus._redis.xack(
                        stream_key, _test_group, message_id,
                    )

        return events

    yield _get_events

    # Cleanup: best-effort removal.  The parent test_event_bus fixture
    # does a full key cleanup anyway via keys("projectcell_test:events:*").
    for et in _observed_types:
        try:
            stream_key = test_event_bus._get_stream_key(et)
            await test_event_bus._redis.delete(stream_key)
        except Exception:
            logger.debug("cleanup failed for observer stream %s", et, exc_info=True)


# ============ App Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def client(test_db, test_event_bus) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI test client with isolated Agent instance per test.

    Agent 生命周期由此 fixture 管理（不依赖 FastAPI lifespan）。
    teardown 时先关闭 consumer task 和 event bus，再让 test_db fixture 自行清理 DB。
    """
    from agents.capabilities.requirements.db.database import get_db

    test_agent = await _create_test_agent(test_db, test_event_bus)

    async def override_get_db():
        async with test_db.session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with patch("agents.capabilities.requirements.api.ingest.get_agent", return_value=test_agent), \
         patch("agents.capabilities.requirements.api.feedback.get_agent", return_value=test_agent), \
         patch("agents.capabilities.requirements.app.main.agent", test_agent):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()

    # 安全关闭 agent：只关闭 consumer task 和 event bus，
    # 不关闭 db_manager（由 test_db fixture 自行管理）
    await _safe_shutdown_agent(test_agent)


# ============ LLM Fixtures ============

@pytest.fixture
def mock_llm():
    """Mock LLM Gateway，返回预录响应"""

    def load_fixture(name: str) -> str:
        fixture_path = FIXTURES_DIR / f"{name}.json"
        if fixture_path.exists():
            return fixture_path.read_text()
        msg = f"LLM fixture not found: {fixture_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    async def mock_call(prompt: str, **kwargs):
        # 根据 prompt 内容返回不同的 fixture
        prompt_lower = prompt.lower()

        if "提取" in prompt or "extract" in prompt_lower:
            return load_fixture("extract_requirements")
        elif "prd" in prompt_lower:
            return load_fixture("generate_prd")
        elif "冲突" in prompt or "conflict" in prompt_lower:
            return load_fixture("check_conflict")
        elif "问题" in prompt or "question" in prompt_lower:
            return load_fixture("generate_questions")

        return "{}"

    with patch.object(_llm_gw_instance, "complete", new=AsyncMock(side_effect=mock_call)):
        yield


@pytest.fixture
def real_llm():
    """真实 LLM（Full E2E 使用）"""
    # 不做 mock，使用真实服务
    yield


# ============ 辅助函数 ============

@pytest.fixture
def sample_meeting_content() -> str:
    """示例会议内容"""
    return """
    今天的会议讨论了录音分析项目的需求。

    客户提出以下要求：
    1. 必须支持离线录音功能，设备在无网络时也能工作
    2. 录音文件需要支持 MP3 和 WAV 格式
    3. 希望能自动识别说话人

    张总说这些功能必须在下个版本实现。

    待确认问题：
    - 离线存储的容量上限是多少？
    - 是否需要支持其他音频格式？
    """


# ============ Seed Data Fixtures ============

@pytest.fixture
def meeting_factory():
    """Meeting data factory for scenario-based testing"""
    from agents.capabilities.requirements.tests.fixtures.seed_data import MeetingFactory
    return MeetingFactory


@pytest.fixture
def requirement_factory():
    """Requirement data factory for lifecycle testing"""
    from agents.capabilities.requirements.tests.fixtures.seed_data import RequirementFactory
    return RequirementFactory


@pytest.fixture
def scenario_runner(client):
    """E2E scenario runner"""
    from agents.capabilities.requirements.tests.fixtures.seed_data import ScenarioRunner
    return ScenarioRunner(client)


# ============ Observability Fixtures ============

@pytest.fixture(scope="session")
def tracing_enabled():
    """Check if tracing is enabled for this test run"""
    return os.environ.get("ENABLE_TRACING", "0") == "1"


@pytest.fixture(scope="session")
def tracer(tracing_enabled):
    """OpenTelemetry tracer (only if tracing is enabled)"""
    if not tracing_enabled:
        yield None
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Setup tracer provider
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

        # Configure OTLP exporter
        otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

        otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        yield trace.get_tracer("e2e-tests")

        # Cleanup
        provider.shutdown()

    except ImportError:
        # OpenTelemetry not installed
        yield None


@pytest.fixture(autouse=True)
def trace_test(request, tracer):
    """Automatically trace each test (if tracing is enabled)"""
    if tracer is None:
        yield
        return

    test_name = request.node.name
    test_file = request.fspath.basename if request.fspath else "unknown"

    with tracer.start_as_current_span(test_name) as span:
        span.set_attribute("test.file", test_file)
        span.set_attribute("test.name", test_name)

        # Add markers as attributes
        markers = [marker.name for marker in request.node.iter_markers()]
        if markers:
            span.set_attribute("test.markers", ",".join(markers))

        yield


# ============ Internal Helpers ============


def _create_vector_store() -> VectorStore:
    """Create a VectorStore backed by Milvus for E2E tests.

    Uses the test Milvus instance (port 19531 by default, overridable
    via MILVUS_URI env var).
    """
    milvus_backend = MilvusVectorStore(uri=_MILVUS_URI)
    return VectorStore(store=milvus_backend, collection="requirements_test")


async def _create_test_agent(
    test_db: DatabaseManager,
    test_event_bus: EventBus,
) -> RequirementManagerAgent:
    """Create and initialize a test agent instance.

    注意: 不启动 event consumer task (避免后台任务干扰测试)。
    如果测试需要事件消费，应使用 get_published_events fixture 手动读取。
    """
    agent = RequirementManagerAgent(
        db=test_db,
        bus=test_event_bus,
        vectors=_create_vector_store(),
    )

    # 手动初始化而非调用 startup()，避免启动 event consumer 后台任务
    await test_event_bus.connect()
    try:
        await agent._vector_store.initialize()
    except Exception as exc:
        logger.warning("test_vector_store_init_failed (semantic search disabled): %s", exc)
    logger.info("test_agent_initialized")

    return agent


async def _safe_shutdown_agent(agent: RequirementManagerAgent) -> None:
    """安全关闭 test agent，不关闭 db（由 test_db fixture 管理）。"""
    import asyncio

    # 停止事件消费 task（如果有的话）
    consumer = getattr(agent, "_consumer_task", None)
    if consumer:
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass

    # 关闭向量库连接
    await agent._vector_store.close()

    # 不调用 agent._event_bus.disconnect() — 由 test_event_bus fixture 管理
    # 不调用 agent._db_manager.close() — 由 test_db fixture 管理


def _setup_otel_instrumentation(tracer) -> None:
    """Setup OpenTelemetry instrumentation if tracer is available"""
    if tracer is None:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass


def _teardown_otel_instrumentation(tracer) -> None:
    """Teardown OpenTelemetry instrumentation if it was setup"""
    if tracer is None:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        FastAPIInstrumentor.uninstrument_app(app)
        HTTPXClientInstrumentor().uninstrument()
    except ImportError:
        pass


@pytest_asyncio.fixture(scope="function")
async def traced_client(test_db, test_event_bus, tracer):
    """FastAPI client with OpenTelemetry instrumentation (if tracing enabled)"""
    from agents.capabilities.requirements.db.database import get_db

    test_agent = await _create_test_agent(test_db, test_event_bus)

    async def override_get_db():
        async with test_db.session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    _setup_otel_instrumentation(tracer)

    with patch("agents.capabilities.requirements.api.ingest.get_agent", return_value=test_agent), \
         patch("agents.capabilities.requirements.api.feedback.get_agent", return_value=test_agent), \
         patch("agents.capabilities.requirements.app.main.agent", test_agent):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            yield client

    _teardown_otel_instrumentation(tracer)
    app.dependency_overrides.clear()
    await _safe_shutdown_agent(test_agent)
