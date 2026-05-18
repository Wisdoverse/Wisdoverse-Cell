"""SyncModule HTTP endpoints."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from shared.utils.logger import get_logger

from ..core.api_use_cases import SyncApiUseCase
from ..core.mapping_queries import SyncMappingQueryService
from ..service.agent import get_agent
from .dependencies import get_sync_mapping_query_service
from .schemas import (
    SyncMappingListResponse,
    SyncMappingOut,
    SyncStatusResponse,
    SyncTriggerResponse,
)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])
logger = get_logger("sync_module.api")


def get_sync_api_use_case() -> SyncApiUseCase:
    return SyncApiUseCase(get_agent())


@router.post("/trigger", response_model=SyncTriggerResponse)
async def trigger_sync(sync_api: SyncApiUseCase = Depends(get_sync_api_use_case)):
    """Trigger the compatibility full sync."""
    return _sync_response(await sync_api.trigger_sync())


@router.post("/openproject/trigger", response_model=SyncTriggerResponse)
async def trigger_openproject_sync(
    sync_api: SyncApiUseCase = Depends(get_sync_api_use_case),
):
    """Trigger only the OpenProject-to-Bitable sync boundary."""
    return _sync_response(await sync_api.trigger_openproject_sync())


@router.post("/feishu-bitable/trigger", response_model=SyncTriggerResponse)
async def trigger_feishu_bitable_sync(
    sync_api: SyncApiUseCase = Depends(get_sync_api_use_case),
):
    """Trigger only the Feishu Bitable-to-OpenProject sync boundary."""
    return _sync_response(await sync_api.trigger_feishu_bitable_sync())


def _sync_response(result: dict):
    response = SyncTriggerResponse.model_validate(result)
    if result.get("status") == "failed":
        return JSONResponse(status_code=502, content=response.model_dump())
    return response


@router.get("/status", response_model=SyncStatusResponse)
async def sync_status(sync_api: SyncApiUseCase = Depends(get_sync_api_use_case)):
    """Read sync capability status."""
    return SyncStatusResponse.model_validate(await sync_api.get_status())


@router.get("/mappings", response_model=SyncMappingListResponse)
async def list_mappings(
    queries: SyncMappingQueryService = Depends(get_sync_mapping_query_service),
):
    """List OpenProject-to-Bitable mappings."""
    mappings = await queries.list_mappings()
    items = [SyncMappingOut.model_validate(m) for m in mappings]
    return SyncMappingListResponse(total=len(items), items=items)
