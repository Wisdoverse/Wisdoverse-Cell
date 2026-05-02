"""QAAgent API - REST Endpoints"""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from shared.utils.logger import get_logger

from ..models.schemas import QARunRequest
from ..service.agent import get_agent
from .schemas import (
    QARunDetailResponse,
    QARunListItem,
    QARunListResponse,
    QARunTriggerRequest,
    QARunTriggerResponse,
    QAStatsResponse,
)

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])
logger = get_logger("qa_agent.api")


@router.post(
    "/run",
    response_model=QARunTriggerResponse,
)
async def trigger_run(request: QARunTriggerRequest):
    """手动触发 QA 验收运行"""
    agent = get_agent()

    run_req = QARunRequest(
        agent_name=request.agent_name,
        level=request.level,
        commit_sha=request.commit_sha,
        files_changed=request.files_changed,
        mr_iid=request.mr_iid,
        gitlab_project_id=request.gitlab_project_id,
        trigger="manual",  # 显式标为 manual
        requested_by=request.requested_by,
        reason=request.reason,
    )

    try:
        # 使用 asyncio.wait_for 以防 agent 内部超时逻辑失效
        # timeout 取自 settings 最好，但这里我们依赖 run_acceptance 内部的超时控制
        result = await agent.run_acceptance(run_req)

        # 映射 L0 状态到 API 状态
        status_map = {
            "PASS": "passed",
            "FAIL": "failed",
            "WARN": "warn",
            "ERROR": "error",
        }
        status = status_map.get(result.summary.l0_gate, "error")

        # run_id and notification_summary are injected by agent.run_acceptance

        return QARunTriggerResponse(
            run_id=result.run_id,
            status=status,
            agent_name=request.agent_name,
            level=request.level,
            summary=result.summary,
            duration_seconds=result.duration_seconds,
            notification_summary=result.notification_summary,
        )
    except asyncio.TimeoutError:
        logger.error("api_run_timeout", agent_name=request.agent_name)
        raise HTTPException(status_code=504, detail="验收运行超时")
    except Exception as e:
        logger.error("api_run_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"验收运行失败: {str(e)}")


@router.get(
    "/runs",
    response_model=QARunListResponse,
)
async def list_runs(
    agent_name: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """查询 QA 验收历史列表"""
    agent = get_agent()
    try:
        runs_data = await agent.list_runs(
            agent_name=agent_name,
            limit=limit,
            offset=offset,
        )

        items = []
        for r in runs_data:
            items.append(
                QARunListItem(
                    run_id=r["id"],
                    agent_name=r["agent_name"],
                    commit_sha=r.get("commit_sha"),
                    mr_iid=r.get("mr_iid"),
                    trigger=r["trigger"],
                    l0_status=r["l0_status"],
                    l1_status=r["l1_status"],
                    total_checks=r["total_checks"],
                    duration_seconds=r["duration_seconds"],
                    created_at=r["created_at"],
                )
            )

        # Note: 这里的 total 可能是分页后的，如果 BaseAgent.list_runs 支持 count 的话更好。
        # 暂时按 items 长度返回，或者从 agent 获取更多元数据。
        return QARunListResponse(total=len(items), items=items)
    except Exception as e:
        logger.error("api_list_runs_error", error=str(e))
        raise HTTPException(status_code=500, detail="获取运行列表失败")


@router.get(
    "/runs/{run_id}",
    response_model=QARunDetailResponse,
)
async def get_run_detail(run_id: str):
    """查询单次验收运行详情"""
    agent = get_agent()
    try:
        run = await agent.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="验收记录不存在")

        return QARunDetailResponse(
            run_id=run["id"],
            agent_name=run["agent_name"],
            commit_sha=run.get("commit_sha"),
            files_changed=run.get("files_changed", []),
            trigger=run["trigger"],
            level=run["level"],
            summary=run["summary"],
            findings=run.get("findings", []),
            raw_report=run["raw_report"],
            report_markdown=run.get("report_markdown"),
            notification_summary=run.get("notification_summary", {}),
            created_at=run["created_at"],
            completed_at=run.get("completed_at"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("api_get_run_detail_error", run_id=run_id, error=str(e))
        raise HTTPException(status_code=500, detail="获取运行详情失败")


@router.get(
    "/stats",
    response_model=QAStatsResponse,
)
async def get_stats(
    agent_name: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
):
    """获取 QA 运行统计数据"""
    agent = get_agent()
    try:
        stats = await agent.get_stats(agent_name=agent_name, days=days)
        return QAStatsResponse(
            agent_name=stats.agent_name,
            days=stats.days,
            total_runs=stats.total_runs,
            pass_runs=stats.pass_runs,
            warn_runs=stats.warn_runs,
            failed_runs=stats.failed_runs,
            l0_fail_rate=stats.l0_fail_rate,
            avg_duration_seconds=stats.avg_duration_seconds,
            top_l0_failures=stats.top_l0_failures,
            top_l1_warnings=stats.top_l1_warnings,
        )
    except Exception as e:
        logger.error("api_get_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail="获取统计数据失败")
