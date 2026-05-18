"""QAAgent API - REST Endpoints"""

from fastapi import APIRouter, Depends, Query

from shared.api import (
    raise_qa_run_detail_failed,
    raise_qa_run_failed,
    raise_qa_run_list_failed,
    raise_qa_run_not_found,
    raise_qa_run_timeout,
    raise_qa_stats_failed,
)
from shared.utils.logger import get_logger

from ..core.api_use_cases import (
    QAApiListRunsFailedError,
    QAApiRunDetailFailedError,
    QAApiRunFailedError,
    QAApiRunNotFoundError,
    QAApiStatsFailedError,
    QAApiTimeoutError,
    QAApiUseCase,
    QAListRunsQuery,
    QAStatsQuery,
    QATriggerRunCommand,
)
from ..service.agent import get_agent
from .schemas import (
    QARunDetailResponse,
    QARunListResponse,
    QARunTriggerRequest,
    QARunTriggerResponse,
    QAStatsResponse,
)

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])
logger = get_logger("qa_agent.api")


def get_qa_api_use_case() -> QAApiUseCase:
    return QAApiUseCase(get_agent())


@router.post(
    "/run",
    response_model=QARunTriggerResponse,
)
async def trigger_run(
    request: QARunTriggerRequest,
    qa_api: QAApiUseCase = Depends(get_qa_api_use_case),
):
    """Trigger a QA acceptance run manually."""
    try:
        return QARunTriggerResponse.model_validate(
            await qa_api.trigger_run(
                QATriggerRunCommand(
                    agent_name=request.agent_name,
                    level=request.level,
                    commit_sha=request.commit_sha,
                    files_changed=request.files_changed,
                    mr_iid=request.mr_iid,
                    gitlab_project_id=request.gitlab_project_id,
                    requested_by=request.requested_by,
                    reason=request.reason,
                )
            )
        )
    except QAApiTimeoutError:
        logger.error("api_run_timeout", agent_name=request.agent_name)
        raise_qa_run_timeout()
    except QAApiRunFailedError as exc:
        logger.error("api_run_error", error=str(exc))
        raise_qa_run_failed(f"QA acceptance run failed: {str(exc)}")


@router.get(
    "/runs",
    response_model=QARunListResponse,
)
async def list_runs(
    agent_name: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    qa_api: QAApiUseCase = Depends(get_qa_api_use_case),
):
    """List QA acceptance run history."""
    try:
        return QARunListResponse.model_validate(
            await qa_api.list_runs(
                QAListRunsQuery(
                    agent_name=agent_name,
                    limit=limit,
                    offset=offset,
                )
            )
        )
    except QAApiListRunsFailedError as exc:
        logger.error("api_list_runs_error", error=str(exc))
        raise_qa_run_list_failed()


@router.get(
    "/runs/{run_id}",
    response_model=QARunDetailResponse,
)
async def get_run_detail(
    run_id: str,
    qa_api: QAApiUseCase = Depends(get_qa_api_use_case),
):
    """Get details for one QA acceptance run."""
    try:
        return QARunDetailResponse.model_validate(await qa_api.get_run_detail(run_id))
    except QAApiRunDetailFailedError as exc:
        logger.error("api_get_run_detail_error", run_id=run_id, error=str(exc))
        raise_qa_run_detail_failed()
    except QAApiRunNotFoundError:
        raise_qa_run_not_found()


@router.get(
    "/stats",
    response_model=QAStatsResponse,
)
async def get_stats(
    agent_name: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    qa_api: QAApiUseCase = Depends(get_qa_api_use_case),
):
    """Get QA run statistics."""
    try:
        return QAStatsResponse.model_validate(
            await qa_api.get_stats(QAStatsQuery(agent_name=agent_name, days=days))
        )
    except QAApiStatsFailedError as exc:
        logger.error("api_get_stats_error", error=str(exc))
        raise_qa_stats_failed()
