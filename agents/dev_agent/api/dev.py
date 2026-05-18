"""REST API for dev_agent."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from shared.api import raise_dev_agent_not_ready
from shared.utils.logger import get_logger

from ..core.api_use_cases import DevApiUseCase, DevWorkflowApprovalCommand

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
        raise_dev_agent_not_ready()
    return runtime.agent


def get_dev_api_use_case() -> DevApiUseCase:
    return DevApiUseCase(_get_agent())


@router.get("/tasks")
async def list_tasks(dev_api: DevApiUseCase = Depends(get_dev_api_use_case)):
    return await dev_api.list_tasks()


@router.get("/tasks/failed")
async def list_failed_tasks(dev_api: DevApiUseCase = Depends(get_dev_api_use_case)):
    return await dev_api.list_failed_tasks()


@router.get("/tasks/{wp_id}")
async def get_task_status(
    wp_id: int,
    dev_api: DevApiUseCase = Depends(get_dev_api_use_case),
):
    return await dev_api.get_task_status(wp_id)


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    dev_api: DevApiUseCase = Depends(get_dev_api_use_case),
):
    return await dev_api.retry_task(task_id)


@router.post("/tasks/{task_id}/cancel")
async def cancel_workflow(
    task_id: str,
    dev_api: DevApiUseCase = Depends(get_dev_api_use_case),
):
    return await dev_api.cancel_workflow(task_id)


@router.post("/tasks/{task_id}/approve")
async def approve_workflow(
    task_id: str,
    body: ApproveWorkflowRequest | None = None,
    dev_api: DevApiUseCase = Depends(get_dev_api_use_case),
):
    body = body or ApproveWorkflowRequest()
    return await dev_api.approve_workflow(
        DevWorkflowApprovalCommand(
            task_id=task_id,
            operator=body.operator,
            approval_id=body.approval_id,
        )
    )
