"""Tests for the BudgetUsage aggregate."""

import pytest

from shared.control_plane.domain.budget_usage import (
    BudgetUsage,
    BudgetUsageRecorded,
    InvalidBudgetUsageError,
    budget_token_count,
)
from shared.control_plane.models import BudgetUsage as BudgetUsageRecord


def test_budget_usage_for_recording_normalizes_record() -> None:
    aggregate = BudgetUsage.for_recording(
        BudgetUsageRecord(
            usage_id="usage_budget_domain",
            company_id="cmp_budget_domain",
            budget_id="bud_budget_domain",
            cost_usd=1.25,
            model="  anthropic/claude-sonnet-4-20250514  ",
            input_tokens=100,
            output_tokens=25,
            metadata={"source": "domain"},
        )
    )

    assert aggregate.record.cost_usd == 1.25
    assert aggregate.record.model == "anthropic/claude-sonnet-4-20250514"
    assert aggregate.record.input_tokens == 100
    assert aggregate.record.output_tokens == 25
    assert aggregate.record.metadata == {"source": "domain"}


def test_budget_usage_requires_model_identifier() -> None:
    with pytest.raises(InvalidBudgetUsageError, match="model_required"):
        BudgetUsage.for_recording(
            BudgetUsageRecord(
                company_id="cmp_budget_domain",
                budget_id="bud_budget_domain",
                cost_usd=0,
                model=" ",
            )
        )


def test_budget_usage_token_count_rejects_negative_values() -> None:
    with pytest.raises(InvalidBudgetUsageError, match="input_tokens_must_be_non_negative"):
        budget_token_count(-1, "input_tokens")


def test_budget_usage_mark_recorded_raises_domain_event() -> None:
    aggregate = BudgetUsage.for_recording(
        BudgetUsageRecord(
            usage_id="usage_budget_domain",
            company_id="cmp_budget_domain",
            budget_id="bud_budget_domain",
            cost_usd=0.42,
            model="tool:agentforge_apply",
            input_tokens=0,
            output_tokens=0,
            run_id="run_budget_domain",
            trace_id="trace_budget_domain",
            metadata={"tool": "agentforge_apply"},
        )
    )

    aggregate.mark_recorded()

    events = aggregate.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, BudgetUsageRecorded)
    assert event.usage_id == "usage_budget_domain"
    assert event.cost_usd == pytest.approx(0.42)
    assert event.model == "tool:agentforge_apply"
    assert event.run_id == "run_budget_domain"
    assert event.trace_id == "trace_budget_domain"
    assert event.metadata_keys == ("tool",)
    assert aggregate.pull_events() == []
