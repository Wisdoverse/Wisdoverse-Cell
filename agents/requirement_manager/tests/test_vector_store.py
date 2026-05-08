"""Tests for the requirement_manager VectorStore wrapper."""

import importlib
from unittest.mock import AsyncMock, patch

import pytest

from agents.requirement_manager.db.vector_store import VectorStore, _milvus_health_url
from shared.infra.vector_store import VectorDocument

vector_store_module = importlib.import_module("agents.requirement_manager.db.vector_store")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_vs(mock_store: AsyncMock, collection: str = "reqs") -> VectorStore:
    """Create a VectorStore with _available=True (simulates successful init)."""
    vs = VectorStore(store=mock_store, collection=collection)
    vs._available = True
    return vs


@pytest.fixture(autouse=True)
def _stub_to_thread(monkeypatch):
    """Avoid real thread-pool teardown hangs in pytest-asyncio."""

    async def _run_inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(vector_store_module.asyncio, "to_thread", _run_inline)


# ── _milvus_health_url ────────────────────────────────────────────────────────


class TestMilvusHealthUrl:
    def test_standard_uri(self):
        assert _milvus_health_url("http://milvus:19530") == "http://milvus:9091"

    def test_nonstandard_port(self):
        assert _milvus_health_url("http://milvus:29530") == "http://milvus:9091"

    def test_https_scheme(self):
        assert _milvus_health_url("https://milvus.prod:19530") == "https://milvus.prod:9091"

    def test_uri_with_path_strips_path(self):
        result = _milvus_health_url("http://milvus:19530/some/path")
        assert result == "http://milvus:9091"

    def test_localhost(self):
        assert _milvus_health_url("http://localhost:19530") == "http://localhost:9091"


# ── VectorStore.get_stats URI sanitization ────────────────────────────────────


class TestVectorStoreGetStats:
    @pytest.mark.asyncio
    async def test_get_stats_sanitizes_uri(self):
        mock_store = AsyncMock()
        mock_store.count.return_value = 42

        vs = _make_vs(mock_store, collection="test_col")

        with patch("agents.requirement_manager.db.vector_store.settings") as mock_settings:
            mock_settings.milvus_uri = "http://milvus-host:19530"
            stats = await vs.get_stats()

        assert stats["uri"] == "milvus-host:19530"
        assert stats["total_documents"] == 42
        assert stats["collection"] == "test_col"
        assert "milvus_token" not in str(stats)

    @pytest.mark.asyncio
    async def test_get_stats_does_not_leak_token_in_uri(self):
        mock_store = AsyncMock()
        mock_store.count.return_value = 10

        vs = _make_vs(mock_store)

        with patch("agents.requirement_manager.db.vector_store.settings") as mock_settings:
            mock_settings.milvus_uri = "http://user:secret@milvus:19530"
            stats = await vs.get_stats()

        assert "secret" not in stats["uri"]
        assert stats["uri"] == "milvus:19530"

    @pytest.mark.asyncio
    async def test_get_stats_unavailable(self):
        vs = VectorStore(store=AsyncMock())
        stats = await vs.get_stats()
        assert stats["status"] == "unavailable"
        assert stats["total_documents"] == 0


# ── VectorStore.find_similar via abstraction ──────────────────────────────────


class TestVectorStoreFindSimilar:
    @pytest.mark.asyncio
    async def test_find_similar_uses_get_by_ids(self):
        """Verify find_similar goes through BaseVectorStore.get_by_ids, not _client."""
        mock_store = AsyncMock()
        mock_store.get_by_ids.return_value = [
            VectorDocument(
                id="req-1",
                document="需求: test\n描述: a requirement",
                metadata={"title": "test"},
            )
        ]
        mock_store.search.return_value = []

        vs = _make_vs(mock_store)

        with patch("agents.requirement_manager.db.vector_store.shared_embedder") as mock_emb:
            mock_emb.embed.return_value = [0.1, 0.2, 0.3]
            result = await vs.find_similar("req-1")

        mock_store.get_by_ids.assert_called_once_with(
            collection="reqs",
            ids=["req-1"],
            output_fields=["document", "metadata"],
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_find_similar_returns_empty_for_missing_id(self):
        mock_store = AsyncMock()
        mock_store.get_by_ids.return_value = []

        vs = _make_vs(mock_store)
        result = await vs.find_similar("nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_find_similar_returns_empty_when_unavailable(self):
        vs = VectorStore(store=AsyncMock())
        result = await vs.find_similar("any-id")
        assert result == []


# ── VectorStore.search category filter sanitization ──────────────────────────


class TestVectorStoreSearchSanitization:
    @pytest.mark.asyncio
    async def test_category_filter_strips_quotes(self):
        mock_store = AsyncMock()
        mock_store.search.return_value = []

        vs = _make_vs(mock_store)

        with patch("agents.requirement_manager.db.vector_store.shared_embedder") as mock_emb:
            mock_emb.embed.return_value = [0.1]
            await vs.search("test", category_filter='test"injection')

        call_kwargs = mock_store.search.call_args
        filter_expr = call_kwargs.kwargs.get("filter_expr") or call_kwargs[1].get("filter_expr")
        assert '"' not in filter_expr.split("==")[1].replace('"testinjection"', "")
        assert "injection" in filter_expr

    @pytest.mark.asyncio
    async def test_category_filter_strips_backslash(self):
        mock_store = AsyncMock()
        mock_store.search.return_value = []

        vs = _make_vs(mock_store)

        with patch("agents.requirement_manager.db.vector_store.shared_embedder") as mock_emb:
            mock_emb.embed.return_value = [0.1]
            await vs.search("test", category_filter='cat\\"; evil')

        call_kwargs = mock_store.search.call_args
        filter_expr = call_kwargs.kwargs.get("filter_expr") or call_kwargs[1].get("filter_expr")
        assert "\\" not in filter_expr
        assert "evil" in filter_expr

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_unavailable(self):
        vs = VectorStore(store=AsyncMock())
        result = await vs.search("any query")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_logs_query_length_not_query_text(self):
        mock_store = AsyncMock()
        mock_store.search.return_value = []

        vs = _make_vs(mock_store)

        with (
            patch("agents.requirement_manager.db.vector_store.shared_embedder") as mock_emb,
            patch("agents.requirement_manager.db.vector_store.logger") as mock_logger,
        ):
            mock_emb.embed.return_value = [0.1]
            await vs.search("sensitive search text")

        log_kwargs = mock_logger.debug.call_args.kwargs
        assert "query" not in log_kwargs
        assert log_kwargs["query_length"] == len("sensitive search text")
