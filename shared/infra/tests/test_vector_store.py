"""Tests for the shared vector store abstraction and MilvusVectorStore."""

from unittest.mock import MagicMock, patch

import pytest

from shared.infra.milvus_store import MilvusVectorStore
from shared.infra.vector_store import BaseVectorStore, VectorDocument, VectorSearchResult

# ── VectorSearchResult ────────────────────────────────────────────────────────


class TestVectorSearchResult:
    def test_default_values(self):
        r = VectorSearchResult(id="abc", score=0.9)
        assert r.id == "abc"
        assert r.score == 0.9
        assert r.metadata == {}
        assert r.document == ""

    def test_full_construction(self):
        r = VectorSearchResult(
            id="req-1", score=0.85, metadata={"title": "Test"}, document="hello"
        )
        assert r.metadata["title"] == "Test"
        assert r.document == "hello"

    def test_frozen_immutability(self):
        r = VectorSearchResult(id="abc", score=0.9)
        with pytest.raises(AttributeError):
            r.score = 0.5  # type: ignore[misc]


class TestVectorDocument:
    def test_defaults(self):
        d = VectorDocument(id="x")
        assert d.document == ""
        assert d.metadata == {}

    def test_frozen(self):
        d = VectorDocument(id="x", document="hi")
        with pytest.raises(AttributeError):
            d.document = "bye"  # type: ignore[misc]


# ── BaseVectorStore is abstract ───────────────────────────────────────────────


class TestBaseVectorStoreAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseVectorStore()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_upsert_batch_validates_length_in_base_class(self):
        """Length validation is in BaseVectorStore, not just MilvusVectorStore."""
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with pytest.raises(ValueError, match="Length mismatch"):
            await store.upsert_batch(
                collection="test",
                ids=["a"],
                embeddings=[[0.1], [0.2]],
                documents=["d"],
                metadatas=[{}],
            )


# ── MilvusVectorStore with mocked client ──────────────────────────────────────


def _mock_milvus_client():
    """Return a MagicMock that behaves like MilvusClient."""
    client = MagicMock()
    client.has_collection.return_value = False
    client.create_schema.return_value = MagicMock()
    client.prepare_index_params.return_value = MagicMock()
    client.create_collection.return_value = None
    client.upsert.return_value = None
    client.delete.return_value = None
    client.get_collection_stats.return_value = {"row_count": 42}
    client.search.return_value = [
        [
            {
                "id": "doc-1",
                "distance": 0.95,
                "entity": {"document": "hello world", "metadata": {"key": "val"}},
            }
        ]
    ]
    client.get.return_value = [
        {"id": "doc-1", "document": "hello world", "metadata": {"key": "val"}}
    ]
    client.close.return_value = None
    return client


class TestMilvusVectorStoreInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_client(self):
        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_client = _mock_milvus_client()
            mock_to_thread.return_value = mock_client

            store = MilvusVectorStore(uri="http://test:19530")
            await store.initialize()

            assert store._client is mock_client

    @pytest.mark.asyncio
    async def test_close_calls_client_close(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = None
            await store.close()

        assert store._client is None

    @pytest.mark.asyncio
    async def test_close_logs_on_exception(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = ConnectionError("network down")
            await store.close()

        assert store._client is None

    @pytest.mark.asyncio
    async def test_double_initialize_closes_first(self):
        store = MilvusVectorStore()
        first_client = _mock_milvus_client()
        store._client = first_client

        second_client = _mock_milvus_client()

        call_count = 0

        async def mock_to_thread_fn(fn, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # close() on first client
                return None
            # MilvusClient() constructor
            return second_client

        with patch("shared.infra.milvus_store.asyncio.to_thread", side_effect=mock_to_thread_fn):
            await store.initialize()

        assert store._client is second_client
        assert call_count == 2


class TestMilvusVectorStoreSafeUri:
    def test_safe_uri_strips_credentials(self):
        store = MilvusVectorStore(uri="http://user:secret@milvus:19530")
        assert store._safe_uri() == "http://milvus:19530"


class TestMilvusVectorStoreEnsureCollection:
    @pytest.mark.asyncio
    async def test_creates_collection_when_not_exists(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        client.has_collection.return_value = False
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            # has_collection -> False, create_schema, prepare_index_params, create_collection
            mock_to_thread.side_effect = [False, MagicMock(), MagicMock(), None]
            await store.ensure_collection("test_col", dimension=384)

        assert mock_to_thread.call_count == 4

    @pytest.mark.asyncio
    async def test_skips_creation_when_exists(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = True  # has_collection -> True
            await store.ensure_collection("test_col")

        # Only has_collection call, no create_collection
        assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def test_treats_already_exists_race_as_success(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = [
                False,
                MagicMock(),
                MagicMock(),
                RuntimeError("collection already exists"),
                True,
            ]

            await store.ensure_collection("test_col", dimension=384)

        assert mock_to_thread.call_count == 5


class TestMilvusVectorStoreUpsert:
    @pytest.mark.asyncio
    async def test_upsert_single(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = None
            await store.upsert(
                collection="test",
                id="doc-1",
                embedding=[0.1, 0.2],
                document="test doc",
                metadata={"key": "val"},
            )

        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_batch(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = None
            await store.upsert_batch(
                collection="test",
                ids=["a", "b"],
                embeddings=[[0.1], [0.2]],
                documents=["doc a", "doc b"],
                metadatas=[{"k": 1}, {"k": 2}],
            )

        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_batch_length_mismatch_raises(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with pytest.raises(ValueError, match="Length mismatch"):
            await store.upsert_batch(
                collection="test",
                ids=["a", "b", "c"],
                embeddings=[[0.1], [0.2]],
                documents=["doc a", "doc b"],
                metadatas=[{"k": 1}, {"k": 2}],
            )


class TestMilvusVectorStoreSearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [
                [
                    {
                        "id": "doc-1",
                        "distance": 0.95,
                        "entity": {
                            "document": "hello",
                            "metadata": {"title": "Test"},
                        },
                    },
                    {
                        "id": "doc-2",
                        "distance": 0.8,
                        "entity": {"document": "world", "metadata": {}},
                    },
                ]
            ]
            results = await store.search("test", [0.1, 0.2], limit=5)

        assert len(results) == 2
        assert results[0].id == "doc-1"
        assert results[0].score == 0.95
        assert results[0].document == "hello"
        assert results[0].metadata == {"title": "Test"}
        assert results[1].id == "doc-2"

    @pytest.mark.asyncio
    async def test_search_with_filter(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [[]]
            await store.search(
                "test", [0.1], limit=3, filter_expr='metadata["cat"] == "A"'
            )

        # Verify the lambda was called (search kwargs include filter)
        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_empty_results(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [[]]
            results = await store.search("test", [0.1])

        assert results == []


class TestMilvusVectorStoreDelete:
    @pytest.mark.asyncio
    async def test_delete_calls_client(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = None
            await store.delete("test", ["id-1", "id-2"])

        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_empty_ids_is_noop(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            await store.delete("test", [])

        mock_to_thread.assert_not_called()


class TestMilvusVectorStoreCount:
    @pytest.mark.asyncio
    async def test_count_returns_row_count(self):
        store = MilvusVectorStore()
        client = _mock_milvus_client()
        store._client = client

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {"row_count": 42}
            count = await store.count("test")

        assert count == 42


class TestMilvusVectorStoreGetByIds:
    @pytest.mark.asyncio
    async def test_get_by_ids_returns_vector_documents(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [
                {"id": "doc-1", "document": "hello", "metadata": {"k": "v"}}
            ]
            rows = await store.get_by_ids("test", ["doc-1"])

        assert len(rows) == 1
        assert isinstance(rows[0], VectorDocument)
        assert rows[0].id == "doc-1"
        assert rows[0].document == "hello"
        assert rows[0].metadata == {"k": "v"}

    @pytest.mark.asyncio
    async def test_get_by_ids_empty_result(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = None
            rows = await store.get_by_ids("test", ["nonexistent"])

        assert rows == []

    @pytest.mark.asyncio
    async def test_get_by_ids_custom_fields(self):
        store = MilvusVectorStore()
        store._client = _mock_milvus_client()

        with patch("shared.infra.milvus_store.asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = [{"id": "doc-1", "document": "hi"}]
            rows = await store.get_by_ids("test", ["doc-1"], output_fields=["document"])

        assert len(rows) == 1
        assert rows[0].document == "hi"
        mock_to_thread.assert_called_once()


class TestMilvusVectorStoreLifecycleGuards:
    @pytest.mark.asyncio
    async def test_upsert_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.upsert("col", "id", [0.1], "doc", {})

    @pytest.mark.asyncio
    async def test_search_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.search("col", [0.1])

    @pytest.mark.asyncio
    async def test_delete_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.delete("col", ["id"])

    @pytest.mark.asyncio
    async def test_count_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.count("col")

    @pytest.mark.asyncio
    async def test_get_by_ids_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.get_by_ids("col", ["id"])

    @pytest.mark.asyncio
    async def test_ensure_collection_fails_without_init(self):
        store = MilvusVectorStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.ensure_collection("col", dimension=384)
