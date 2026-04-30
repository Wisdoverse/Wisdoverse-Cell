"""
DenialTracker unit tests

Tracks user-rejected actions to avoid re-proposing them.
Uses fakeredis for isolation.

Test coverage:
1. Not denied initially
2. Denied after record
3. Different user not denied
4. Different table not denied
5. Different action not denied
6. Clear by agent and user
7. Clear does not affect other users
8. Prometheus counter increments on hit
"""
import pytest

fakeredis = pytest.importorskip("fakeredis")
fakeredis_aioredis = fakeredis.aioredis

from shared.infra.denial_tracker import DENIAL_BLOCKED_TOTAL, DenialTracker


@pytest.fixture
async def redis():
    r = fakeredis_aioredis.FakeRedis()
    yield r
    await r.aclose()


@pytest.fixture
def tracker(redis):
    return DenialTracker(redis=redis, ttl=3600)


class TestRecordAndCheck:
    @pytest.mark.asyncio
    async def test_not_denied_initially(self, tracker):
        result = await tracker.is_denied(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_denied_after_record(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
        )
        assert result is not None
        assert result["reason"] == "user_rejected"

    @pytest.mark.asyncio
    async def test_different_user_not_denied(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied(
            agent_id="chat-agent",
            user_id="bob",
            action_type="update",
            table_id="tbl_abc",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_different_table_not_denied(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_xyz",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_different_action_not_denied(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        result = await tracker.is_denied(
            agent_id="chat-agent",
            user_id="alice",
            action_type="create",
            table_id="tbl_abc",
        )
        assert result is None


class TestClearDenials:
    @pytest.mark.asyncio
    async def test_clear_by_agent_and_user(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="create",
            table_id="tbl_xyz",
            reason="user_rejected",
        )
        count = await tracker.clear_denials(agent_id="chat-agent", user_id="alice")
        assert count == 2

        # Verify they are actually gone
        assert await tracker.is_denied("chat-agent", "alice", "update", "tbl_abc") is None
        assert await tracker.is_denied("chat-agent", "alice", "create", "tbl_xyz") is None

    @pytest.mark.asyncio
    async def test_clear_does_not_affect_other_users(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="bob",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )
        await tracker.clear_denials(agent_id="chat-agent", user_id="alice")

        # Bob's denial must survive
        result = await tracker.is_denied("chat-agent", "bob", "update", "tbl_abc")
        assert result is not None
        assert result["reason"] == "user_rejected"


class TestMetrics:
    @pytest.mark.asyncio
    async def test_blocked_counter_increments(self, tracker):
        await tracker.record_denial(
            agent_id="chat-agent",
            user_id="alice",
            action_type="update",
            table_id="tbl_abc",
            reason="user_rejected",
        )

        before = DENIAL_BLOCKED_TOTAL.labels(
            agent_id="chat-agent", action_type="update",
        )._value.get()

        await tracker.is_denied("chat-agent", "alice", "update", "tbl_abc")

        after = DENIAL_BLOCKED_TOTAL.labels(
            agent_id="chat-agent", action_type="update",
        )._value.get()

        assert after == before + 1
