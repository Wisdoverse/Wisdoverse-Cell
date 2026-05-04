"""
E2E test fixtures.

Provides:
- Test database (PostgreSQL)
- Test Redis (EventBus)
- FastAPI test client
- Mock/real LLM switching

Design principles:
- Each test function gets an isolated DB session and EventBus (function scope)
- Agent lifecycle is managed by tests instead of FastAPI lifespan
- All non-critical external dependencies are isolated in tests
"""
import sys
from pathlib import Path

# Ensure the project root is on the Python path before other imports.
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

# Test environment configuration, set before importing the app.
# Local development uses non-standard ports to avoid production conflicts;
# CI may override these defaults with standard ports.
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "projectcell_test")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6380")
os.environ.setdefault("MILVUS_URI", "http://localhost:19531")
os.environ["FEISHU_ENABLED"] = "false"  # Disable Feishu notifications during tests.

# Read effective configuration values; CI can override the defaults.
_POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
_POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5433")
_POSTGRES_DB = os.environ.get("POSTGRES_DB", "projectcell_test")
_POSTGRES_USER = os.environ.get("POSTGRES_USER", "test")
_POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "test")
_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6380")
_MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19531")

from agents.requirement_manager.app.main import app
from agents.requirement_manager.db.database import DatabaseManager
from agents.requirement_manager.db.vector_store import VectorStore
from agents.requirement_manager.service.agent import RequirementManagerAgent
from shared.infra.event_bus import EventBus
from shared.infra.llm_gateway import llm_gateway as _llm_gw_instance
from shared.infra.milvus_store import MilvusVectorStore
from shared.schemas.event import Event

logger = logging.getLogger(__name__)

# Fixtures directory.
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"

# Default E2E smoke-test timeout, in seconds.
E2E_TIMEOUT = 30


# ============ Database Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_db() -> AsyncGenerator[DatabaseManager, None]:
    """Test database, reset before each test."""
    db = DatabaseManager(
        database_url=f"postgresql+asyncpg://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}@{_POSTGRES_HOST}:{_POSTGRES_PORT}/{_POSTGRES_DB}"
    )

    # Recreate tables.
    await db.drop_tables()
    await db.create_tables()

    yield db

    # Cleanup.
    await db.drop_tables()
    await db.close()


# ============ Redis Fixtures ============

@pytest_asyncio.fixture(scope="function")
async def test_event_bus() -> AsyncGenerator[EventBus, None]:
    """Test EventBus."""
    bus = EventBus(
        redis_url=f"redis://{_REDIS_HOST}:{_REDIS_PORT}/0",
        queue_prefix="projectcell_test:events"
    )
    await bus.connect()

    # Clear test queues.
    if bus._redis:
        keys = await bus._redis.keys("projectcell_test:events:*")
        if keys:
            await bus._redis.delete(*keys)

    yield bus

    # Cleanup.
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

    This fixture manages the agent lifecycle without relying on FastAPI
    lifespan. During teardown it closes the consumer task and EventBus first,
    then lets the test_db fixture clean up the database.
    """
    from agents.requirement_manager.db.database import get_db

    test_agent = await _create_test_agent(test_db, test_event_bus)

    async def override_get_db():
        async with test_db.session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    with patch("agents.requirement_manager.api.ingest.get_agent", return_value=test_agent), \
         patch("agents.requirement_manager.api.feedback.get_agent", return_value=test_agent), \
         patch("agents.requirement_manager.app.main.agent", test_agent):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()

    # Safely shut down the agent: close only the consumer task and EventBus.
    # Do not close db_manager; the test_db fixture owns that lifecycle.
    await _safe_shutdown_agent(test_agent)


# ============ LLM Fixtures ============

@pytest.fixture
def mock_llm():
    """Mock LLM Gateway that returns recorded responses."""

    def load_fixture(name: str) -> str:
        fixture_path = FIXTURES_DIR / f"{name}.json"
        if fixture_path.exists():
            return fixture_path.read_text()
        msg = f"LLM fixture not found: {fixture_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    async def mock_call(prompt: str, **kwargs):
        # Return different fixtures based on prompt content.
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
    """Real LLM for full E2E runs."""
    # No mock: use the real service.
    yield


# ============ Helper Functions ============

@pytest.fixture
def sample_meeting_content() -> str:
    """Sample meeting content."""
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
    from agents.requirement_manager.tests.fixtures.seed_data import MeetingFactory
    return MeetingFactory


@pytest.fixture
def requirement_factory():
    """Requirement data factory for lifecycle testing"""
    from agents.requirement_manager.tests.fixtures.seed_data import RequirementFactory
    return RequirementFactory


@pytest.fixture
def scenario_runner(client):
    """E2E scenario runner"""
    from agents.requirement_manager.tests.fixtures.seed_data import ScenarioRunner
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

    Note: do not start the event consumer task, to avoid background tasks
    interfering with tests. Tests that need consumed events should read them
    manually through the get_published_events fixture.
    """
    agent = RequirementManagerAgent(
        db=test_db,
        bus=test_event_bus,
        vectors=_create_vector_store(),
    )

    # Initialize manually instead of calling startup(), avoiding the background
    # event-consumer task.
    await test_event_bus.connect()
    try:
        await agent._vector_store.initialize()
    except Exception as exc:
        logger.warning("test_vector_store_init_failed (semantic search disabled): %s", exc)
    logger.info("test_agent_initialized")

    return agent


async def _safe_shutdown_agent(agent: RequirementManagerAgent) -> None:
    """Safely shut down the test agent without closing the test DB."""
    import asyncio

    # Stop the event-consumer task, if present.
    consumer = getattr(agent, "_consumer_task", None)
    if consumer:
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass

    # Close the vector-store connection.
    await agent._vector_store.close()

    # Do not call agent._event_bus.disconnect(); test_event_bus owns it.
    # Do not call agent._db_manager.close(); test_db owns it.


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
    from agents.requirement_manager.db.database import get_db

    test_agent = await _create_test_agent(test_db, test_event_bus)

    async def override_get_db():
        async with test_db.session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    _setup_otel_instrumentation(tracer)

    with patch("agents.requirement_manager.api.ingest.get_agent", return_value=test_agent), \
         patch("agents.requirement_manager.api.feedback.get_agent", return_value=test_agent), \
         patch("agents.requirement_manager.app.main.agent", test_agent):

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            yield client

    _teardown_otel_instrumentation(tracer)
    app.dependency_overrides.clear()
    await _safe_shutdown_agent(test_agent)
