"""DSAR (Data Subject Access Request) Service

Cloud-native implementation following GDPR Article 17 (Right to Erasure)
and China PIPL Article 47 requirements.

Architecture: Each agent mounts the shared router and provides its own
DSARHandler implementation.  The handler knows which tables and Redis
key patterns belong to that agent.
"""
from __future__ import annotations

import abc
import hashlib
from typing import Any, Optional, Sequence

import redis.asyncio as aioredis
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.schemas.dsar import DSARResult
from shared.utils.logger import get_logger

logger = get_logger("dsar")


def _hash_uid(user_id: str) -> str:
    """One-way hash for audit logs — never log PII in plain text."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


class TableSpec:
    """Describes a table that stores user-associated data.

    Args:
        table_name: SQL table name.
        user_column: Column that holds the user identifier.
        model: SQLAlchemy ORM model class (optional, for ORM-style queries).
    """

    def __init__(self, table_name: str, user_column: str = "user_id", model: Any = None):
        self.table_name = table_name
        self.user_column = user_column
        self.model = model


class DSARHandler(abc.ABC):
    """Abstract base — each agent implements this."""

    @abc.abstractmethod
    def table_specs(self) -> Sequence[TableSpec]:
        """Return the list of tables this agent owns."""

    @abc.abstractmethod
    def redis_key_patterns(self) -> Sequence[str]:
        """Return Redis key patterns containing ``{user_id}`` placeholder.

        Example: ``["pending_op:*", "chat:user_info:*"]``
        For patterns that embed user_id literally, use ``{user_id}`` and
        the service will substitute at runtime.
        """

    @abc.abstractmethod
    async def get_session(self) -> AsyncSession:
        """Provide a write-capable async session (caller manages commit)."""

    def get_redis(self) -> Optional[aioredis.Redis]:
        """Return a Redis client, or None if this agent has no Redis keys."""
        return None


class DSARService:
    """Handles data subject access requests for one agent."""

    def __init__(self, handler: DSARHandler):
        self._handler = handler

    # ------------------------------------------------------------------
    # Export (GDPR Art. 20 — data portability)
    # ------------------------------------------------------------------
    async def export_user_data(self, user_id: str) -> dict:
        """Export all data associated with a user.

        Returns a structured dict: ``{table_name: [row_dicts, ...]}``
        """
        uid_hash = _hash_uid(user_id)
        logger.info("dsar_export_start", user_id_hash=uid_hash)

        result: dict[str, list[dict]] = {}
        errors: list[str] = []

        session = await self._handler.get_session()
        try:
            for spec in self._handler.table_specs():
                try:
                    stmt = text(
                        f"SELECT * FROM {spec.table_name} "  # noqa: S608
                        f"WHERE {spec.user_column} = :uid"
                    ).bindparams(uid=user_id)
                    rows = (await session.execute(stmt)).mappings().all()
                    result[spec.table_name] = [dict(r) for r in rows]
                except Exception as exc:
                    errors.append(f"{spec.table_name}: {exc}")
                    logger.error(
                        "dsar_export_table_error",
                        table=spec.table_name,
                        user_id_hash=uid_hash,
                        error=str(exc),
                    )
        finally:
            await session.close()

        logger.info(
            "dsar_export_done",
            user_id_hash=uid_hash,
            tables=len(result),
            errors=len(errors),
        )
        return result

    # ------------------------------------------------------------------
    # Delete (GDPR Art. 17 — right to erasure)
    # ------------------------------------------------------------------
    async def delete_user_data(
        self, user_id: str, *, dry_run: bool = True
    ) -> DSARResult:
        """Delete all data associated with a user.

        Args:
            user_id: The user's open_id.
            dry_run: If True, only report what would be deleted.

        Returns:
            DSARResult with counts of affected records per table.
        """
        uid_hash = _hash_uid(user_id)
        action = "delete_dry_run" if dry_run else "delete"
        logger.info("dsar_delete_start", user_id_hash=uid_hash, dry_run=dry_run)

        affected: dict[str, int] = {}
        errors: list[str] = []

        # --- Database tables ---
        session = await self._handler.get_session()
        try:
            for spec in self._handler.table_specs():
                try:
                    count = await self._count_or_delete_table(
                        session, spec, user_id, dry_run=dry_run,
                    )
                    affected[spec.table_name] = count
                except Exception as exc:
                    errors.append(f"{spec.table_name}: {exc}")
                    logger.error(
                        "dsar_delete_table_error",
                        table=spec.table_name,
                        user_id_hash=uid_hash,
                        error=str(exc),
                    )

            if not dry_run and not errors:
                await session.commit()
            elif not dry_run and errors:
                # Partial failure: still commit successful deletes
                await session.commit()
        finally:
            await session.close()

        # --- Redis keys ---
        redis_count = 0
        try:
            redis_result = await self._delete_redis_user_data(
                user_id, dry_run=dry_run,
            )
            redis_count = redis_result.get("keys_affected", 0)
        except Exception as exc:
            errors.append(f"redis: {exc}")
            logger.error(
                "dsar_delete_redis_error",
                user_id_hash=uid_hash,
                error=str(exc),
            )

        status = "partial_failure" if errors else "completed"
        result = DSARResult(
            user_id=user_id,
            action=action,
            affected_tables=affected,
            redis_keys_affected=redis_count,
            status=status,
            errors=errors,
        )

        logger.info(
            "dsar_delete_done",
            user_id_hash=uid_hash,
            action=action,
            affected=affected,
            redis_keys=redis_count,
            status=status,
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _count_or_delete_table(
        session: AsyncSession,
        spec: TableSpec,
        user_id: str,
        *,
        dry_run: bool,
    ) -> int:
        """Count matching rows (dry_run) or delete them."""
        if dry_run:
            stmt = text(
                f"SELECT count(*) FROM {spec.table_name} "  # noqa: S608
                f"WHERE {spec.user_column} = :uid"
            ).bindparams(uid=user_id)
            row = (await session.execute(stmt)).scalar_one()
            return int(row)

        if spec.model is not None:
            col = getattr(spec.model, spec.user_column)
            stmt = delete(spec.model).where(col == user_id)
        else:
            stmt = text(
                f"DELETE FROM {spec.table_name} "  # noqa: S608
                f"WHERE {spec.user_column} = :uid"
            ).bindparams(uid=user_id)

        result = await session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def _delete_redis_user_data(
        self, user_id: str, *, dry_run: bool = True
    ) -> dict:
        """Clean up Redis keys associated with a user.

        Uses SCAN (never KEYS) to avoid blocking Redis.
        """
        r = self._handler.get_redis()
        if r is None:
            return {"keys_affected": 0}

        uid_hash = _hash_uid(user_id)
        patterns = self._handler.redis_key_patterns()
        matched_keys: list[str] = []

        for pattern in patterns:
            resolved = pattern.replace("{user_id}", user_id)
            async for key in r.scan_iter(match=resolved, count=100):
                matched_keys.append(key)

        if not dry_run and matched_keys:
            await r.delete(*matched_keys)

        logger.info(
            "dsar_redis_cleanup",
            user_id_hash=uid_hash,
            keys_found=len(matched_keys),
            dry_run=dry_run,
        )
        return {"keys_affected": len(matched_keys)}
