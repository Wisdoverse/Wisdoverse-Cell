"""Budget usage event publishing helpers."""

from typing import Any

from shared.schemas.event import Event, EventTypes
from shared.schemas.event_payloads import BudgetUsageRecordedPayload
from shared.utils.logger import get_logger

logger = get_logger("infra.budget_events")


async def publish_budget_usage_recorded(
    *,
    company_id: str,
    usage_id: str,
    budget_id: str,
    cost_usd: float,
    model: str,
    source_agent_id: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    scope: str | None = None,
    scope_id: str | None = None,
    period: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    event_bus: Any | None = None,
) -> Event | None:
    """Publish the budget.usage-recorded EventBus contract.

    Event publication is operational evidence and must not make the already
    persisted budget usage fail.
    """
    payload = BudgetUsageRecordedPayload(
        company_id=company_id,
        usage_id=usage_id,
        budget_id=budget_id,
        scope=scope,
        scope_id=scope_id,
        period=period,
        cost_usd=cost_usd,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        run_id=run_id,
        trace_id=trace_id,
    ).model_dump()
    event = Event.create(
        event_type=EventTypes.BUDGET_USAGE_RECORDED,
        source_agent=source_agent_id,
        payload=payload,
        trace_id=trace_id,
    )

    try:
        if event_bus is None:
            from shared.infra.event_bus import event_bus as default_event_bus

            event_bus = default_event_bus
        published = await event_bus.publish(event)
    except Exception as exc:
        logger.warning(
            "budget_usage_event_publish_failed",
            usage_id=usage_id,
            budget_id=budget_id,
            source_agent_id=source_agent_id,
            error=str(exc),
            error_type=type(exc).__name__,
            trace_id=trace_id,
        )
        return None

    if not published:
        logger.warning(
            "budget_usage_event_publish_rejected",
            usage_id=usage_id,
            budget_id=budget_id,
            source_agent_id=source_agent_id,
            trace_id=trace_id,
        )
        return None

    return event
