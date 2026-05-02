"""
Admin API - 管理端点

提供系统管理功能:
- LLM 使用量统计
- 断路器状态
"""
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.infra.llm_gateway import llm_gateway

from ..db.database import get_db
from ..db.repository import LLMUsageRepository

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


class LLMUsageSummaryResponse(BaseModel):
    """LLM 使用量汇总响应"""
    date: str
    total_calls: int
    success_calls: int
    failed_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    avg_latency_ms: int
    by_agent: dict[str, dict]
    by_task_type: dict[str, dict]


class CircuitBreakerStatusResponse(BaseModel):
    """断路器状态响应"""
    state: str
    failures: int
    failure_threshold: int
    recovery_timeout: int
    last_failure_time: Optional[str]


@router.get("/llm-usage", response_model=LLMUsageSummaryResponse)
async def get_llm_usage(
    date: Optional[str] = Query(
        default=None,
        description="日期 (YYYY-MM-DD)，默认为今天",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    agent_id: Optional[str] = Query(
        default=None,
        description="Agent ID 过滤"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    获取 LLM 使用量统计

    返回指定日期的 LLM 调用统计信息，包括:
    - 总调用次数和成功/失败分布
    - Token 使用量
    - 成本统计
    - 按 Agent 和任务类型的分组统计
    """
    if date is None:
        date = datetime.now(UTC).strftime("%Y-%m-%d")

    repo = LLMUsageRepository(db)
    summary = await repo.get_daily_summary(date, agent_id)

    return LLMUsageSummaryResponse(**summary)


@router.get("/circuit-breaker", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status():
    """
    获取断路器状态

    返回 LLM Gateway 断路器的当前状态。
    """
    stats = llm_gateway.get_circuit_breaker_stats()

    return CircuitBreakerStatusResponse(
        state=stats["state"],
        failures=stats["failures"],
        failure_threshold=stats["failure_threshold"],
        recovery_timeout=stats["recovery_timeout"],
        last_failure_time=stats.get("last_failure_time")
    )


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker():
    """
    重置断路器

    手动重置断路器状态为 CLOSED。
    用于运维场景，当确认 LLM 服务已恢复时使用。
    """
    llm_gateway.reset_circuit_breaker()

    return {"message": "Circuit breaker reset successfully", "state": "closed"}
