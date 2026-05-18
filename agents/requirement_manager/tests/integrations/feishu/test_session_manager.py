"""Tests for SessionManager — session lifecycle, timeout, extraction trigger."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.requirement_manager.integrations.feishu import (
    session_manager as _sm_mod,
)
from agents.requirement_manager.integrations.feishu.session_manager import (
    SessionManager,
)

# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────


@pytest.fixture
def mock_agent():
    """MagicMock agent with async extract_from_session."""
    agent = MagicMock()
    agent.extract_from_session = AsyncMock()
    return agent


@pytest.fixture
def manager(mock_redis, mock_db_session, mock_agent):
    """SessionManager wired to mock redis, db, and agent."""
    return SessionManager(mock_redis, mock_db_session, mock_agent)


@pytest.fixture
def manager_no_agent(mock_redis, mock_db_session):
    """SessionManager with agent=None."""
    return SessionManager(mock_redis, mock_db_session, agent=None)


def _patch_repo(message_count: int):
    """Return a context-manager that patches message-store session counts."""
    repo = MagicMock()
    repo.count_by_session = AsyncMock(return_value=message_count)
    return patch.object(_sm_mod, "SqlAlchemyRequirementMessageStore", return_value=repo)


# ──────────────────────────────────────────────
# TestSessionCreation
# ──────────────────────────────────────────────


class TestSessionCreation:
    """get_or_create_session — create, reuse, isolate, extend."""

    @pytest.mark.asyncio
    async def test_create_new_session__returns_session_id_with_prefix(
        self, manager, mock_redis
    ):
        """First call for a chat_id creates a session starting with 'ses_'."""
        session_id = await manager.get_or_create_session("oc_chat_new")

        assert session_id.startswith("ses_")
        assert manager._active_sessions["oc_chat_new"] == session_id
        score = mock_redis.get_score(manager.REDIS_KEY, "oc_chat_new")
        assert score is not None
        assert score > time.time() - 1  # set in the future

    @pytest.mark.asyncio
    async def test_reuse_existing_session__same_chat_id(self, manager):
        """Repeated calls with the same chat_id return the identical session_id."""
        first = await manager.get_or_create_session("oc_chat_reuse")
        second = await manager.get_or_create_session("oc_chat_reuse")

        assert first == second

    @pytest.mark.asyncio
    async def test_different_chats__different_sessions(self, manager):
        """Distinct chat_ids yield distinct session_ids."""
        sid_a = await manager.get_or_create_session("oc_chat_a")
        sid_b = await manager.get_or_create_session("oc_chat_b")

        assert sid_a != sid_b

    @pytest.mark.asyncio
    async def test_timeout_extended__mock_time_advancing(self, manager, mock_redis):
        """A second message bumps the Redis timeout score forward."""
        t0 = 1_700_000_000.0

        with patch.object(_sm_mod, "time") as mock_time:
            mock_time.time.return_value = t0
            await manager.get_or_create_session("oc_chat_extend")
            first_score = mock_redis.get_score(manager.REDIS_KEY, "oc_chat_extend")

            mock_time.time.return_value = t0 + 60  # 60 s later
            await manager.get_or_create_session("oc_chat_extend")
            second_score = mock_redis.get_score(manager.REDIS_KEY, "oc_chat_extend")

        assert second_score > first_score
        assert second_score - first_score == pytest.approx(60.0)


# ──────────────────────────────────────────────
# TestTimeoutDetection
# ──────────────────────────────────────────────


class TestTimeoutDetection:
    """check_timeouts — active, expired, extraction gating."""

    @pytest.mark.asyncio
    async def test_active_session__no_timeout(self, manager, mock_redis):
        """A session whose score is in the future is NOT expired."""
        await manager.get_or_create_session("oc_active")

        with _patch_repo(message_count=10):
            processed = await manager.check_timeouts()

        assert processed == []
        assert "oc_active" in manager._active_sessions

    @pytest.mark.asyncio
    async def test_timeout_session__triggers_extraction(
        self, manager, mock_redis, mock_agent
    ):
        """An expired session triggers agent.extract_from_session."""
        session_id = await manager.get_or_create_session("oc_expired")

        # Simulate expired timeout
        mock_redis._data[manager.REDIS_KEY]["oc_expired"] = time.time() - 100

        with _patch_repo(message_count=10):
            processed = await manager.check_timeouts()

        assert processed == [session_id]
        assert "oc_expired" not in manager._active_sessions
        mock_agent.extract_from_session.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_message_count_below_min__skip_extraction(
        self, manager, mock_redis, mock_agent
    ):
        """Fewer than the configured min messages threshold => no extraction call."""
        session_id = await manager.get_or_create_session("oc_few_msgs")
        mock_redis._data[manager.REDIS_KEY]["oc_few_msgs"] = time.time() - 100

        with _patch_repo(message_count=2):
            processed = await manager.check_timeouts()

        assert session_id in processed
        mock_agent.extract_from_session.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_agent_none__skip_extraction(
        self, manager_no_agent, mock_redis
    ):
        """When agent is None, _on_session_ended completes without error."""
        session_id = await manager_no_agent.get_or_create_session("oc_no_agent")
        mock_redis._data[manager_no_agent.REDIS_KEY]["oc_no_agent"] = time.time() - 100

        with _patch_repo(message_count=10):
            processed = await manager_no_agent.check_timeouts()

        assert session_id in processed

    @pytest.mark.asyncio
    async def test_agent_extract_exception__no_crash(
        self, manager, mock_redis, mock_agent
    ):
        """If agent.extract_from_session raises, check_timeouts still returns normally."""
        mock_agent.extract_from_session = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        session_id = await manager.get_or_create_session("oc_err")
        mock_redis._data[manager.REDIS_KEY]["oc_err"] = time.time() - 100

        with _patch_repo(message_count=10):
            processed = await manager.check_timeouts()

        assert session_id in processed
        mock_agent.extract_from_session.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_multiple_expired__all_processed(
        self, manager, mock_redis, mock_agent
    ):
        """Multiple expired chats are all processed in one call."""
        ids = {}
        for chat in ("oc_m1", "oc_m2", "oc_m3"):
            ids[chat] = await manager.get_or_create_session(chat)
            mock_redis._data[manager.REDIS_KEY][chat] = time.time() - 50

        with _patch_repo(message_count=10):
            processed = await manager.check_timeouts()

        assert set(processed) == set(ids.values())
        assert manager._active_sessions == {}

    @pytest.mark.asyncio
    async def test_expired_chat_without_active_session__skipped(
        self, manager, mock_redis, mock_agent
    ):
        """A Redis entry with no matching _active_sessions entry is cleaned up silently."""
        # Inject an orphan entry directly into Redis
        mock_redis._data[manager.REDIS_KEY] = {"oc_orphan": time.time() - 100}

        with _patch_repo(message_count=10):
            processed = await manager.check_timeouts()

        assert processed == []
        assert mock_redis.get_score(manager.REDIS_KEY, "oc_orphan") is None

    @pytest.mark.asyncio
    async def test_check_timeouts__redis_entry_removed(
        self, manager, mock_redis, mock_agent
    ):
        """After processing, the expired entry is removed from Redis."""
        await manager.get_or_create_session("oc_rem")
        mock_redis._data[manager.REDIS_KEY]["oc_rem"] = time.time() - 100

        with _patch_repo(message_count=10):
            await manager.check_timeouts()

        assert mock_redis.get_score(manager.REDIS_KEY, "oc_rem") is None


# ──────────────────────────────────────────────
# TestForceEndSession
# ──────────────────────────────────────────────


class TestForceEndSession:
    """force_end_session — exists vs. nonexistent chat."""

    @pytest.mark.asyncio
    async def test_existing_session__returns_session_id_and_cleans_up(
        self, manager, mock_redis, mock_agent
    ):
        """Force-ending an active session returns its id, cleans Redis, triggers extraction."""
        session_id = await manager.get_or_create_session("oc_force")

        with _patch_repo(message_count=10):
            result = await manager.force_end_session("oc_force")

        assert result == session_id
        assert "oc_force" not in manager._active_sessions
        assert mock_redis.get_score(manager.REDIS_KEY, "oc_force") is None
        mock_agent.extract_from_session.assert_awaited_once_with(session_id)

    @pytest.mark.asyncio
    async def test_nonexistent_session__returns_none(self, manager):
        """Force-ending a chat that has no active session returns None."""
        result = await manager.force_end_session("oc_ghost")

        assert result is None


# ──────────────────────────────────────────────
# TestGetActiveSessions
# ──────────────────────────────────────────────


class TestGetActiveSessions:
    """get_active_sessions — empty and populated states."""

    @pytest.mark.asyncio
    async def test_empty__returns_empty_dict(self, manager):
        """No sessions => empty dict."""
        result = await manager.get_active_sessions()

        assert result == {}

    @pytest.mark.asyncio
    async def test_with_sessions__returns_copy(self, manager):
        """Returns a copy that does not mutate internal state."""
        sid_a = await manager.get_or_create_session("oc_a")
        sid_b = await manager.get_or_create_session("oc_b")

        result = await manager.get_active_sessions()

        assert result == {"oc_a": sid_a, "oc_b": sid_b}

        # Mutating the copy must not affect internal dict
        result["oc_c"] = "ses_injected"
        assert "oc_c" not in manager._active_sessions


# ──────────────────────────────────────────────
# TestCleanup
# ──────────────────────────────────────────────


class TestCleanup:
    """cleanup — tears down every active session."""

    @pytest.mark.asyncio
    async def test_cleanup__ends_all_sessions(self, manager, mock_redis, mock_agent):
        """After cleanup, _active_sessions is empty and Redis entries are gone."""
        chats = ["oc_c1", "oc_c2", "oc_c3"]
        for chat in chats:
            await manager.get_or_create_session(chat)

        with _patch_repo(message_count=2):
            await manager.cleanup()

        assert manager._active_sessions == {}
        for chat in chats:
            assert mock_redis.get_score(manager.REDIS_KEY, chat) is None


# ──────────────────────────────────────────────
# TestSetAgent
# ──────────────────────────────────────────────


class TestSetAgent:
    """set_agent — late-binding the agent reference."""

    def test_set_agent__updates_reference(self, manager_no_agent):
        """set_agent replaces None with a concrete agent."""
        assert manager_no_agent.agent is None

        new_agent = MagicMock()
        manager_no_agent.set_agent(new_agent)

        assert manager_no_agent.agent is new_agent
