"""SyncAgent HTTP endpoints."""
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
    """Trigger the compatibility full sync."""
    agent = get_agent()
    result = await agent.trigger_sync(triggered_by="api")
    return _sync_response(result)


@router.post("/openproject/trigger", response_model=SyncTriggerResponse)
async def trigger_openproject_sync():
    """Trigger only the OpenProject-to-Bitable sync boundary."""
    agent = get_agent()
    result = await agent.trigger_openproject_sync(triggered_by="api")
    return _sync_response(result)


@router.post("/feishu-bitable/trigger", response_model=SyncTriggerResponse)
async def trigger_feishu_bitable_sync():
    """Trigger only the Feishu Bitable-to-OpenProject sync boundary."""
    agent = get_agent()
    result = await agent.trigger_feishu_bitable_sync(triggered_by="api")
    return _sync_response(result)


def _sync_response(result: dict):
    response = SyncTriggerResponse(
        status=result.get("status", "completed"),
        total_processed=result.get("total_processed", result.get("processed", 0)),
        errors=result.get("errors", []),
        error=result.get("error"),
    )
    if result.get("status") == "failed":
        return JSONResponse(status_code=502, content=response.model_dump())
    return response


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status():
    """Read sync capability status."""
    agent = get_agent()
    result = await agent.handle_request({"action": "status"})
    return SyncStatusResponse(**result)


@router.get("/mappings", response_model=SyncMappingListResponse)
async def list_mappings(db: AsyncSession = Depends(get_db)):
    """List OpenProject-to-Bitable mappings."""
    repo = SyncMappingRepository(db)
    mappings = await repo.list_all()
    items = [SyncMappingOut.model_validate(m) for m in mappings]
    return SyncMappingListResponse(total=len(items), items=items)
