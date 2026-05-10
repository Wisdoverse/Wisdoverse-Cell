"""VectorStorePlugin — RuntimePlugin for vector search with circuit breaker protection.

Provides text embedding + vector upsert/search/delete with:
- Circuit breaker for resilience
- Graceful degradation (non-strict mode returns defaults)
- Metadata filter compilation for Milvus expressions
- Batch operations for efficiency
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from prometheus_client import Counter, Gauge, Histogram

from shared.app.runtime import AgentRuntime, HealthCheckResult, RuntimePlugin
from shared.infra.circuit_breaker import CircuitBreaker
from shared.infra.embedder import DEFAULT_DIMENSION, TextEmbedder, embedder
from shared.infra.vector_store import BaseVectorStore, VectorDocument, VectorSearchResult
from shared.utils.logger import get_logger

logger = get_logger("plugin.vector-store")

_COLLECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_METADATA_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RETRY_BASE_DELAY_SECONDS = 0.1

T = TypeVar("T")

VECTOR_STORE_OPERATIONS = Counter(
    "wisdoverse-cell_vector_store_operations_total",
    "Total vector store operations by collection, operation, and outcome.",
    ["collection", "operation", "status"],
)

VECTOR_STORE_OPERATION_DURATION = Histogram(
    "wisdoverse-cell_vector_store_operation_duration_seconds",
    "Vector store operation duration in seconds.",
    ["collection", "operation"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

VECTOR_STORE_AVAILABLE = Gauge(
    "wisdoverse-cell_vector_store_available",
    "Whether the vector store plugin currently has a usable client.",
)

VECTOR_STORE_DOCUMENTS = Gauge(
    "wisdoverse-cell_vector_store_documents",
    "Number of indexed documents per vector collection.",
    ["collection"],
)

VECTOR_STORE_CIRCUIT_BREAKER_OPEN_TOTAL = Counter(
    "wisdoverse-cell_vector_store_circuit_breaker_open_total",
    "Number of vector store operations short-circuited by an open circuit breaker.",
)


# ── Data Types ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VectorCollection:
    """Collection configuration."""

    description: str = ""
    dimension: int = DEFAULT_DIMENSION


@dataclass(frozen=True)
class VectorUpsertItem:
    """Item for batch upsert operations."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Plugin ─────────────────────────────────────────────────────────────────


class VectorStorePlugin(RuntimePlugin):
    """Vector store integration with circuit breaker and graceful degradation."""

    name = "vector-store"

    def __init__(
        self,
        *,
        collections: dict[str, VectorCollection | str],
        required: bool = False,
        enabled: bool = True,
        uri: str = "",
        token: str = "",
        store: BaseVectorStore | None = None,
        embedder_instance: TextEmbedder | None = None,
        connect_timeout_seconds: int = 10,
        operation_timeout_seconds: int = 15,
        retry_attempts: int = 2,
    ) -> None:
        if not collections:
            raise ValueError("collections must not be empty")

        normalized: dict[str, VectorCollection] = {}
        for name, col in collections.items():
            if not _COLLECTION_NAME_RE.match(name):
                raise ValueError(
                    f"Invalid collection name '{name}': must match ^[a-z][a-z0-9_]*$"
                )
            if isinstance(col, str):
                col = VectorCollection(description=col)
            if col.dimension < 1:
                raise ValueError(
                    f"Collection '{name}' has non-positive dimension: {col.dimension}"
                )
            normalized[name] = col

        self._collections = normalized
        self._required = required
        self._enabled = enabled
        self._uri = uri
        self._token = token
        self._store = store
        self._embedder = embedder_instance or embedder
        self._connect_timeout = connect_timeout_seconds
        self._operation_timeout = operation_timeout_seconds
        self._retry_attempts = retry_attempts
        self._available = False
        self._collections_ready = False
        self._last_error = ""
        self._agent_id = ""
        self._reconnect_lock = asyncio.Lock()
        self._breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            name="vector-store",
        )

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True only when enabled AND connected."""
        return self._enabled and self._available

    # ── Lifecycle ──────────────────────────────────────────────────────────

    async def startup(self, runtime: AgentRuntime) -> None:
        self._agent_id = runtime.agent_id
        if not self._enabled:
            self._set_available(False)
            logger.info("vector_store_plugin_disabled", agent_id=runtime.agent_id)
            return

        self._breaker.name = f"{runtime.agent_id}.vector-store"
        try:
            await self._initialize_store()
            self._last_error = ""
            logger.info(
                "vector_store_plugin_started",
                agent_id=runtime.agent_id,
                collections=list(self._collections.keys()),
            )
        except Exception as exc:
            self._set_available(False)
            self._collections_ready = False
            self._last_error = type(exc).__name__
            logger.warning(
                "vector_store_plugin_startup_failed",
                agent_id=runtime.agent_id,
                error_type=type(exc).__name__,
            )
            await self._close_store_best_effort()

    async def shutdown(self, runtime: AgentRuntime) -> None:
        self._set_available(False)
        self._collections_ready = False
        await self._close_store_best_effort()

    async def health_check(self) -> dict[str, HealthCheckResult]:
        if not self._enabled:
            return {}

        detail = self._last_error or "vector store unavailable"
        client_status = self._capability_status(ok=self._available, detail=detail)
        collections_status = self._capability_status(
            ok=self._collections_ready,
            detail=detail,
        )

        breaker_state = self._breaker.state.value
        breaker_status = HealthCheckResult(
            "ok" if breaker_state == "closed" else "degraded",
            f"state={breaker_state}",
        )

        return {
            "client": client_status,
            "collections": collections_status,
            "circuit_breaker": breaker_status,
        }

    def _capability_status(self, *, ok: bool, detail: str) -> HealthCheckResult:
        if ok:
            return HealthCheckResult("ok")
        if self._required:
            return HealthCheckResult("down", detail)
        return HealthCheckResult("degraded", detail)

    def _set_available(self, available: bool) -> None:
        self._available = available
        VECTOR_STORE_AVAILABLE.set(1 if available else 0)

    async def _ensure_store(self) -> None:
        if self._store is not None:
            return

        from shared.config import settings
        from shared.infra.milvus_store import MilvusVectorStore

        uri = self._uri or settings.milvus_uri
        token = self._token or settings.milvus_token.get_secret_value()
        self._store = MilvusVectorStore(
            uri=uri,
            token=token,
            timeout=self._connect_timeout,
        )

    async def _initialize_store(self) -> None:
        await self._ensure_store()
        await asyncio.wait_for(
            self._store.initialize(),  # type: ignore[union-attr]
            timeout=self._connect_timeout,
        )
        for col_name, col in self._collections.items():
            await asyncio.wait_for(
                self._store.ensure_collection(col_name, col.dimension),  # type: ignore[union-attr]
                timeout=self._connect_timeout,
            )
        self._set_available(True)
        self._collections_ready = True

    async def _close_store_best_effort(self) -> None:
        if self._store is None:
            return
        try:
            await self._store.close()
        except Exception as exc:
            logger.warning(
                "vector_store_plugin_close_failed",
                agent_id=self._agent_id,
                error_type=type(exc).__name__,
            )

    # ── Guard helpers ──────────────────────────────────────────────────────

    def _validate_collection(self, collection: str) -> None:
        """Raise ValueError if collection is not registered."""
        if collection not in self._collections:
            raise ValueError(
                f"Unknown collection '{collection}'. "
                f"Registered: {list(self._collections.keys())}"
            )

    async def _recover(self, *, collection: str, operation: str, strict: bool) -> bool:
        async with self._reconnect_lock:
            if self.available:
                return True

            if not self._breaker.can_execute():
                self._record_degraded_operation(
                    collection=collection,
                    operation=operation,
                    breaker_open=True,
                )
                if strict:
                    raise RuntimeError("Vector store is not available")
                return False

            try:
                await self._initialize_store()
                self._breaker.record_success()
                self._last_error = ""
                logger.info(
                    "vector_store_plugin_recovered",
                    agent_id=self._agent_id,
                    collection=collection,
                    operation=operation,
                )
                return True
            except Exception as exc:
                self._set_available(False)
                self._collections_ready = False
                self._last_error = type(exc).__name__
                self._breaker.record_failure()
                logger.warning(
                    "vector_store_plugin_recovery_failed",
                    agent_id=self._agent_id,
                    collection=collection,
                    operation=operation,
                    error_type=type(exc).__name__,
                )
                await self._close_store_best_effort()
                if strict:
                    raise RuntimeError("Vector store is not available") from exc
                self._record_degraded_operation(
                    collection=collection,
                    operation=operation,
                )
                return False

    async def _check_available(
        self,
        *,
        collection: str,
        operation: str,
        strict: bool,
    ) -> bool:
        """Check availability + circuit breaker, attempting lazy recovery when needed."""
        if not self._enabled:
            self._record_degraded_operation(
                collection=collection,
                operation=operation,
            )
            if strict:
                raise RuntimeError("Vector store is not available")
            return False

        if self.available and self._breaker.can_execute():
            return True

        if self.available and not self._breaker.can_execute():
            self._record_degraded_operation(
                collection=collection,
                operation=operation,
                breaker_open=True,
            )
            if strict:
                raise RuntimeError("Vector store is not available")
            return False

        return await self._recover(
            collection=collection,
            operation=operation,
            strict=strict,
        )

    # ── Metadata filter compilation ────────────────────────────────────────

    @staticmethod
    def _escape_filter_string(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _compile_metadata_filters(cls, filters: dict[str, Any] | None) -> str | None:
        """Compile metadata filters to Milvus filter expression."""
        if not filters:
            return None

        parts: list[str] = []
        for key, value in filters.items():
            if not _METADATA_KEY_RE.match(key):
                raise ValueError(
                    f"Invalid metadata filter key '{key}': must match "
                    f"{_METADATA_KEY_RE.pattern}"
                )
            if isinstance(value, str):
                escaped = cls._escape_filter_string(value)
                parts.append(f'metadata["{key}"] == "{escaped}"')
            elif isinstance(value, bool):
                parts.append(f'metadata["{key}"] == {"true" if value else "false"}')
            elif isinstance(value, (int, float)):
                parts.append(f'metadata["{key}"] == {value}')
            else:
                escaped = cls._escape_filter_string(str(value))
                parts.append(f'metadata["{key}"] == "{escaped}"')
        return " and ".join(parts)

    # ── Metrics + retry helpers ────────────────────────────────────────────

    def _record_operation(
        self,
        *,
        collection: str,
        operation: str,
        status: str,
        duration_seconds: float | None = None,
    ) -> None:
        VECTOR_STORE_OPERATIONS.labels(
            collection=collection,
            operation=operation,
            status=status,
        ).inc()
        if duration_seconds is not None:
            VECTOR_STORE_OPERATION_DURATION.labels(
                collection=collection,
                operation=operation,
            ).observe(duration_seconds)

    def _record_degraded_operation(
        self,
        *,
        collection: str,
        operation: str,
        breaker_open: bool = False,
    ) -> None:
        self._record_operation(
            collection=collection,
            operation=operation,
            status="degraded",
        )
        if breaker_open:
            VECTOR_STORE_CIRCUIT_BREAKER_OPEN_TOTAL.inc()

    def _retry_delay_seconds(self, attempt: int) -> float:
        base = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        return base * random.uniform(0.5, 1.0)

    async def _embed_text(
        self,
        *,
        collection: str,
        operation: str,
        text: str,
        strict: bool,
    ) -> list[float] | None:
        started_at = time.monotonic()
        try:
            return await asyncio.to_thread(self._embedder.embed, text)
        except Exception as exc:
            self._last_error = type(exc).__name__
            self._breaker.record_failure()
            logger.error(
                "vector_store_embed_failed",
                agent_id=self._agent_id,
                collection=collection,
                operation=operation,
                error_type=type(exc).__name__,
            )
            self._record_operation(
                collection=collection,
                operation=operation,
                status="error" if strict else "degraded",
                duration_seconds=time.monotonic() - started_at,
            )
            if strict:
                raise
            return None

    async def _embed_batch(
        self,
        *,
        collection: str,
        operation: str,
        texts: list[str],
        strict: bool,
    ) -> list[list[float]] | None:
        started_at = time.monotonic()
        try:
            return await asyncio.to_thread(self._embedder.embed_batch, texts)
        except Exception as exc:
            self._last_error = type(exc).__name__
            self._breaker.record_failure()
            logger.error(
                "vector_store_embed_batch_failed",
                agent_id=self._agent_id,
                collection=collection,
                operation=operation,
                error_type=type(exc).__name__,
            )
            self._record_operation(
                collection=collection,
                operation=operation,
                status="error" if strict else "degraded",
                duration_seconds=time.monotonic() - started_at,
            )
            if strict:
                raise
            return None

    async def _run_store_call(
        self,
        *,
        operation: str,
        collection: str,
        call: Callable[[], Awaitable[T]],
        default_factory: Callable[[], T],
        strict: bool,
    ) -> T:
        attempts = max(1, self._retry_attempts + 1)
        started_at = time.monotonic()

        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(call(), timeout=self._operation_timeout)
                self._breaker.record_success()
                self._last_error = ""
                self._record_operation(
                    collection=collection,
                    operation=operation,
                    status="success",
                    duration_seconds=time.monotonic() - started_at,
                )
                return result
            except ValueError:
                raise
            except Exception as exc:
                if attempt < attempts:
                    logger.warning(
                        "vector_store_operation_retry",
                        agent_id=self._agent_id,
                        collection=collection,
                        operation=operation,
                        attempt=attempt,
                        max_attempts=attempts,
                        error_type=type(exc).__name__,
                    )
                    await asyncio.sleep(self._retry_delay_seconds(attempt))
                    continue

                self._breaker.record_failure()
                self._last_error = type(exc).__name__
                logger.error(
                    "vector_store_operation_failed",
                    agent_id=self._agent_id,
                    collection=collection,
                    operation=operation,
                    attempt=attempt,
                    attempts=attempts,
                    error_type=type(exc).__name__,
                )
                self._record_operation(
                    collection=collection,
                    operation=operation,
                    status="error" if strict else "degraded",
                    duration_seconds=time.monotonic() - started_at,
                )
                if strict:
                    raise
                return default_factory()

        return default_factory()

    # ── Store operation adapters ──────────────────────────────────────────

    async def _upsert_document(
        self,
        *,
        collection: str,
        doc_id: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any],
    ) -> bool:
        await self._store.upsert(  # type: ignore[union-attr]
            collection,
            doc_id,
            embedding,
            text,
            metadata,
        )
        return True

    async def _upsert_batch_documents(
        self,
        *,
        collection: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> int:
        await self._store.upsert_batch(  # type: ignore[union-attr]
            collection,
            ids,
            embeddings,
            documents,
            metadatas,
        )
        return len(ids)

    async def _delete_documents(
        self,
        *,
        collection: str,
        doc_ids: list[str],
    ) -> bool:
        await self._store.delete(collection, doc_ids)  # type: ignore[union-attr]
        return True

    async def _delete_many_documents(
        self,
        *,
        collection: str,
        doc_ids: list[str],
    ) -> int:
        await self._store.delete(collection, doc_ids)  # type: ignore[union-attr]
        return len(doc_ids)

    # ── Operations ─────────────────────────────────────────────────────────

    async def search_text(
        self,
        collection: str,
        query: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        metadata_filters: dict[str, Any] | None = None,
        strict: bool = False,
    ) -> list[VectorSearchResult]:
        """Search by text query."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="search_text",
            strict=strict,
        ):
            return []

        filter_expr = self._compile_metadata_filters(metadata_filters)
        embedding = await self._embed_text(
            collection=collection,
            operation="search_text",
            text=query,
            strict=strict,
        )
        if embedding is None:
            return []

        results = await self._run_store_call(
            operation="search_text",
            collection=collection,
            call=lambda: self._store.search(  # type: ignore[union-attr]
                collection,
                embedding,
                limit=limit,
                filter_expr=filter_expr,
            ),
            default_factory=list,
            strict=strict,
        )
        if min_score is not None:
            results = [r for r in results if r.score >= min_score]
        return results

    async def search_by_id(
        self,
        collection: str,
        doc_id: str,
        *,
        limit: int = 10,
        min_score: float | None = None,
        include_self: bool = False,
        strict: bool = False,
    ) -> list[VectorSearchResult]:
        """Search for similar documents to one identified by id."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="search_by_id",
            strict=strict,
        ):
            return []

        docs = await self._run_store_call(
            operation="get_by_ids",
            collection=collection,
            call=lambda: self._store.get_by_ids(collection, [doc_id]),  # type: ignore[union-attr]
            default_factory=list,
            strict=strict,
        )
        if not docs:
            return []

        doc = docs[0]
        if not doc.document:
            return []

        embedding = await self._embed_text(
            collection=collection,
            operation="search_by_id",
            text=doc.document,
            strict=strict,
        )
        if embedding is None:
            return []

        fetch_limit = limit if include_self else limit + 1
        results = await self._run_store_call(
            operation="search_by_id",
            collection=collection,
            call=lambda: self._store.search(  # type: ignore[union-attr]
                collection,
                embedding,
                limit=fetch_limit,
            ),
            default_factory=list,
            strict=strict,
        )
        if not include_self:
            results = [r for r in results if r.id != doc_id][:limit]
        if min_score is not None:
            results = [r for r in results if r.score >= min_score]
        return results

    async def upsert_text(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        strict: bool = False,
    ) -> bool:
        """Upsert a single document by text."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="upsert_text",
            strict=strict,
        ):
            return False

        embedding = await self._embed_text(
            collection=collection,
            operation="upsert_text",
            text=text,
            strict=strict,
        )
        if embedding is None:
            return False

        return await self._run_store_call(
            operation="upsert_text",
            collection=collection,
            call=lambda: self._upsert_document(
                collection=collection,
                doc_id=doc_id,
                embedding=embedding,
                text=text,
                metadata=metadata or {},
            ),
            default_factory=lambda: False,
            strict=strict,
        )

    async def upsert_batch_text(
        self,
        collection: str,
        items: list[VectorUpsertItem],
        *,
        strict: bool = False,
    ) -> int:
        """Batch upsert documents. Returns number of items upserted."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="upsert_batch_text",
            strict=strict,
        ):
            return 0

        if not items:
            return 0

        texts = [item.text for item in items]
        embeddings = await self._embed_batch(
            collection=collection,
            operation="upsert_batch_text",
            texts=texts,
            strict=strict,
        )
        if embeddings is None:
            return 0

        ids = [item.id for item in items]
        documents = texts
        metadatas = [item.metadata for item in items]
        return await self._run_store_call(
            operation="upsert_batch_text",
            collection=collection,
            call=lambda: self._upsert_batch_documents(
                collection=collection,
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            ),
            default_factory=lambda: 0,
            strict=strict,
        )

    async def get_by_ids(
        self,
        collection: str,
        ids: list[str],
        *,
        strict: bool = False,
    ) -> list[VectorDocument]:
        """Retrieve documents by primary key."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="get_by_ids",
            strict=strict,
        ):
            return []

        return await self._run_store_call(
            operation="get_by_ids",
            collection=collection,
            call=lambda: self._store.get_by_ids(collection, ids),  # type: ignore[union-attr]
            default_factory=list,
            strict=strict,
        )

    async def delete(
        self,
        collection: str,
        doc_id: str,
        *,
        strict: bool = False,
    ) -> bool:
        """Delete a single document."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="delete",
            strict=strict,
        ):
            return False

        return await self._run_store_call(
            operation="delete",
            collection=collection,
            call=lambda: self._delete_documents(
                collection=collection,
                doc_ids=[doc_id],
            ),
            default_factory=lambda: False,
            strict=strict,
        )

    async def delete_many(
        self,
        collection: str,
        doc_ids: list[str],
        *,
        strict: bool = False,
    ) -> int:
        """Delete multiple documents. Returns number of ids submitted for deletion."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="delete_many",
            strict=strict,
        ):
            return 0

        if not doc_ids:
            return 0

        return await self._run_store_call(
            operation="delete_many",
            collection=collection,
            call=lambda: self._delete_many_documents(
                collection=collection,
                doc_ids=doc_ids,
            ),
            default_factory=lambda: 0,
            strict=strict,
        )

    async def count(
        self,
        collection: str,
        *,
        strict: bool = False,
    ) -> int:
        """Return total number of vectors in a collection."""
        self._validate_collection(collection)
        if not await self._check_available(
            collection=collection,
            operation="count",
            strict=strict,
        ):
            return 0

        count = await self._run_store_call(
            operation="count",
            collection=collection,
            call=lambda: self._store.count(collection),  # type: ignore[union-attr]
            default_factory=lambda: 0,
            strict=strict,
        )
        VECTOR_STORE_DOCUMENTS.labels(collection=collection).set(count)
        return count
