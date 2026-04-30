"""Milvus vector store implementation.

Uses ``pymilvus.MilvusClient`` (lightweight SDK, no separate gRPC dep).
The client is synchronous, so all I/O calls are wrapped in
``asyncio.to_thread`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from shared.utils.logger import get_logger

from .vector_store import BaseVectorStore, VectorDocument, VectorSearchResult

if TYPE_CHECKING:
    from pymilvus import MilvusClient

logger = get_logger("infra.milvus")


class MilvusVectorStore(BaseVectorStore):
    """Milvus-backed vector store."""

    # Connection timeout in seconds — prevents indefinite blocking if Milvus is slow to start.
    DEFAULT_TIMEOUT = 10

    def __init__(
        self,
        uri: str = "http://localhost:19530",
        token: str = "",
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self._uri = uri
        self._token = token
        self._timeout = timeout
        self._client: MilvusClient | None = None

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _require_client(self) -> MilvusClient:
        """Return the initialised client or raise."""
        if self._client is None:
            raise RuntimeError("MilvusVectorStore not initialized — call initialize() first")
        return self._client

    def _safe_uri(self) -> str:
        """Return the configured URI without embedded credentials."""
        parsed = urlparse(self._uri)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        scheme = parsed.scheme or "http"
        return f"{scheme}://{host}{port}"

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        if self._client is not None:
            logger.warning("milvus_already_initialized", uri=self._safe_uri())
            await self.close()

        from pymilvus import MilvusClient as _MilvusClient

        try:
            self._client = await asyncio.to_thread(
                _MilvusClient, uri=self._uri, token=self._token, timeout=self._timeout
            )
        except Exception as exc:
            logger.error(
                "milvus_connection_failed",
                uri=self._safe_uri(),
                error_type=type(exc).__name__,
            )
            raise
        logger.info("milvus_client_initialized", uri=self._safe_uri())

    async def close(self) -> None:
        if self._client is not None:
            try:
                await asyncio.to_thread(self._client.close)
            except Exception as exc:
                logger.warning(
                    "milvus_close_failed",
                    error_type=type(exc).__name__,
                    uri=self._safe_uri(),
                )
            self._client = None

    # ── Collection management ──────────────────────────────────────────────────

    async def ensure_collection(self, collection: str, dimension: int = 384) -> None:
        client = self._require_client()

        from pymilvus import DataType

        has = await asyncio.to_thread(client.has_collection, collection)
        if has:
            return

        schema = await asyncio.to_thread(client.create_schema, auto_id=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("document", DataType.VARCHAR, max_length=65535)
        schema.add_field("metadata", DataType.JSON)

        index_params = await asyncio.to_thread(client.prepare_index_params)
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            params={"nlist": 128},
        )

        try:
            await asyncio.to_thread(
                client.create_collection,
                collection_name=collection,
                schema=schema,
                index_params=index_params,
            )
        except Exception:
            # Another replica may have created the collection after our initial
            # existence check but before create_collection() executed.
            if await asyncio.to_thread(client.has_collection, collection):
                logger.info(
                    "milvus_collection_create_race_won_elsewhere",
                    collection=collection,
                )
                return
            raise
        logger.info("milvus_collection_created", collection=collection, dimension=dimension)

    # ── CRUD ───────────────────────────────────────────────────────────────────

    async def upsert(
        self,
        collection: str,
        id: str,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        client = self._require_client()
        data = [
            {"id": id, "embedding": embedding, "document": document, "metadata": metadata}
        ]
        await asyncio.to_thread(client.upsert, collection_name=collection, data=data)

    async def _do_upsert_batch(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        client = self._require_client()
        data = [
            {
                "id": ids[i],
                "embedding": embeddings[i],
                "document": documents[i],
                "metadata": metadatas[i],
            }
            for i in range(len(ids))
        ]
        await asyncio.to_thread(client.upsert, collection_name=collection, data=data)

    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 10,
        filter_expr: str | None = None,
    ) -> list[VectorSearchResult]:
        client = self._require_client()
        kwargs: dict[str, Any] = {
            "collection_name": collection,
            "data": [query_embedding],
            "limit": limit,
            "output_fields": ["document", "metadata"],
        }
        if filter_expr:
            kwargs["filter"] = filter_expr

        raw = await asyncio.to_thread(lambda: client.search(**kwargs))
        results: list[VectorSearchResult] = []
        if raw and len(raw) > 0:
            for hit in raw[0]:
                results.append(
                    VectorSearchResult(
                        id=hit["id"],
                        score=hit["distance"],
                        metadata=hit["entity"].get("metadata", {}),
                        document=hit["entity"].get("document", ""),
                    )
                )
        return results

    async def delete(self, collection: str, ids: list[str]) -> None:
        client = self._require_client()
        if not ids:
            return
        await asyncio.to_thread(client.delete, collection_name=collection, ids=ids)

    async def count(self, collection: str) -> int:
        client = self._require_client()
        stats = await asyncio.to_thread(
            client.get_collection_stats, collection_name=collection
        )
        return stats.get("row_count", 0)

    async def get_by_ids(
        self,
        collection: str,
        ids: list[str],
        output_fields: list[str] | None = None,
    ) -> list[VectorDocument]:
        client = self._require_client()
        fields = output_fields or ["document", "metadata"]
        rows = await asyncio.to_thread(
            client.get,
            collection_name=collection,
            ids=ids,
            output_fields=fields,
        )
        if not rows:
            return []
        return [
            VectorDocument(
                id=row.get("id", ""),
                document=row.get("document", ""),
                metadata=dict(row.get("metadata", {})),
            )
            for row in rows
        ]
