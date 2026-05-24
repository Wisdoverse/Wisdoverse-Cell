"""Unit tests for budget value objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.budget_amount import BudgetAmount, BudgetWarningThreshold


def test_budget_amount_is_immutable_value_object() -> None:
    amount = BudgetAmount.non_negative_usd(1.25)
    same_value = BudgetAmount.non_negative_usd(1.25)

    assert amount == same_value
    assert amount.as_float() == 1.25
    with pytest.raises(FrozenInstanceError):
        amount.usd = 2.0  # type: ignore[misc]


def test_budget_amount_requires_non_negative_finite_value() -> None:
    assert BudgetAmount.zero().as_float() == 0.0
    assert BudgetAmount.positive_usd(0.01).as_float() == 0.01

    with pytest.raises(ValueError, match="non-negative"):
        BudgetAmount.non_negative_usd(-0.01)
    with pytest.raises(ValueError, match="positive"):
        BudgetAmount.positive_usd(0)
    with pytest.raises(ValueError, match="finite"):
        BudgetAmount.non_negative_usd(float("inf"))


def test_budget_amount_adds_and_compares_totals() -> None:
    current = BudgetAmount.non_negative_usd(8)
    estimate = BudgetAmount.non_negative_usd(3)
    limit = BudgetAmount.positive_usd(10)

    assert current.plus(estimate).as_float() == 11
    assert current.plus(estimate).exceeds(limit)


def test_budget_warning_threshold_is_immutable_ratio() -> None:
    threshold = BudgetWarningThreshold.from_ratio(0.8)

    assert threshold.as_float() == 0.8
    with pytest.raises(FrozenInstanceError):
        threshold.ratio = 0.7  # type: ignore[misc]
    with pytest.raises(ValueError, match="within"):
        BudgetWarningThreshold.from_ratio(0)
    with pytest.raises(ValueError, match="within"):
        BudgetWarningThreshold.from_ratio(1.01)
    with pytest.raises(ValueError, match="finite"):
        BudgetWarningThreshold.from_ratio(float("nan"))
