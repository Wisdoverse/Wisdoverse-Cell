"""PMAgent API Schemas"""

from typing import Any, Optional

from pydantic import BaseModel


class PMConfigResponse(BaseModel):
    members: list[dict[str, Any]] = []
    projects: list[dict[str, Any]] = []
    rules: dict[str, str] | list = {}


class ConfigRefreshResponse(BaseModel):
    status: str = "refreshed"


class AlertItem(BaseModel):
    type: str
    task: str = ""
    message: str
    severity: str


class AlertListResponse(BaseModel):
    total: int = 0
    alerts: list[AlertItem] = []


class HealthResponse(BaseModel):
    status: str
    agent: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, bool]


class DecomposeStatusResponse(BaseModel):
    wp_id: int
    project_id: int
    status: str
    assignee_id: Optional[int] = None
    decompose_result: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    approved_by: Optional[str] = None


class DecomposeActionRequest(BaseModel):
    operator: str = ""
    reason: str = ""


class DecomposeActionResponse(BaseModel):
    success: bool
    wp_id: int
    action: str
    message: str = ""
    subject: str = ""
    story_count: int = 0
    task_count: int = 0
