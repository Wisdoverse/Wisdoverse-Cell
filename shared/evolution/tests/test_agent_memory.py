"""Tests for AgentMemory three-tier memory (Redis + PG + Milvus)."""

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import shared.evolution.agent_memory as agent_memory_module
from shared.evolution.agent_memory import AgentMemory

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_redis(get_value=None, raise_on_get=False, raise_on_set=False):
    """Return an AsyncMock redis client."""
    redis = AsyncMock()
    if raise_on_get:
        redis.get.side_effect = ConnectionError("Redis down")
    else:
        redis.get.return_value = get_value
    if raise_on_set:
        redis.set.side_effect = ConnectionError("Redis down")
    return redis


def _make_db_manager(memory_row=None, raise_on_session=False):
    """Return a mock db_manager whose session() context manager yields a mock session."""
    db_manager = MagicMock()

    if raise_on_session:
        @asynccontextmanager
        async def _bad_session():
            raise RuntimeError("DB connection failed")
            yield  # pragma: no cover
        db_manager.session.return_value = _bad_session()
        db_manager.session.side_effect = RuntimeError("DB connection failed")
    else:
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_memory.return_value = memory_row
        mock_repo.save_memory.return_value = memory_row

        @asynccontextmanager
        async def _session():
            yield mock_session

        db_manager.session = _session
        db_manager._mock_repo = mock_repo
        db_manager._mock_session = mock_session

    return db_manager


# ── Short-term memory (Redis) ────────────────────────────────────────────────


class TestShortTermMemory:
    """set_short_term / get_short_term operate on Redis with TTL."""

    @pytest.mark.asyncio
    async def test_set_short_term_stores_in_redis(self):
        """set_short_term serialises value and calls redis.set with TTL."""
        redis = _make_redis()
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)
        value = {"score": 0.9, "version": 3}

        await memory.set_short_term("my_key", value, ttl_seconds=600)

        expected_key = "evolution:memory:pjm-agent:my_key"
        redis.set.assert_called_once_with(expected_key, json.dumps(value), ex=600)

    @pytest.mark.asyncio
    async def test_get_short_term_returns_dict(self):
        """get_short_term deserialises JSON stored in Redis."""
        value = {"score": 0.9}
        redis = _make_redis(get_value=json.dumps(value))
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)

        result = await memory.get_short_term("my_key")

        assert result == value
        redis.get.assert_called_once_with("evolution:memory:pjm-agent:my_key")

    @pytest.mark.asyncio
    async def test_get_short_term_returns_none_for_missing_key(self):
        """get_short_term returns None when key is absent (Redis returns None)."""
        redis = _make_redis(get_value=None)
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)

        result = await memory.get_short_term("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_short_term_returns_none_when_redis_down(self):
        """get_short_term returns None gracefully if Redis raises an exception."""
        redis = _make_redis(raise_on_get=True)
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)

        result = await memory.get_short_term("any_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_short_term_silently_fails_when_redis_down(self):
        """set_short_term does not raise even if Redis is unavailable."""
        redis = _make_redis(raise_on_set=True)
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)

        # Must not raise
        await memory.set_short_term("key", {"x": 1})

    @pytest.mark.asyncio
    async def test_set_short_term_uses_default_ttl(self):
        """set_short_term defaults TTL to 3600 seconds."""
        redis = _make_redis()
        memory = AgentMemory(agent_id="pjm-agent", redis=redis)

        await memory.set_short_term("key", {"x": 1})

        _args, kwargs = redis.set.call_args
        assert kwargs.get("ex") == 3600

    @pytest.mark.asyncio
    async def test_set_short_term_noop_when_redis_none(self):
        """set_short_term does nothing when no Redis client is provided."""
        memory = AgentMemory(agent_id="pjm-agent", redis=None)
        # Must not raise
        await memory.set_short_term("key", {"x": 1})

    @pytest.mark.asyncio
    async def test_get_short_term_returns_none_when_redis_none(self):
        """get_short_term returns None when no Redis client is provided."""
        memory = AgentMemory(agent_id="pjm-agent", redis=None)
        result = await memory.get_short_term("key")
        assert result is None


# ── Long-term memory (PostgreSQL) ────────────────────────────────────────────


class TestLongTermMemory:
    """set_long_term / get_long_term operate on PostgreSQL via EvolutionRepository."""

    @pytest.mark.asyncio
    async def test_set_long_term_calls_repo_save_memory(self):
        """set_long_term opens a session and calls repo.save_memory with correct args."""
        db_manager = _make_db_manager()
        memory = AgentMemory(agent_id="pjm-agent", db_manager=db_manager)
        value = {"result": "pass", "score": 1.0}

        with patch.object(agent_memory_module, "EvolutionRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            MockRepo.return_value = mock_repo_instance

            await memory.set_long_term("my_lt_key", value)

            MockRepo.assert_called_once()
            mock_repo_instance.save_memory.assert_called_once_with(
                agent_id="pjm-agent",
                memory_type="long_term",
                key="my_lt_key",
                value=value,
            )

    @pytest.mark.asyncio
    async def test_get_long_term_returns_value_from_repo(self):
        """get_long_term returns the value field of the memory row returned by repo."""
        expected_value = {"optimized": True}
        mock_row = MagicMock()
        mock_row.value = expected_value

        db_manager = _make_db_manager()
        memory = AgentMemory(agent_id="pjm-agent", db_manager=db_manager)

        with patch.object(agent_memory_module, "EvolutionRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_memory.return_value = mock_row
            MockRepo.return_value = mock_repo_instance

            result = await memory.get_long_term("my_lt_key")

        assert result == expected_value

    @pytest.mark.asyncio
    async def test_get_long_term_returns_none_for_missing_key(self):
        """get_long_term returns None when the repository returns no row."""
        db_manager = _make_db_manager()
        memory = AgentMemory(agent_id="pjm-agent", db_manager=db_manager)

        with patch.object(agent_memory_module, "EvolutionRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_memory.return_value = None
            MockRepo.return_value = mock_repo_instance

            result = await memory.get_long_term("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_long_term_noop_when_db_manager_none(self):
        """set_long_term does nothing when no db_manager is provided."""
        memory = AgentMemory(agent_id="pjm-agent", db_manager=None)
        # Must not raise
        await memory.set_long_term("key", {"x": 1})

    @pytest.mark.asyncio
    async def test_get_long_term_returns_none_when_db_manager_none(self):
        """get_long_term returns None when no db_manager is provided."""
        memory = AgentMemory(agent_id="pjm-agent", db_manager=None)
        result = await memory.get_long_term("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_long_term_silently_fails_on_db_error(self):
        """set_long_term does not raise when the repository throws an exception."""
        db_manager = _make_db_manager()
        memory = AgentMemory(agent_id="pjm-agent", db_manager=db_manager)

        with patch.object(agent_memory_module, "EvolutionRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_memory.side_effect = RuntimeError("PG down")
            MockRepo.return_value = mock_repo_instance

            # Must not raise
            await memory.set_long_term("key", {"x": 1})

    @pytest.mark.asyncio
    async def test_get_long_term_returns_none_on_db_error(self):
        """get_long_term returns None when the repository throws an exception."""
        db_manager = _make_db_manager()
        memory = AgentMemory(agent_id="pjm-agent", db_manager=db_manager)

        with patch.object(agent_memory_module, "EvolutionRepository") as MockRepo:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_memory.side_effect = RuntimeError("PG timeout")
            MockRepo.return_value = mock_repo_instance

            result = await memory.get_long_term("key")

        assert result is None


# ── record_optimization ───────────────────────────────────────────────────────


class TestRecordOptimization:
    """record_optimization is a convenience wrapper around set_long_term."""

    @pytest.mark.asyncio
    async def test_record_optimization_calls_set_long_term(self):
        """record_optimization delegates to set_long_term with the structured key."""
        memory = AgentMemory(agent_id="pjm-agent")
        memory.set_long_term = AsyncMock()

        await memory.record_optimization(
            skill_id="decompose",
            version=3,
            success=True,
            details={"improvement": 0.12},
        )

        memory.set_long_term.assert_called_once_with(
            "optimization:decompose:v3",
            {
                "skill_id": "decompose",
                "version": 3,
                "success": True,
                "improvement": 0.12,
            },
        )

    @pytest.mark.asyncio
    async def test_record_optimization_key_format(self):
        """record_optimization key is 'optimization:{skill_id}:v{version}'."""
        memory = AgentMemory(agent_id="pjm-agent")
        captured_keys = []

        async def _capture(key, value):
            captured_keys.append(key)

        memory.set_long_term = _capture

        await memory.record_optimization("scoring", version=7, success=False, details={})
        assert captured_keys == ["optimization:scoring:v7"]

    @pytest.mark.asyncio
    async def test_record_optimization_merges_details(self):
        """record_optimization merges details dict into the stored value."""
        memory = AgentMemory(agent_id="pjm-agent")
        captured_values = []

        async def _capture(key, value):
            captured_values.append(value)

        memory.set_long_term = _capture

        await memory.record_optimization(
            "routing", version=1, success=True, details={"latency_ms": 42, "tokens": 200}
        )
        stored = captured_values[0]
        assert stored["latency_ms"] == 42
        assert stored["tokens"] == 200
        assert stored["skill_id"] == "routing"
        assert stored["version"] == 1
        assert stored["success"] is True


# ── Both backends None ────────────────────────────────────────────────────────


class TestBothBackendsNone:
    """When both redis and db_manager are None, all operations are no-ops / return None."""

    @pytest.mark.asyncio
    async def test_set_short_term_noop(self):
        memory = AgentMemory(agent_id="pjm-agent")
        await memory.set_short_term("k", {"v": 1})  # no raise

    @pytest.mark.asyncio
    async def test_get_short_term_returns_none(self):
        memory = AgentMemory(agent_id="pjm-agent")
        assert await memory.get_short_term("k") is None

    @pytest.mark.asyncio
    async def test_set_long_term_noop(self):
        memory = AgentMemory(agent_id="pjm-agent")
        await memory.set_long_term("k", {"v": 1})  # no raise

    @pytest.mark.asyncio
    async def test_get_long_term_returns_none(self):
        memory = AgentMemory(agent_id="pjm-agent")
        assert await memory.get_long_term("k") is None

    @pytest.mark.asyncio
    async def test_record_optimization_noop(self):
        memory = AgentMemory(agent_id="pjm-agent")
        # set_long_term is a no-op → record_optimization must not raise
        await memory.record_optimization("skill", 1, True, {})


# ── Semantic search (Milvus) ──────────────────────────────────────────────────


def _make_vector_store(search_results=None, raise_on_search=False, raise_on_upsert=False):
    """Return an AsyncMock BaseVectorStore."""
    store = AsyncMock()
    if raise_on_search:
        store.search.side_effect = ConnectionError("Milvus down")
    else:
        store.search.return_value = search_results or []
    if raise_on_upsert:
        store.upsert.side_effect = ConnectionError("Milvus down")
    return store


def _make_embedder(embedding=None):
    """Return a mock TextEmbedder."""
    emb = MagicMock()
    emb.embed.return_value = embedding or [0.1, 0.2, 0.3]
    return emb


class TestSemanticSearch:
    """semantic_search and store_semantic use Milvus vector store."""

    @pytest.mark.asyncio
    async def test_semantic_search_returns_results(self):
        from shared.infra.vector_store import VectorSearchResult

        mock_results = [
            VectorSearchResult(id="pjm-agent:key1", score=0.9, metadata={"k": "v"}, document="text"),
        ]
        vs = _make_vector_store(search_results=mock_results)
        emb = _make_embedder([0.5, 0.6])
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        results = await memory.semantic_search("find something")

        assert len(results) == 1
        assert results[0]["id"] == "pjm-agent:key1"
        assert results[0]["score"] == 0.9
        assert results[0]["value"] == {"k": "v"}
        emb.embed.assert_called_once_with("find something")

    @pytest.mark.asyncio
    async def test_semantic_search_returns_empty_when_no_vector_store(self):
        memory = AgentMemory(agent_id="pjm-agent", vector_store=None)
        results = await memory.semantic_search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_semantic_search_returns_empty_on_error(self):
        vs = _make_vector_store(raise_on_search=True)
        emb = _make_embedder()
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        results = await memory.semantic_search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_store_semantic_upserts_to_vector_store(self):
        vs = _make_vector_store()
        emb = _make_embedder([0.1, 0.2])
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        await memory.store_semantic("my_key", "some text", metadata={"extra": 1})

        vs.upsert.assert_called_once_with(
            collection="evolution_memory",
            id="pjm-agent:my_key",
            embedding=[0.1, 0.2],
            document="some text",
            metadata={"agent_id": "pjm-agent", "key": "my_key", "extra": 1},
        )

    @pytest.mark.asyncio
    async def test_store_semantic_noop_when_no_vector_store(self):
        memory = AgentMemory(agent_id="pjm-agent", vector_store=None)
        # Must not raise
        await memory.store_semantic("key", "text")

    @pytest.mark.asyncio
    async def test_store_semantic_silently_fails_on_error(self):
        vs = _make_vector_store(raise_on_upsert=True)
        emb = _make_embedder()
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        # Must not raise
        await memory.store_semantic("key", "text")

    @pytest.mark.asyncio
    async def test_semantic_search_custom_collection(self):
        vs = _make_vector_store(search_results=[])
        emb = _make_embedder()
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        await memory.semantic_search("query", collection="custom_col", limit=3)

        vs.search.assert_called_once_with("custom_col", emb.embed.return_value, limit=3)

    @pytest.mark.asyncio
    async def test_store_semantic_wraps_embed_in_to_thread(self):
        """Verify embedder.embed is called via asyncio.to_thread (non-blocking)."""
        vs = _make_vector_store()
        emb = _make_embedder([0.1, 0.2])
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        with patch("shared.evolution.agent_memory.asyncio.to_thread", new_callable=AsyncMock) as mock_tt:
            mock_tt.return_value = [0.1, 0.2]
            await memory.store_semantic("k", "text")

        mock_tt.assert_called_once_with(emb.embed, "text")

    @pytest.mark.asyncio
    async def test_semantic_search_wraps_embed_in_to_thread(self):
        """Verify embedder.embed is called via asyncio.to_thread (non-blocking)."""
        vs = _make_vector_store(search_results=[])
        emb = _make_embedder([0.5])
        memory = AgentMemory(agent_id="pjm-agent", vector_store=vs, embedder_instance=emb)

        with patch("shared.evolution.agent_memory.asyncio.to_thread", new_callable=AsyncMock) as mock_tt:
            mock_tt.return_value = [0.5]
            await memory.semantic_search("query")

        mock_tt.assert_called_once_with(emb.embed, "query")
