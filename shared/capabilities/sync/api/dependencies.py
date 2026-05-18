"""Sync API dependency wiring."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.mapping_queries import SyncMappingQueryService
from ..db.database import get_db
from ..db.repository import SyncMappingRepository


def get_sync_mapping_query_service(
    db: AsyncSession = Depends(get_db),
) -> SyncMappingQueryService:
    return SyncMappingQueryService(SyncMappingRepository(db))
