"""Tests for VectorStorePlugin — full coverage with mock store + embedder."""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import shared.app.plugins.vector_store as vector_store_mod
from shared.app.plugins.vector_store import (
    VectorCollection,
    VectorStorePlugin,
    VectorUpsertItem,
)
from shared.infra.circuit_breaker import CircuitState
from shared.infra.vector_store import VectorDocument, VectorSearchResult

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_plugin(**overrides):
    """Helper: plugin with mock store + embedder."""
    store = AsyncMock()
    store.initialize = AsyncMock()
    store.close = AsyncMock()
    store.ensure_collection = AsyncMock()
    store.search = AsyncMock(return_value=[])
    store.upsert = AsyncMock()
    store.upsert_batch = AsyncMock()
    store.delete = AsyncMock()
    store.count = AsyncMock(return_value=0)
    store.get_by_ids = AsyncMock(return_value=[])
    emb = MagicMock()
    emb.embed = MagicMock(return_value=[0.1] * 384)
    emb.embed_batch = MagicMock(return_value=[[0.1] * 384])
    emb.dimension = 384
    defaults = dict(
        collections={"test_col": VectorCollection(description="test")},
        store=store,
        embedder_instance=emb,
    )
    defaults.update(overrides)
    return VectorStorePlugin(**defaults), store, emb


def _make_runtime():
    """Helper: minimal mock runtime."""
    rt = MagicMock()
    rt.agent_id = "test-agent"
    return rt


@pytest.fixture(autouse=True)
def _stub_to_thread(monkeypatch):
    """Avoid real thread-pool teardown hangs in pytest-asyncio."""

    async def _run_inline(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(vector_store_mod.asyncio, "to_thread", _run_inline)


# ── TestVectorCollection ──────────────────────────────────────────────────


class TestVectorCollection:
    def test_defaults(self):
        col = VectorCollection()
        assert col.description == ""
        assert col.dimension == 384

    def test_custom(self):
        col = VectorCollection(description="my desc", dimension=768)
        assert col.description == "my desc"
        assert col.dimension == 768

    def test_frozen(self):
        col = VectorCollection()
        with pytest.raises(FrozenInstanceError):
            col.description = "changed"  # type: ignore[misc]


# ── TestVectorUpsertItem ──────────────────────────────────────────────────


class TestVectorUpsertItem:
    def test_fields(self):
        item = VectorUpsertItem(id="doc1", text="hello", metadata={"k": "v"})
        assert item.id == "doc1"
        assert item.text == "hello"
        assert item.metadata == {"k": "v"}

    def test_default_metadata(self):
        item = VectorUpsertItem(id="doc1", text="hello")
        assert item.metadata == {}


# ── TestPluginConstructor ─────────────────────────────────────────────────


class TestPluginConstructor:
    def test_string_normalization(self):
        plugin, _, _ = _make_plugin(
            collections={"my_col": "a description"}
        )
        assert "my_col" in plugin._collections
        assert plugin._collections["my_col"].description == "a description"

    def test_empty_collections_error(self):
        with pytest.raises(ValueError, match="must not be empty"):
            VectorStorePlugin(collections={})

    def test_bad_dimension_error(self):
        with pytest.raises(ValueError, match="non-positive dimension"):
            VectorStorePlugin(
                collections={"test": VectorCollection(dimension=0)}
            )

    def test_invalid_name_error(self):
        with pytest.raises(ValueError, match="Invalid collection name"):
            VectorStorePlugin(collections={"Bad-Name": VectorCollection()})

    def test_invalid_name_starts_with_number(self):
        with pytest.raises(ValueError, match="Invalid collection name"):
            VectorStorePlugin(collections={"1col": VectorCollection()})

    def test_disabled_plugin(self):
        plugin, _, _ = _make_plugin(enabled=False)
        assert not plugin.available

    def test_plugin_name(self):
        plugin, _, _ = _make_plugin()
        assert plugin.name == "vector-store"


# ── TestStartup ───────────────────────────────────────────────────────────


class TestStartup:
    @pytest.mark.asyncio
    async def test_successful_startup(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()

        await plugin.startup(rt)

        assert plugin.available is True
        store.initialize.assert_awaited_once()
        store.ensure_collection.assert_awaited_once_with("test_col", 384)

    @pytest.mark.asyncio
    async def test_milvus_down_degrades(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()

        await plugin.startup(rt)  # Should NOT raise

        assert plugin.available is False

    @pytest.mark.asyncio
    async def test_disabled_skips(self):
        plugin, store, _ = _make_plugin(enabled=False)
        rt = _make_runtime()

        await plugin.startup(rt)

        store.initialize.assert_not_awaited()
        assert plugin.available is False

    @pytest.mark.asyncio
    async def test_recovers_lazily_after_failed_startup(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = [ConnectionError("refused"), None]
        rt = _make_runtime()

        await plugin.startup(rt)

        assert plugin.available is False

        await plugin.search_text("test_col", "query")

        assert plugin.available is True
        assert store.initialize.await_count == 2


# ── TestShutdown ──────────────────────────────────────────────────────────


class TestShutdown:
    @pytest.mark.asyncio
    async def test_closes_store(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.shutdown(rt)

        store.close.assert_awaited_once()
        assert plugin.available is False

    @pytest.mark.asyncio
    async def test_tolerates_close_failure(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        store.close.side_effect = RuntimeError("close failed")

        await plugin.shutdown(rt)  # Should NOT raise

        assert plugin.available is False


# ── TestHealthCheck ───────────────────────────────────────────────────────


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_healthy(self):
        plugin, _, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        health = await plugin.health_check()

        assert health["client"].status == "ok"
        assert health["circuit_breaker"].status == "ok"

    @pytest.mark.asyncio
    async def test_unavailable_optional_degraded(self):
        plugin, store, _ = _make_plugin(required=False)
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        health = await plugin.health_check()

        assert health["client"].status == "degraded"

    @pytest.mark.asyncio
    async def test_unavailable_required_down(self):
        plugin, store, _ = _make_plugin(required=True)
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        health = await plugin.health_check()

        assert health["client"].status == "down"

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        plugin, _, _ = _make_plugin(enabled=False)

        health = await plugin.health_check()

        assert health == {}

    @pytest.mark.asyncio
    async def test_includes_collections_status(self):
        plugin, _, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        health = await plugin.health_check()

        assert health["collections"].status == "ok"


# ── TestSearchText ────────────────────────────────────────────────────────


class TestSearchText:
    @pytest.mark.asyncio
    async def test_returns_results(self):
        plugin, store, emb = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        expected = [VectorSearchResult(id="doc1", score=0.9, document="hello")]
        store.search.return_value = expected

        results = await plugin.search_text("test_col", "query text")

        assert results == expected
        emb.embed.assert_called_once_with("query text")
        store.search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        results = await plugin.search_text("test_col", "query")

        assert results == []

    @pytest.mark.asyncio
    async def test_strict_raises_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        with pytest.raises(RuntimeError, match="not available"):
            await plugin.search_text("test_col", "query", strict=True)

    @pytest.mark.asyncio
    async def test_validates_collection(self):
        plugin, _, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        with pytest.raises(ValueError, match="Unknown collection"):
            await plugin.search_text("nonexistent", "query")

    @pytest.mark.asyncio
    async def test_metadata_filters_compile(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.search_text(
            "test_col", "query", metadata_filters={"cat": "login"}
        )

        call_kwargs = store.search.call_args
        assert call_kwargs.kwargs.get("filter_expr") == 'metadata["cat"] == "login"'

    @pytest.mark.asyncio
    async def test_metadata_filters_int_value(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.search_text(
            "test_col", "query", metadata_filters={"priority": 5}
        )

        call_kwargs = store.search.call_args
        assert call_kwargs.kwargs.get("filter_expr") == 'metadata["priority"] == 5'

    @pytest.mark.asyncio
    async def test_metadata_filters_bool_value(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.search_text(
            "test_col", "query", metadata_filters={"active": True}
        )

        call_kwargs = store.search.call_args
        assert call_kwargs.kwargs.get("filter_expr") == 'metadata["active"] == true'

    @pytest.mark.asyncio
    async def test_metadata_filters_escape_quotes(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.search_text(
            "test_col", "query", metadata_filters={"name": 'he said "hi"'}
        )

        call_kwargs = store.search.call_args
        assert (
            call_kwargs.kwargs.get("filter_expr")
            == 'metadata["name"] == "he said \\"hi\\""'
        )

    @pytest.mark.asyncio
    async def test_metadata_filters_escape_backslashes(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.search_text(
            "test_col", "query", metadata_filters={"path": r"folder\name"}
        )

        call_kwargs = store.search.call_args
        assert (
            call_kwargs.kwargs.get("filter_expr")
            == 'metadata["path"] == "folder\\\\name"'
        )

    @pytest.mark.asyncio
    async def test_metadata_filters_reject_invalid_keys(self):
        plugin, _, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        with pytest.raises(ValueError, match="Invalid metadata filter key"):
            await plugin.search_text(
                "test_col",
                "query",
                metadata_filters={'bad"] == true or metadata["other': "x"},
            )

    @pytest.mark.asyncio
    async def test_min_score_filters_results(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        store.search.return_value = [
            VectorSearchResult(id="doc1", score=0.9),
            VectorSearchResult(id="doc2", score=0.3),
        ]

        results = await plugin.search_text("test_col", "query", min_score=0.5)

        assert len(results) == 1
        assert results[0].id == "doc1"

    @pytest.mark.asyncio
    async def test_error_records_breaker_failure(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        store.search.side_effect = RuntimeError("boom")

        results = await plugin.search_text("test_col", "query")

        assert results == []
        assert plugin._breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_embed_failure_degrades(self):
        plugin, _, emb = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        emb.embed.side_effect = RuntimeError("embed failed")

        results = await plugin.search_text("test_col", "query")

        assert results == []

    @pytest.mark.asyncio
    async def test_retries_transient_search_failures(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        expected = [VectorSearchResult(id="doc1", score=0.9)]
        store.search.side_effect = [
            ConnectionError("temporary-1"),
            ConnectionError("temporary-2"),
            expected,
        ]

        sleep_path = "shared.app.plugins.vector_store.asyncio.sleep"
        with patch(sleep_path, new_callable=AsyncMock) as mock_sleep:
            results = await plugin.search_text("test_col", "query")

        assert results == expected
        assert store.search.await_count == 3
        assert mock_sleep.await_count == 2


# ── TestUpsertText ────────────────────────────────────────────────────────


class TestUpsertText:
    @pytest.mark.asyncio
    async def test_upserts(self):
        plugin, store, emb = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.upsert_text("test_col", "doc1", "hello world")

        assert result is True
        emb.embed.assert_called_once_with("hello world")
        store.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_false_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.upsert_text("test_col", "doc1", "text")

        assert result is False

    @pytest.mark.asyncio
    async def test_with_metadata(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        await plugin.upsert_text("test_col", "doc1", "text", {"key": "val"})

        call_args = store.upsert.call_args
        assert call_args.args[3] == "text"
        assert call_args.args[4] == {"key": "val"}


# ── TestUpsertBatch ───────────────────────────────────────────────────────


class TestUpsertBatch:
    @pytest.mark.asyncio
    async def test_batch_upsert(self):
        plugin, store, emb = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        items = [
            VectorUpsertItem(id="d1", text="hello"),
            VectorUpsertItem(id="d2", text="world"),
        ]
        emb.embed_batch.return_value = [[0.1] * 384, [0.2] * 384]

        count = await plugin.upsert_batch_text("test_col", items)

        assert count == 2
        store.upsert_batch.assert_awaited_once()
        emb.embed_batch.assert_called_once_with(["hello", "world"])

    @pytest.mark.asyncio
    async def test_returns_zero_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        count = await plugin.upsert_batch_text("test_col", [])

        assert count == 0

    @pytest.mark.asyncio
    async def test_empty_items_returns_zero(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        count = await plugin.upsert_batch_text("test_col", [])

        assert count == 0
        store.upsert_batch.assert_not_awaited()


# ── TestSearchById ────────────────────────────────────────────────────────


class TestSearchById:
    @pytest.mark.asyncio
    async def test_fetches_doc_then_searches(self):
        plugin, store, emb = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        store.get_by_ids.return_value = [
            VectorDocument(id="doc1", document="hello world")
        ]
        store.search.return_value = [
            VectorSearchResult(id="doc1", score=1.0),
            VectorSearchResult(id="doc2", score=0.8),
        ]

        results = await plugin.search_by_id("test_col", "doc1")

        store.get_by_ids.assert_awaited_once_with("test_col", ["doc1"])
        emb.embed.assert_called_once_with("hello world")
        # Default: exclude self
        assert len(results) == 1
        assert results[0].id == "doc2"

    @pytest.mark.asyncio
    async def test_include_self(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        store.get_by_ids.return_value = [
            VectorDocument(id="doc1", document="hello")
        ]
        store.search.return_value = [
            VectorSearchResult(id="doc1", score=1.0),
            VectorSearchResult(id="doc2", score=0.8),
        ]

        results = await plugin.search_by_id(
            "test_col", "doc1", include_self=True
        )

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_doc_not_found_returns_empty(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        store.get_by_ids.return_value = []

        results = await plugin.search_by_id("test_col", "missing")

        assert results == []


# ── TestGetByIds ──────────────────────────────────────────────────────────


class TestGetByIds:
    @pytest.mark.asyncio
    async def test_returns_docs(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        expected = [VectorDocument(id="doc1", document="hello")]
        store.get_by_ids.return_value = expected

        results = await plugin.get_by_ids("test_col", ["doc1"])

        assert results == expected

    @pytest.mark.asyncio
    async def test_empty_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        results = await plugin.get_by_ids("test_col", ["doc1"])

        assert results == []


# ── TestDelete ────────────────────────────────────────────────────────────


class TestDelete:
    @pytest.mark.asyncio
    async def test_single_delete(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.delete("test_col", "doc1")

        assert result is True
        store.delete.assert_awaited_once_with("test_col", ["doc1"])

    @pytest.mark.asyncio
    async def test_delete_many(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.delete_many("test_col", ["doc1", "doc2"])

        assert result == 2
        store.delete.assert_awaited_once_with("test_col", ["doc1", "doc2"])

    @pytest.mark.asyncio
    async def test_delete_returns_false_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.delete("test_col", "doc1")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_many_empty_list(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.delete_many("test_col", [])

        assert result == 0
        store.delete.assert_not_awaited()


# ── TestCount ─────────────────────────────────────────────────────────────


class TestCount:
    @pytest.mark.asyncio
    async def test_count(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        store.count.return_value = 42

        result = await plugin.count("test_col")

        assert result == 42

    @pytest.mark.asyncio
    async def test_returns_zero_when_unavailable(self):
        plugin, store, _ = _make_plugin()
        store.initialize.side_effect = ConnectionError("refused")
        rt = _make_runtime()
        await plugin.startup(rt)

        result = await plugin.count("test_col")

        assert result == 0


# ── TestMetrics ────────────────────────────────────────────────────────────


class TestMetrics:
    @pytest.mark.asyncio
    async def test_available_gauge_tracks_lifecycle(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        store.count.return_value = 7

        await plugin.startup(rt)
        assert vector_store_mod.VECTOR_STORE_AVAILABLE._value.get() == 1

        await plugin.shutdown(rt)
        assert vector_store_mod.VECTOR_STORE_AVAILABLE._value.get() == 0

    @pytest.mark.asyncio
    async def test_successful_search_increments_operations_metric(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        counter = vector_store_mod.VECTOR_STORE_OPERATIONS.labels(
            collection="test_col",
            operation="search_text",
            status="success",
        )
        before = counter._value.get()

        await plugin.search_text("test_col", "query")

        assert counter._value.get() == before + 1

    @pytest.mark.asyncio
    async def test_open_breaker_increments_degraded_and_open_metrics(self):
        plugin, _, _ = _make_plugin()
        rt = _make_runtime()
        await plugin.startup(rt)
        plugin._breaker._state = CircuitState.OPEN
        plugin._breaker._last_failure_time = time.time()

        degraded_counter = vector_store_mod.VECTOR_STORE_OPERATIONS.labels(
            collection="test_col",
            operation="search_text",
            status="degraded",
        )
        degraded_before = degraded_counter._value.get()
        open_before = vector_store_mod.VECTOR_STORE_CIRCUIT_BREAKER_OPEN_TOTAL._value.get()

        results = await plugin.search_text("test_col", "query")

        assert results == []
        assert degraded_counter._value.get() == degraded_before + 1
        breaker_total = vector_store_mod.VECTOR_STORE_CIRCUIT_BREAKER_OPEN_TOTAL
        assert breaker_total._value.get() == open_before + 1

    @pytest.mark.asyncio
    async def test_count_updates_document_gauge(self):
        plugin, store, _ = _make_plugin()
        rt = _make_runtime()
        store.count.return_value = 42

        await plugin.startup(rt)
        result = await plugin.count("test_col")

        assert result == 42
        docs_gauge = vector_store_mod.VECTOR_STORE_DOCUMENTS.labels(collection="test_col")
        assert docs_gauge._value.get() == 42
