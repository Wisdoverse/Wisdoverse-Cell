"""SyncModule API schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SyncTriggerRequest(BaseModel):
    triggered_by: str = Field(default="manual", description="Trigger source")


class SyncTriggerResponse(BaseModel):
    status: str
    total_processed: int = 0
    errors: list[str] = []
    error: Optional[str] = None


class SyncStatusResponse(BaseModel):
    status: str
    agent_id: str
    capabilities: list[str] = []


class SyncMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    op_work_package_id: int
    feishu_record_id: Optional[str] = None
    op_project_id: Optional[int] = None
    updated_at: Optional[datetime] = None


class SyncMappingListResponse(BaseModel):
    total: int
    items: list[SyncMappingOut]


class HealthResponse(BaseModel):
    status: str
    agent: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]
