"""Unit tests for execution intent and adapter authorization policy."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from shared.control_plane.domain.execution_policy import (
    ExecutionDenied,
    authorize_adapter,
    bounded_cost,
    intent_hash,
    period_start,
)


def agent(**updates):
    values = {
        "company_id": "cmp_one",
        "agent_id": "dev-agent",
        "adapter_type": "http",
        "adapter_config": {"action": "wakeup", "endpoint": "internal", "max_cost_usd": "2.50"},
        "permissions": ["work.execute", "adapter:http", "tool:wakeup"],
        "budget_policy_id": "budget_monthly",
        "status": "active",
        "escalation_policy": {},
    }
    values.update(updates)
    return SimpleNamespace(**values)


@pytest.mark.public
def test_intent_hash_is_canonical_and_binds_role_configuration_and_input():
    original = agent()
    equivalent = agent(permissions=["tool:wakeup", "work.execute", "adapter:http"])
    payload = {"task": {"z": 1, "a": ["x", 2]}}
    digest = intent_hash(original, payload, "work_1")
    assert digest == intent_hash(equivalent, {"task": {"a": ["x", 2], "z": 1}}, "work_1")

    changed = [
        agent(adapter_config={**original.adapter_config, "endpoint": "other"}),
        agent(permissions=["work.execute", "adapter:http"]),
        agent(budget_policy_id="budget_other"),
        agent(adapter_type="queue"),
        agent(escalation_policy={"approval_required": True}),
    ]
    assert all(intent_hash(item, payload, "work_1") != digest for item in changed)
    assert intent_hash(original, {"task": {"z": 1, "a": ["x", 3]}}, "work_1") != digest
    assert intent_hash(original, payload, "work_2") != digest


@pytest.mark.public
@pytest.mark.parametrize(
    "value", [-1, "-0.01", "NaN", "Infinity", float("nan"), float("inf"), 1_000_001]
)
def test_costs_reject_negative_nonfinite_and_over_ceiling_values(value):
    with pytest.raises(ExecutionDenied, match="invalid_execution_cost"):
        bounded_cost(value)


@pytest.mark.public
def test_costs_are_bounded_and_quantized():
    assert bounded_cost("1.2345678") == Decimal("1.234568")
    assert bounded_cost(0) == Decimal("0.000000")


@pytest.mark.public
def test_external_adapter_requires_every_capability_and_a_cost_ceiling():
    assert authorize_adapter(agent()) == Decimal("2.500000")
    for permissions in ([], ["work.execute"], ["adapter:http", "tool:wakeup"]):
        with pytest.raises(ExecutionDenied, match="execution_permission_denied"):
            authorize_adapter(agent(permissions=permissions))
    # A revoked capability takes effect on the next authorization check.
    with pytest.raises(ExecutionDenied, match="execution_permission_denied"):
        authorize_adapter(agent(permissions=["work.execute", "adapter:http"]))
    with pytest.raises(ExecutionDenied, match="execution_cost_ceiling_required"):
        authorize_adapter(agent(adapter_config={"action": "wakeup"}))


@pytest.mark.public
def test_builtin_adapter_is_record_only_zero_cost_and_still_requires_active_role():
    assert authorize_adapter(
        agent(adapter_type="builtin", adapter_config={}, permissions=[])
    ) == Decimal(0)
    with pytest.raises(ExecutionDenied, match="agent_not_runnable"):
        authorize_adapter(agent(adapter_type="builtin", status="disabled"))


@pytest.mark.public
@pytest.mark.parametrize(
    "date, expected",
    [
        (datetime(2026, 3, 31, 23, 59, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
        (datetime(2026, 4, 1, 0, 0, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)),
        (datetime(2026, 12, 31, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC)),
    ],
)
def test_quarterly_period_starts_at_calendar_quarter_boundary(date, expected):
    assert period_start("quarterly", date) == expected
