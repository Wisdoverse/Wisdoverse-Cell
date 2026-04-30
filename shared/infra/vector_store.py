"""Unified vector store abstraction (base class and result types).

Provides a backend-agnostic vector search interface used by:
- requirement_manager: requirement semantic search
- evolution system: trace/memory semantic search
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VectorSearchResult:
    """Single search result.

    ``score`` semantics depend on the metric: for COSINE the value is
    cosine similarity in [-1.0, 1.0] (higher = more similar).  With
    non-negative embeddings (e.g. all-MiniLM-L6-v2) the effective
    range is [0.0, 1.0].

    Note: the dataclass is frozen (attribute rebinding is prevented),
    but ``metadata`` contents remain mutable by design — treat as
    read-only.
    """

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    document: str = ""


@dataclass(frozen=True)
class VectorDocument:
    """A document retrieved by primary key via ``get_by_ids``.

    Frozen (attribute rebinding prevented), but ``metadata`` contents
    remain mutable — treat as read-only.
    """

    id: str
    document: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Abstract vector store interface.

    All implementations must be async-safe.  Concrete backends live in
    separate modules (e.g. ``milvus_store.py``) so the import cost of
    heavy SDKs is paid only when actually used.

    Results from ``search`` are ordered by descending similarity.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Connect to the vector database."""

    @abstractmethod
    async def close(self) -> None:
        """Release resources / close connections."""

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        id: str,
        embedding: list[float],
        document: str,
        metadata: dict[str, Any],
    ) -> None:
        """Insert or update a single vector."""

    async def upsert_batch(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert or update multiple vectors in one call.

        Validates that all lists have the same length, then delegates
        to ``_do_upsert_batch``.  Subclasses override ``_do_upsert_batch``.
        """
        n = len(ids)
        if not (len(embeddings) == len(documents) == len(metadatas) == n):
            raise ValueError(
                f"Length mismatch: ids={n}, embeddings={len(embeddings)}, "
                f"documents={len(documents)}, metadatas={len(metadatas)}"
            )
        await self._do_upsert_batch(collection, ids, embeddings, documents, metadatas)

    @abstractmethod
    async def _do_upsert_batch(
        self,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Backend-specific batch upsert (called after length validation)."""

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_embedding: list[float],
        limit: int = 10,
        filter_expr: str | None = None,
    ) -> list[VectorSearchResult]:
        """Return the *limit* most similar vectors (descending similarity)."""

    @abstractmethod
    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete vectors by id."""

    @abstractmethod
    async def count(self, collection: str) -> int:
        """Return total number of vectors in *collection*."""

    @abstractmethod
    async def ensure_collection(self, collection: str, dimension: int = 384) -> None:
        """Create the collection if it does not exist."""

    @abstractmethod
    async def get_by_ids(
        self,
        collection: str,
        ids: list[str],
        output_fields: list[str] | None = None,
    ) -> list[VectorDocument]:
        """Retrieve documents by primary key.

        Returns a list of ``VectorDocument`` for the requested *ids*.
        *output_fields* defaults to ``["document", "metadata"]``.
        """
