"""
Admin API.

Provides system administration endpoints:
- LLM usage statistics.
- Circuit breaker status.
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
    """LLM usage summary response."""
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
    """Circuit breaker status response."""
    state: str
    failures: int
    failure_threshold: int
    recovery_timeout: int
    last_failure_time: Optional[str]


@router.get("/llm-usage", response_model=LLMUsageSummaryResponse)
async def get_llm_usage(
    date: Optional[str] = Query(
        default=None,
        description="Date in YYYY-MM-DD format. Defaults to today.",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
    agent_id: Optional[str] = Query(
        default=None,
        description="Agent ID filter"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Get LLM usage statistics.

    Returns usage statistics for the selected date, including:
    - Total calls and success/failure distribution.
    - Token usage.
    - Cost statistics.
    - Grouped statistics by agent and task type.
    """
    if date is None:
        date = datetime.now(UTC).strftime("%Y-%m-%d")

    repo = LLMUsageRepository(db)
    summary = await repo.get_daily_summary(date, agent_id)

    return LLMUsageSummaryResponse(**summary)


@router.get("/circuit-breaker", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status():
    """
    Get circuit breaker status.

    Returns the current LLM Gateway circuit breaker state.
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
    Reset the circuit breaker.

    Manually resets the circuit breaker state to CLOSED for operations
    scenarios where the LLM service has recovered.
    """
    llm_gateway.reset_circuit_breaker()

    return {"message": "Circuit breaker reset successfully", "state": "closed"}
