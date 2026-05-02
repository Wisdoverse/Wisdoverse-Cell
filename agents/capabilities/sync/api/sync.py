"""SyncAgent API - 同步相关 HTTP 端点"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..db.database import get_db
from ..db.repository import SyncMappingRepository
from ..service.agent import get_agent
from .schemas import (
    SyncMappingListResponse,
    SyncMappingOut,
    SyncStatusResponse,
    SyncTriggerResponse,
)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])
logger = get_logger("sync_agent.api")


@router.post("/trigger", response_model=SyncTriggerResponse)
async def trigger_sync():
    """手动触发同步"""
    agent = get_agent()
    result = await agent.trigger_sync(triggered_by="api")
    response = SyncTriggerResponse(
        status=result.get("status", "completed"),
        total_processed=result.get("total_processed", 0),
        errors=result.get("errors", []),
        error=result.get("error"),
    )
    if result.get("status") == "failed":
        return JSONResponse(status_code=502, content=response.model_dump())
    return response


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status():
    """获取同步状态"""
    agent = get_agent()
    result = await agent.handle_request({"action": "status"})
    return SyncStatusResponse(**result)


@router.get("/mappings", response_model=SyncMappingListResponse)
async def list_mappings(db: AsyncSession = Depends(get_db)):
    """列出所有同步映射"""
    repo = SyncMappingRepository(db)
    mappings = await repo.list_all()
    items = [SyncMappingOut.model_validate(m) for m in mappings]
    return SyncMappingListResponse(total=len(items), items=items)
