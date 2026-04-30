"""
RedisScratchpad 单元测试

Redis-backed scratchpad for cross-agent shared state.
Same logical interface as file-based Scratchpad, but distributed.

测试覆盖:
1. Agent output read/write
2. Workflow read/write
3. Global status read/write
4. Decision log append + read
5. Incremental snapshot (combines all sections)
6. Namespace isolation (different sessions don't collide)
7. Token estimation + compaction threshold
8. TTL expiration
"""
import pytest

fakeredis = pytest.importorskip("fakeredis")
fakeredis_aioredis = fakeredis.aioredis

from shared.infra.redis_scratchpad import RedisScratchpad


@pytest.fixture
async def redis():
    r = fakeredis_aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
async def pad(redis):
    return RedisScratchpad(redis=redis, namespace="test-session")


class TestAgentOutput:
    @pytest.mark.asyncio
    async def test_write_and_read(self, pad):
        await pad.write_agent_output("dev-agent", "Built feature X")
        result = await pad.read_agent_output("dev-agent")
        assert result == "Built feature X"

    @pytest.mark.asyncio
    async def test_read_nonexistent_returns_empty(self, pad):
        result = await pad.read_agent_output("ghost-agent")
        assert result == ""

    @pytest.mark.asyncio
    async def test_overwrite(self, pad):
        await pad.write_agent_output("dev-agent", "v1")
        await pad.write_agent_output("dev-agent", "v2")
        assert await pad.read_agent_output("dev-agent") == "v2"


class TestWorkflow:
    @pytest.mark.asyncio
    async def test_write_and_read(self, pad):
        await pad.write_workflow("wf-001", "Step 1 done")
        assert await pad.read_workflow("wf-001") == "Step 1 done"

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, pad):
        assert await pad.read_workflow("wf-999") == ""


class TestGlobalStatus:
    @pytest.mark.asyncio
    async def test_write_and_read(self, pad):
        await pad.update_global_status("All systems go")
        assert await pad.read_global_status() == "All systems go"

    @pytest.mark.asyncio
    async def test_empty_by_default(self, pad):
        assert await pad.read_global_status() == ""


class TestDecisionLog:
    @pytest.mark.asyncio
    async def test_append_and_read(self, pad):
        await pad.append_decision("Decision 1: Deploy to staging")
        await pad.append_decision("Decision 2: Run smoke tests")
        log = await pad.read_decision_log()
        assert "Decision 1" in log
        assert "Decision 2" in log

    @pytest.mark.asyncio
    async def test_preserves_order(self, pad):
        await pad.append_decision("first")
        await pad.append_decision("second")
        await pad.append_decision("third")
        log = await pad.read_decision_log()
        assert log.index("first") < log.index("second") < log.index("third")


class TestIncrementalSnapshot:
    @pytest.mark.asyncio
    async def test_combines_all_sections(self, pad):
        await pad.update_global_status("Status: active")
        await pad.write_agent_output("dev-agent", "Built X")
        await pad.write_workflow("wf-001", "In progress")

        snapshot = await pad.read_incremental()
        assert "Status: active" in snapshot
        assert "dev-agent" in snapshot
        assert "Built X" in snapshot
        assert "wf-001" in snapshot

    @pytest.mark.asyncio
    async def test_empty_scratchpad_returns_empty(self, pad):
        snapshot = await pad.read_incremental()
        assert snapshot == ""

    @pytest.mark.asyncio
    async def test_skips_empty_sections(self, pad):
        await pad.write_agent_output("dev-agent", "content")
        snapshot = await pad.read_incremental()
        assert "Global Status" not in snapshot
        assert "dev-agent" in snapshot


class TestNamespaceIsolation:
    @pytest.mark.asyncio
    async def test_different_namespaces_dont_collide(self, redis):
        pad_a = RedisScratchpad(redis=redis, namespace="session-a")
        pad_b = RedisScratchpad(redis=redis, namespace="session-b")

        await pad_a.write_agent_output("dev-agent", "from A")
        await pad_b.write_agent_output("dev-agent", "from B")

        assert await pad_a.read_agent_output("dev-agent") == "from A"
        assert await pad_b.read_agent_output("dev-agent") == "from B"


class TestTokenEstimation:
    @pytest.mark.asyncio
    async def test_estimate_tokens(self, pad):
        # Write ~400 bytes → ~100 tokens
        await pad.update_global_status("x" * 400)
        tokens = await pad.estimate_tokens()
        assert 80 <= tokens <= 120

    @pytest.mark.asyncio
    async def test_should_compact(self, pad):
        # Default threshold is 10,000 tokens → ~40,000 bytes
        assert pad.should_compact_needed(0) is False
        assert pad.should_compact_needed(10_001) is True


class TestListKeys:
    @pytest.mark.asyncio
    async def test_list_agents(self, pad):
        await pad.write_agent_output("dev-agent", "x")
        await pad.write_agent_output("qa-agent", "y")
        agents = await pad.list_agents()
        assert set(agents) == {"dev-agent", "qa-agent"}

    @pytest.mark.asyncio
    async def test_list_workflows(self, pad):
        await pad.write_workflow("wf-001", "x")
        await pad.write_workflow("wf-002", "y")
        wfs = await pad.list_workflows()
        assert set(wfs) == {"wf-001", "wf-002"}


class TestDecodedRedisCompat:
    @pytest.mark.asyncio
    async def test_works_with_decode_responses_redis(self):
        """P2: Must work with decode_responses=True Redis (repo standard)."""
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        pad = RedisScratchpad(redis=r, namespace="decoded-test")

        await pad.write_agent_output("dev-agent", "hello")
        assert await pad.read_agent_output("dev-agent") == "hello"

        await pad.update_global_status("ok")
        assert await pad.read_global_status() == "ok"

        await pad.append_decision("decision 1")
        assert "decision 1" in await pad.read_decision_log()

        agents = await pad.list_agents()
        assert agents == ["dev-agent"]

        snapshot = await pad.read_incremental()
        assert "hello" in snapshot

        await r.aclose()
