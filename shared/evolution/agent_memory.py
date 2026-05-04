"""
AgentMemory — three-tier memory for evolution agents.

Short-term:  Redis with TTL  (ephemeral, fast, optional)
Long-term:   PostgreSQL via  EvolutionRepository  (permanent, optional)
Semantic:    Milvus via shared VectorStore  (vector search, optional)

All backends are optional; when absent, operations silently become no-ops.
When present but failing, errors are logged at WARNING level.
"""

import asyncio
import json
from typing import Any, Optional

from shared.evolution.db.repository import EvolutionRepository
from shared.infra.embedder import TextEmbedder
from shared.infra.embedder import embedder as default_embedder
from shared.infra.vector_store import BaseVectorStore
from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

logger = get_logger("evolution.memory")

# Default collection for evolution memory vectors
EVOLUTION_MEMORY_COLLECTION = "evolution_memory"


class AgentMemory:
    """Three-tier memory: short-term (Redis) + long-term (PG) + semantic (Milvus)."""

    REDIS_PREFIX = "evolution:memory:{agent_id}:"

    def __init__(
        self,
        agent_id: str,
        redis=None,
        db_manager=None,
        vector_store: Optional[BaseVectorStore] = None,
        embedder_instance: Optional[TextEmbedder] = None,
    ):
        self._agent_id = agent_id
        self._redis = redis
        self._db_manager = db_manager
        self._vector_store = vector_store
        self._embedder = embedder_instance or default_embedder

    # ── Short-term (Redis) ────────────────────────────────────────────────────

    async def set_short_term(
        self, key: str, value: dict[str, Any], ttl_seconds: int = 3600
    ) -> None:
        """Store in Redis with TTL. Logs a warning if Redis unavailable."""
        if self._redis is None:
            return
        try:
            redis_key = f"evolution:memory:{self._agent_id}:{key}"
            await self._redis.set(redis_key, json.dumps(value), ex=ttl_seconds)
        except Exception as e:
            logger.warning("short_term_memory_set_failed", key=key, error=str(e))

    async def get_short_term(self, key: str) -> Optional[dict[str, Any]]:
        """Read from Redis. Returns None if missing or Redis down."""
        if self._redis is None:
            return None
        try:
            redis_key = f"evolution:memory:{self._agent_id}:{key}"
            data = await self._redis.get(redis_key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.warning("short_term_memory_get_failed", key=key, error=str(e))
            return None

    # ── Long-term (PostgreSQL) ────────────────────────────────────────────────

    async def set_long_term(self, key: str, value: dict[str, Any]) -> None:
        """Store in PostgreSQL (permanent). Upsert on key conflict."""
        if self._db_manager is None:
            return
        try:
            async with self._db_manager.session() as session:
                repo = EvolutionRepository(session)
                await repo.save_memory(
                    agent_id=self._agent_id,
                    memory_type="long_term",
                    key=key,
                    value=value,
                )
        except Exception as e:
            logger.warning("long_term_memory_set_failed", key=key, error=str(e))

    async def get_long_term(self, key: str) -> Optional[dict[str, Any]]:
        """Read from PostgreSQL."""
        if self._db_manager is None:
            return None
        try:
            async with self._db_manager.session() as session:
                repo = EvolutionRepository(session)
                row = await repo.get_memory(self._agent_id, key)
                return row.value if row else None
        except Exception as e:
            logger.warning("long_term_memory_get_failed", key=key, error=str(e))
            return None

    # ── Semantic search (Milvus) ──────────────────────────────────────────────

    async def store_semantic(
        self,
        key: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        collection: str = EVOLUTION_MEMORY_COLLECTION,
    ) -> None:
        """Store a text with its embedding in the vector database."""
        if self._vector_store is None:
            return
        try:
            embedding = await asyncio.to_thread(self._embedder.embed, text)
            await self._vector_store.upsert(
                collection=collection,
                id=f"{self._agent_id}:{key}",
                embedding=embedding,
                document=text,
                metadata={"agent_id": self._agent_id, "key": key, **(metadata or {})},
            )
        except Exception as e:
            logger.warning("semantic_memory_store_failed", key=key, error=str(e))

    async def semantic_search(
        self,
        query: str,
        collection: str = EVOLUTION_MEMORY_COLLECTION,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search long-term memory semantically.

        Returns a list of dicts with keys: id, score, value (metadata).
        """
        if self._vector_store is None:
            return []
        try:
            embedding = await asyncio.to_thread(self._embedder.embed, query)
            results = await self._vector_store.search(
                collection, embedding, limit=limit
            )
            return [
                {"id": r.id, "score": r.score, "value": r.metadata}
                for r in results
            ]
        except Exception as e:
            logger.warning(
                "semantic_search_failed",
                query_hash=hash_identifier(query),
                query_length=len(query),
                error=str(e),
            )
            return []

    # ── Convenience ───────────────────────────────────────────────────────────

    async def record_optimization(
        self, skill_id: str, version: int, success: bool, details: dict[str, Any]
    ) -> None:
        """Convenience: record an optimization attempt in long-term memory."""
        key = f"optimization:{skill_id}:v{version}"
        await self.set_long_term(
            key,
            {
                "skill_id": skill_id,
                "version": version,
                "success": success,
                **details,
            },
        )
