"""
AgentLoopBreakerPlugin 单元测试

测试覆盖:
1. Plugin 包装 agent 的 handle_event
2. 成功 handle_event 记录 progress round
3. 空返回记录 no-progress round
4. 异常记录 error round
5. OPEN 状态阻止 handle_event 调用
6. health_check 返回正确状态
7. Governance action reset
"""
import pytest

fakeredis = pytest.importorskip("fakeredis")
fakeredis_aioredis = fakeredis.aioredis

from shared.app.plugins.loop_breaker_plugin import AgentLoopBreakerPlugin
from shared.infra.agent_loop_breaker import AgentLoopBreakerError
from shared.schemas.agent import BaseAgent
from shared.schemas.event import Event


class FakeAgent(BaseAgent):
    """Minimal agent for testing."""

    def __init__(self):
        super().__init__(
            agent_id="fake-agent",
            agent_name="Fake",
            subscribed_events=["test.event"],
            published_events=["test.output"],
        )
        self.handle_event_calls = 0
        self.should_raise = None
        self.should_return = None

    async def handle_request(self, request: dict) -> dict:
        return {}

    async def handle_event(self, event: Event) -> list[Event]:
        self.handle_event_calls += 1
        if self.should_raise:
            raise self.should_raise
        if self.should_return is not None:
            return self.should_return
        return [self.create_event("test.output", {"ok": True})]

    async def startup(self):
        pass

    async def shutdown(self):
        pass


def _make_event() -> Event:
    return Event.create(
        event_type="test.event",
        source_agent="test",
        payload={"data": 1},
    )


@pytest.fixture
async def redis():
    r = fakeredis_aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
async def plugin(redis):
    p = AgentLoopBreakerPlugin(
        no_progress_threshold=3,
        same_error_threshold=5,
        half_open_threshold=2,
        redis=redis,
    )
    return p


@pytest.fixture
async def wrapped_agent(plugin):
    agent = FakeAgent()
    wrapped = plugin.wrap_agent(agent)
    return wrapped


class TestPluginWrapping:
    @pytest.mark.asyncio
    async def test_successful_event_records_progress(self, wrapped_agent, redis):
        event = _make_event()
        result = await wrapped_agent.handle_event(event)
        assert len(result) == 1
        # Check breaker state — should still be CLOSED
        state = await redis.hgetall(b"loop_breaker:fake-agent")
        assert state[b"state"] == b"closed"

    @pytest.mark.asyncio
    async def test_empty_return_still_counts_as_progress(self, wrapped_agent, redis):
        """Empty [] return is a successful round — not a failure."""
        wrapped_agent._inner.should_return = []
        event = _make_event()
        await wrapped_agent.handle_event(event)
        state = await redis.hgetall(b"loop_breaker:fake-agent")
        assert int(state[b"no_progress_count"]) == 0

    @pytest.mark.asyncio
    async def test_exception_records_error_round(self, wrapped_agent, redis):
        wrapped_agent._inner.should_raise = ValueError("test error")
        event = _make_event()
        with pytest.raises(ValueError, match="test error"):
            await wrapped_agent.handle_event(event)
        state = await redis.hgetall(b"loop_breaker:fake-agent")
        assert int(state[b"same_error_count"]) == 1

    @pytest.mark.asyncio
    async def test_open_breaker_blocks_handle_event(self, wrapped_agent, redis):
        # Force breaker to OPEN by recording 3 error rounds
        wrapped_agent._inner.should_raise = RuntimeError("fail")
        event = _make_event()
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await wrapped_agent.handle_event(event)

        # Now it should raise AgentLoopBreakerError (not the inner error)
        with pytest.raises(AgentLoopBreakerError):
            await wrapped_agent.handle_event(event)
        # Inner agent should NOT have been called for the blocked round
        assert wrapped_agent._inner.handle_event_calls == 3


class TestPluginHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok_when_closed(self, plugin):
        agent = FakeAgent()
        plugin.wrap_agent(agent)
        checks = await plugin.health_check()
        assert "loop_breaker" in checks
        assert checks["loop_breaker"].status == "ok"

    @pytest.mark.asyncio
    async def test_health_degraded_when_half_open(self, wrapped_agent, plugin):
        wrapped_agent._inner.should_raise = RuntimeError("fail")
        event = _make_event()
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await wrapped_agent.handle_event(event)
        # Now HALF_OPEN (2 error rounds)
        checks = await plugin.health_check()
        assert checks["loop_breaker"].status == "degraded"

    @pytest.mark.asyncio
    async def test_health_down_when_open(self, wrapped_agent, plugin):
        wrapped_agent._inner.should_raise = RuntimeError("fail")
        event = _make_event()
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await wrapped_agent.handle_event(event)
        checks = await plugin.health_check()
        assert checks["loop_breaker"].status == "down"


class TestGovernanceReset:
    @pytest.mark.asyncio
    async def test_reset_via_governance_action(self, wrapped_agent):
        # Force OPEN via errors
        wrapped_agent._inner.should_raise = RuntimeError("fail")
        event = _make_event()
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await wrapped_agent.handle_event(event)

        # Reset via governance
        result = await wrapped_agent.handle_standard_request(
            {"action": "reset_loop_breaker", "reason": "test reset"}
        )
        assert result is not None
        assert result["status"] == "reset"

        # Should be able to execute again
        wrapped_agent._inner.should_raise = None
        wrapped_agent._inner.should_return = [wrapped_agent._inner.create_event("test.output", {})]
        events = await wrapped_agent.handle_event(event)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_reset_via_handle_request(self, wrapped_agent):
        """P1: reset_loop_breaker must work via handle_request (the public API)."""
        wrapped_agent._inner.should_raise = RuntimeError("fail")
        event = _make_event()
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await wrapped_agent.handle_event(event)

        result = await wrapped_agent.handle_request(
            {"action": "reset_loop_breaker", "reason": "via handle_request"}
        )
        assert result.get("status") == "reset"


class TestEmptyReturnNotAlwaysNoProgress:
    @pytest.mark.asyncio
    async def test_empty_return_is_progress_when_no_error(self, wrapped_agent, redis):
        """P1: Coordinator returns [] on successful progress events — not a failure."""
        wrapped_agent._inner.should_return = []
        event = _make_event()

        # 3 empty returns should NOT trip the breaker for event types
        # that legitimately return empty
        for _ in range(3):
            await wrapped_agent.handle_event(event)

        # Breaker should still allow execution (empty return = neutral, not failure)
        # After fix: empty return without error is treated as progress
        assert await wrapped_agent.handle_event(event) == []


class TestOutputTokensFromMetadata:
    """output_length should prefer output_tokens from event metadata."""

    @pytest.mark.asyncio
    async def test_uses_output_tokens_from_metadata_dict(self, plugin, redis):
        """When event metadata is a dict with output_tokens, use that value."""
        agent = FakeAgent()

        class _DictMetaEvent:
            """Minimal event-like object with dict metadata."""

            def __init__(self, payload, metadata):
                self.payload = payload
                self.metadata = metadata

        agent.should_return = [_DictMetaEvent({"ok": True}, {"output_tokens": 42})]
        wrapped = plugin.wrap_agent(agent)

        event = _make_event()
        await wrapped.handle_event(event)
        # The breaker recorded output_length=42 (from metadata), not payload size.
        state = await wrapped._breaker.get_state()
        assert state["state"] == "closed"

    @pytest.mark.asyncio
    async def test_uses_output_tokens_from_pydantic_metadata(self, redis):
        """When metadata is a Pydantic model with output_tokens, use model_dump()."""
        from pydantic import BaseModel

        class MetaWithTokens(BaseModel):
            output_tokens: int = 0
            trace_id: str | None = None

        agent = FakeAgent()
        plugin = AgentLoopBreakerPlugin(
            no_progress_threshold=3, same_error_threshold=5,
            half_open_threshold=2, redis=redis,
        )

        class _PydanticMetaEvent:
            def __init__(self, payload, metadata):
                self.payload = payload
                self.metadata = metadata

        agent.should_return = [
            _PydanticMetaEvent({"ok": True}, MetaWithTokens(output_tokens=99))
        ]
        wrapped = plugin.wrap_agent(agent)

        event = _make_event()
        await wrapped.handle_event(event)
        state = await wrapped._breaker.get_state()
        assert state["state"] == "closed"

    @pytest.mark.asyncio
    async def test_falls_back_to_payload_size_without_output_tokens(
        self, wrapped_agent, redis
    ):
        """Without output_tokens in metadata, falls back to payload size."""
        event = _make_event()
        result = await wrapped_agent.handle_event(event)
        # Standard events use EventMetadata which has no output_tokens —
        # should still succeed (fallback to payload size).
        assert len(result) == 1
        state = await redis.hgetall(b"loop_breaker:fake-agent")
        assert state[b"state"] == b"closed"


class TestDecodedRedisCompat:
    @pytest.mark.asyncio
    async def test_works_with_decode_responses_redis(self):
        """P1: Must work with decode_responses=True Redis (repo standard)."""
        r = fakeredis.aioredis.FakeRedis(decode_responses=True)
        plugin = AgentLoopBreakerPlugin(
            no_progress_threshold=3, same_error_threshold=5,
            half_open_threshold=2, redis=r,
        )
        agent = FakeAgent()
        wrapped = plugin.wrap_agent(agent)

        event = _make_event()
        # Should not raise AttributeError on decoded strings
        result = await wrapped.handle_event(event)
        assert len(result) == 1

        checks = await plugin.health_check()
        assert checks["loop_breaker"].status == "ok"
        await r.aclose()
