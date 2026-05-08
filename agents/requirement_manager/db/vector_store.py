"""Milvus-backed vector store operations.

Provides semantic search and similarity queries for requirements.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

from shared.config import settings
from shared.infra.embedder import embedder as shared_embedder
from shared.infra.milvus_store import MilvusVectorStore
from shared.infra.vector_store import BaseVectorStore
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from ..core.embedder import embedder

if TYPE_CHECKING:
    from shared.app.plugins.vector_store import VectorStorePlugin

logger = get_logger("vector_store")

# Collection-name constants.
COLLECTION_REQUIREMENTS = "requirements"


def _milvus_health_url(milvus_uri: str) -> str:
    """Derive the Milvus health-check URL from the HTTP URI."""
    parsed = urlparse(milvus_uri)
    if not parsed.hostname:
        raise ValueError(f"Cannot derive health URL: invalid milvus_uri={milvus_uri!r}")
    return f"{parsed.scheme}://{parsed.hostname}:9091"


class VectorStore:
    """Vector store manager.

    Uses the shared ``BaseVectorStore`` abstraction.  The public API
    (``add_requirement``, ``search``, ``find_similar``, ``delete_*``) is
    unchanged so callers require no modifications.

    When bound to a ``VectorStorePlugin`` via :meth:`bind_plugin`, all
    operations delegate to the plugin (which provides circuit breaker
    protection and shared lifecycle).  When not bound, the original
    direct-Milvus code path is used as fallback.
    """

    def __init__(
        self,
        store: BaseVectorStore | None = None,
        collection: str = COLLECTION_REQUIREMENTS,
    ):
        self._store = store or MilvusVectorStore(
            uri=settings.milvus_uri,
            token=settings.milvus_token.get_secret_value(),
        )
        self._collection = collection
        self._available = False
        self._plugin: VectorStorePlugin | None = None

    # ── Plugin binding ─────────────────────────────────────────────────────

    def bind_plugin(self, plugin: VectorStorePlugin) -> None:
        """Bind a VectorStorePlugin so all operations delegate to it."""
        self._plugin = plugin
        self._available = plugin.available
        logger.info("vector_store_bound_to_plugin", available=plugin.available)

    def unbind_plugin(self) -> None:
        """Unbind the plugin, reverting to direct-Milvus fallback."""
        self._plugin = None
        self._available = False
        logger.info("vector_store_unbound_from_plugin")

    @property
    def available(self) -> bool:
        """Whether the vector store was successfully initialized."""
        if self._plugin is not None:
            return self._plugin.available
        return self._available

    async def initialize(self) -> None:
        """Explicitly initialize the vector store during agent startup."""
        await self._store.initialize()
        await self._store.ensure_collection(self._collection, dimension=384)
        self._available = True
        count = await self._store.count(self._collection)
        logger.info(
            "vector_store_initialized",
            backend="milvus",
            collection=self._collection,
            collection_count=count,
        )

    async def close(self) -> None:
        """Release Milvus connection."""
        if self._available:
            await self._store.close()
            self._available = False

    # ── Single-item operations ─────────────────────────────────────────────────

    async def add_requirement(
        self,
        requirement_id: str,
        title: str,
        description: str,
        category: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Add a requirement to the vector store."""
        if not self.available:
            return

        text = embedder.format_requirement_for_embedding(
            title=title,
            description=description,
            category=category,
        )

        doc_metadata: dict[str, Any] = {
            "title": title,
            "category": category or "其他",
            "text_length": len(text),
        }
        if metadata:
            doc_metadata.update(metadata)

        if self._plugin is not None:
            await self._plugin.upsert_text(
                self._collection, requirement_id, text, doc_metadata
            )
            logger.debug(
                "requirement_added_to_vector",
                requirement_id=requirement_id,
                title_hash=hash_identifier(title),
            )
            return

        embedding = await asyncio.to_thread(shared_embedder.embed, text)

        await self._store.upsert(
            collection=self._collection,
            id=requirement_id,
            embedding=embedding,
            document=text,
            metadata=doc_metadata,
        )

        logger.debug(
            "requirement_added_to_vector",
            requirement_id=requirement_id,
            title_hash=hash_identifier(title),
        )

    async def add_requirements_batch(
        self,
        requirements: list[dict[str, Any]],
    ) -> None:
        """Add requirements to the vector store in a batch."""
        if not self.available or not requirements:
            return

        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for req in requirements:
            text = embedder.format_requirement_for_embedding(
                title=req["title"],
                description=req["description"],
                category=req.get("category"),
            )
            texts.append(text)
            ids.append(req["id"])

            doc_metadata: dict[str, Any] = {
                "title": req["title"],
                "category": req.get("category", "其他"),
                "text_length": len(text),
            }
            if req.get("metadata"):
                doc_metadata.update(req["metadata"])
            metadatas.append(doc_metadata)

        if self._plugin is not None:
            from shared.app.plugins.vector_store import VectorUpsertItem

            items = [
                VectorUpsertItem(id=id_, text=text, metadata=meta)
                for id_, text, meta in zip(ids, texts, metadatas)
            ]
            await self._plugin.upsert_batch_text(self._collection, items)
            logger.info("requirements_batch_added", count=len(requirements))
            return

        embeddings = await asyncio.to_thread(shared_embedder.embed_batch, texts)

        await self._store.upsert_batch(
            collection=self._collection,
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info("requirements_batch_added", count=len(requirements))

    # ── Search ─────────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        n_results: int = 10,
        category_filter: Optional[str] = None,
        min_similarity: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Search requirements semantically."""
        if not self.available:
            return []

        if self._plugin is not None:
            metadata_filters: dict[str, Any] | None = None
            if category_filter:
                metadata_filters = {"category": category_filter}
            results = await self._plugin.search_text(
                self._collection,
                query,
                limit=n_results,
                min_score=min_similarity,
                metadata_filters=metadata_filters,
            )
            matches: list[dict[str, Any]] = []
            for r in results:
                matches.append({
                    "id": r.id,
                    "title": r.metadata.get("title", ""),
                    "category": r.metadata.get("category", ""),
                    "similarity": round(r.score, 4),
                    "document": r.document,
                })
            logger.debug(
                "vector_search_completed",
                query_length=len(query),
                results_count=len(matches),
            )
            return matches

        query_embedding = await asyncio.to_thread(shared_embedder.embed, query)

        filter_expr: str | None = None
        if category_filter:
            safe_cat = category_filter.replace('"', "").replace("\\", "")
            filter_expr = f'metadata["category"] == "{safe_cat}"'

        results = await self._store.search(
            collection=self._collection,
            query_embedding=query_embedding,
            limit=n_results,
            filter_expr=filter_expr,
        )

        matches = []
        for r in results:
            similarity = r.score
            if similarity < min_similarity:
                continue
            matches.append({
                "id": r.id,
                "title": r.metadata.get("title", ""),
                "category": r.metadata.get("category", ""),
                "similarity": round(similarity, 4),
                "document": r.document,
            })

        logger.debug(
            "vector_search_completed",
            query_length=len(query),
            results_count=len(matches),
        )
        return matches

    async def find_similar(
        self,
        requirement_id: str,
        n_results: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Find similar requirements.

        Fetches the document for *requirement_id*, re-embeds it,
        then queries for nearest neighbours.
        """
        if not self.available:
            return []

        if self._plugin is not None:
            results = await self._plugin.search_by_id(
                self._collection,
                requirement_id,
                limit=n_results,
                min_score=min_similarity,
            )
            matches: list[dict[str, Any]] = []
            for r in results:
                matches.append({
                    "id": r.id,
                    "title": r.metadata.get("title", ""),
                    "category": r.metadata.get("category", ""),
                    "similarity": round(r.score, 4),
                    "document": r.document,
                })
            return matches

        rows = await self._store.get_by_ids(
            collection=self._collection,
            ids=[requirement_id],
            output_fields=["document", "metadata"],
        )
        if not rows:
            logger.debug("find_similar_target_not_found", requirement_id=requirement_id)
            return []

        target_doc = rows[0].document
        if not target_doc:
            logger.debug("find_similar_target_empty_document", requirement_id=requirement_id)
            return []

        target_embedding = await asyncio.to_thread(shared_embedder.embed, target_doc)

        results = await self._store.search(
            collection=self._collection,
            query_embedding=target_embedding,
            limit=n_results + 1,
        )

        matches = []
        for r in results:
            if r.id == requirement_id:
                continue
            similarity = r.score
            if similarity < min_similarity:
                continue
            matches.append({
                "id": r.id,
                "title": r.metadata.get("title", ""),
                "category": r.metadata.get("category", ""),
                "similarity": round(similarity, 4),
                "document": r.document,
            })

        return matches[:n_results]

    # ── Delete ─────────────────────────────────────────────────────────────────

    async def delete_requirement(self, requirement_id: str) -> None:
        """Delete a requirement vector."""
        if not self.available:
            return
        if self._plugin is not None:
            await self._plugin.delete(self._collection, requirement_id)
        else:
            await self._store.delete(self._collection, [requirement_id])
        logger.debug("requirement_deleted_from_vector", requirement_id=requirement_id)

    async def delete_requirements_batch(self, requirement_ids: list[str]) -> None:
        """Delete requirement vectors in a batch."""
        if not self.available or not requirement_ids:
            return
        if self._plugin is not None:
            await self._plugin.delete_many(self._collection, requirement_ids)
        else:
            await self._store.delete(self._collection, requirement_ids)
        logger.info("requirements_batch_deleted", count=len(requirement_ids))

    # ── Stats ──────────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Return vector-store statistics."""
        if not self.available:
            return {
                "backend": "milvus",
                "status": "unavailable",
                "total_documents": 0,
            }
        if self._plugin is not None:
            count = await self._plugin.count(self._collection)
        else:
            count = await self._store.count(self._collection)
        parsed = urlparse(settings.milvus_uri)
        return {
            "collection": self._collection,
            "total_documents": count,
            "backend": "milvus",
            "uri": f"{parsed.hostname}:{parsed.port}",
        }


# Global vector store instance.
vector_store = VectorStore()
