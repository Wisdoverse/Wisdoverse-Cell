"""Tests for budget usage event publishing."""

from unittest.mock import AsyncMock

import pytest

from shared.infra.budget_events import publish_budget_usage_recorded
from shared.schemas.event import EventTypes
from shared.schemas.event_payloads import validate_event_payload


@pytest.mark.asyncio
async def test_publish_budget_usage_recorded_emits_valid_event() -> None:
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock(return_value=True)

    event = await publish_budget_usage_recorded(
        company_id="cmp_test",
        usage_id="busg_001",
        budget_id="bud_001",
        cost_usd=0.42,
        model="anthropic/claude-sonnet-4-20250514",
        source_agent_id="requirement-manager",
        input_tokens=120,
        output_tokens=40,
        run_id="run_001",
        trace_id="trace_budget",
        event_bus=event_bus,
    )

    assert event is not None
    assert event.event_type == EventTypes.BUDGET_USAGE_RECORDED
    assert event.source_agent == "requirement-manager"
    assert event.metadata.trace_id == "trace_budget"
    assert event.payload["usage_id"] == "busg_001"
    assert event.payload["cost_usd"] == pytest.approx(0.42)
    assert event.payload["input_tokens"] == 120
    assert event.payload["output_tokens"] == 40
    validate_event_payload(event.event_type, event.payload)
    event_bus.publish.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_publish_budget_usage_recorded_returns_none_when_bus_rejects() -> None:
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock(return_value=False)

    event = await publish_budget_usage_recorded(
        company_id="cmp_test",
        usage_id="busg_001",
        budget_id="bud_001",
        cost_usd=0.42,
        model="tool:agentforge_apply",
        source_agent_id="dev-agent",
        event_bus=event_bus,
    )

    assert event is None


@pytest.mark.asyncio
async def test_publish_budget_usage_recorded_uses_event_publisher_port() -> None:
    event_publisher = AsyncMock()
    event_publisher.publish = AsyncMock(return_value=True)
    event_bus = AsyncMock()
    event_bus.publish = AsyncMock(return_value=True)

    event = await publish_budget_usage_recorded(
        company_id="cmp_test",
        usage_id="busg_002",
        budget_id="bud_002",
        cost_usd=0.12,
        model="tool:budgeted",
        source_agent_id="dev-agent",
        event_bus=event_bus,
        event_publisher=event_publisher,
    )

    assert event is not None
    event_publisher.publish.assert_awaited_once_with(event)
    event_bus.publish.assert_not_awaited()
