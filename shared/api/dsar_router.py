"""DSAR API Router — mounted by each agent with its own DSARHandler.

All endpoints require ``X-Internal-Key`` authentication.
Every request is audit-logged with a hashed user_id (never plain text).
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from shared.middleware.internal_auth import verify_internal_key
from shared.schemas.dsar import DSARRequest, DSARResult
from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from shared.infra.dsar import DSARService

logger = get_logger("dsar.api")


def _hash_uid(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def create_dsar_router(dsar_service: "DSARService") -> APIRouter:
    """Factory: create a DSAR router bound to an agent-specific DSARService.

    Usage in agent ``main.py``::

        from shared.api.dsar_router import create_dsar_router
        app.include_router(
            create_dsar_router(my_dsar_service),
            dependencies=[Depends(verify_internal_key)],
        )
    """
    router = APIRouter(prefix="/api/dsar", tags=["DSAR"])

    @router.post("/export", response_model=DSARResult)
    async def export_user_data(
        body: DSARRequest,
        _auth: None = Depends(verify_internal_key),
    ) -> DSARResult:
        """Export all user data (GDPR Art. 20 portability)."""
        uid_hash = _hash_uid(body.user_id)
        logger.info(
            "dsar_api_export",
            user_id_hash=uid_hash,
            timestamp=datetime.now(UTC).isoformat(),
        )

        data = await dsar_service.export_user_data(body.user_id)
        record_counts = {table: len(rows) for table, rows in data.items()}

        return DSARResult(
            user_id=body.user_id,
            action="export",
            affected_tables=record_counts,
            redis_keys_affected=0,
            status="completed",
        )

    @router.post("/delete", response_model=DSARResult)
    async def delete_user_data(
        body: DSARRequest,
        confirm: bool = Query(False, description="Set to true to actually delete"),
        _auth: None = Depends(verify_internal_key),
    ) -> DSARResult:
        """Delete all user data.

        - Default (confirm=false): dry-run, returns counts only.
        - confirm=true: actually deletes data.
        """
        dry_run = not confirm
        uid_hash = _hash_uid(body.user_id)
        logger.info(
            "dsar_api_delete",
            user_id_hash=uid_hash,
            dry_run=dry_run,
            timestamp=datetime.now(UTC).isoformat(),
        )

        result = await dsar_service.delete_user_data(body.user_id, dry_run=dry_run)

        logger.info(
            "dsar_api_delete_done",
            user_id_hash=uid_hash,
            action=result.action,
            status=result.status,
            affected=result.affected_tables,
        )
        return result

    return router
