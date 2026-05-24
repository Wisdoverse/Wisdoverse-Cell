"""Budget value objects for Control Plane cost policies."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True, order=True)
class BudgetAmount:
    """Immutable USD amount used by budget policies and usage records."""

    usd: float

    def __post_init__(self) -> None:
        value = float(self.usd)
        if not isfinite(value):
            raise ValueError("budget amount must be finite")
        if value < 0:
            raise ValueError("budget amount must be non-negative")
        object.__setattr__(self, "usd", value)

    @classmethod
    def zero(cls) -> BudgetAmount:
        return cls(0.0)

    @classmethod
    def non_negative_usd(cls, value: float) -> BudgetAmount:
        return cls(value)

    @classmethod
    def positive_usd(cls, value: float) -> BudgetAmount:
        amount = cls(value)
        if amount.usd <= 0:
            raise ValueError("budget amount must be positive")
        return amount

    def plus(self, other: BudgetAmount) -> BudgetAmount:
        return BudgetAmount(self.usd + other.usd)

    def exceeds(self, other: BudgetAmount) -> bool:
        return self.usd > other.usd

    def as_float(self) -> float:
        return self.usd


@dataclass(frozen=True, slots=True)
class BudgetWarningThreshold:
    """Immutable ratio used to warn before a budget is exhausted."""

    ratio: float

    def __post_init__(self) -> None:
        value = float(self.ratio)
        if not isfinite(value):
            raise ValueError("budget warning threshold must be finite")
        if value <= 0 or value > 1:
            raise ValueError("budget warning threshold must be within (0, 1]")
        object.__setattr__(self, "ratio", value)

    @classmethod
    def from_ratio(cls, value: float) -> BudgetWarningThreshold:
        return cls(value)

    def as_float(self) -> float:
        return self.ratio


__all__ = [
    "BudgetAmount",
    "BudgetWarningThreshold",
]
