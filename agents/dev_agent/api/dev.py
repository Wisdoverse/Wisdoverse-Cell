"""REST API for dev_agent."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from shared.utils.logger import get_logger

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])
logger = get_logger("dev_agent.api")


class ApproveWorkflowRequest(BaseModel):
    model_config = ConfigDict(strict=False)

    operator: str = ""
    approval_id: str | None = None


def _get_agent():
    from ..app.main import app

    runtime = getattr(app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Agent not ready")
    return runtime.agent


@router.get("/tasks")
async def list_tasks():
    agent = _get_agent()
    return await agent.handle_request({"action": "list_active_workflows"})


@router.get("/tasks/failed")
async def list_failed_tasks():
    agent = _get_agent()
    return await agent.handle_request({"action": "list_failed"})


@router.get("/tasks/{wp_id}")
async def get_task_status(wp_id: int):
    agent = _get_agent()
    return await agent.handle_request({"action": "get_task_status", "wp_id": wp_id})


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    agent = _get_agent()
    return await agent.handle_request({"action": "retry_task", "task_id": task_id})


@router.post("/tasks/{task_id}/cancel")
async def cancel_workflow(task_id: str):
    agent = _get_agent()
    return await agent.handle_request({"action": "cancel_workflow", "task_id": task_id})


@router.post("/tasks/{task_id}/approve")
async def approve_workflow(task_id: str, body: ApproveWorkflowRequest | None = None):
    agent = _get_agent()
    request = {"action": "approve_workflow", "task_id": task_id}
    if body is not None:
        if body.operator:
            request["approved_by"] = body.operator
        if body.approval_id:
            request["approval_id"] = body.approval_id
    return await agent.handle_request(request)
