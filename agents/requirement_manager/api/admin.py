"""
Admin API.

Provides system administration endpoints:
- LLM usage statistics.
- Circuit breaker status.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..core.admin_circuit_breaker import CircuitBreakerAdminUseCase
from ..core.llm_usage_queries import LLMUsageQueryService
from .dependencies import (
    get_circuit_breaker_admin_use_case,
    get_llm_usage_query_service,
)

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
    queries: LLMUsageQueryService = Depends(get_llm_usage_query_service),
):
    """
    Get LLM usage statistics.

    Returns usage statistics for the selected date, including:
    - Total calls and success/failure distribution.
    - Token usage.
    - Cost statistics.
    - Grouped statistics by agent and task type.
    """
    summary = await queries.get_daily_summary(date=date, agent_id=agent_id)

    return LLMUsageSummaryResponse(**summary)


@router.get("/circuit-breaker", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status(
    circuit_breaker: CircuitBreakerAdminUseCase = Depends(
        get_circuit_breaker_admin_use_case
    ),
):
    """
    Get circuit breaker status.

    Returns the current LLM Gateway circuit breaker state.
    """
    status = circuit_breaker.get_status()

    return CircuitBreakerStatusResponse(
        state=status.state,
        failures=status.failures,
        failure_threshold=status.failure_threshold,
        recovery_timeout=status.recovery_timeout,
        last_failure_time=status.last_failure_time,
    )


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(
    circuit_breaker: CircuitBreakerAdminUseCase = Depends(
        get_circuit_breaker_admin_use_case
    ),
):
    """
    Reset the circuit breaker.

    Manually resets the circuit breaker state to CLOSED for operations
    scenarios where the LLM service has recovered.
    """
    circuit_breaker.reset()

    return {"message": "Circuit breaker reset successfully", "state": "closed"}
