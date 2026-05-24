"""BudgetUsage aggregate root and spend-recording policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import BudgetUsage as BudgetUsageRecord
from .budget_amount import BudgetAmount
from .events import ControlPlaneDomainEvent


class InvalidBudgetUsageError(ValueError):
    """Raised when a BudgetUsage record violates spend-recording invariants."""


def budget_token_count(value: int | None, field_name: str) -> int:
    """Return a non-negative integer token count."""
    count = int(value or 0)
    if count < 0:
        raise InvalidBudgetUsageError(f"{field_name}_must_be_non_negative")
    return count


def clean_budget_usage_model(value: Any) -> str:
    """Return the required model/tool identifier for a usage record."""
    cleaned = str(value or "").strip()
    if not cleaned:
        raise InvalidBudgetUsageError("model_required")
    return cleaned


@dataclass(frozen=True, slots=True)
class BudgetUsageRecorded(ControlPlaneDomainEvent):
    """In-memory event raised when model/tool spend is recorded."""

    usage_id: str
    company_id: str
    budget_id: str
    cost_usd: float
    model: str
    input_tokens: int
    output_tokens: int
    run_id: str | None
    trace_id: str | None
    metadata_keys: tuple[str, ...]


@dataclass
class BudgetUsage:
    """BudgetUsage aggregate root for immutable spend evidence."""

    record: BudgetUsageRecord
    _events: list[BudgetUsageRecorded] = field(default_factory=list)

    @classmethod
    def for_recording(cls, record: BudgetUsageRecord) -> BudgetUsage:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @classmethod
    def from_record(cls, record: BudgetUsageRecord) -> BudgetUsage:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @property
    def usage_id(self) -> str:
        return self.record.usage_id

    def mark_recorded(self) -> None:
        """Raise the recorded event after persistence has accepted the row."""
        self._events.append(
            BudgetUsageRecorded(
                usage_id=self.record.usage_id,
                company_id=self.record.company_id,
                budget_id=self.record.budget_id,
                cost_usd=self.record.cost_usd,
                model=self.record.model,
                input_tokens=self.record.input_tokens,
                output_tokens=self.record.output_tokens,
                run_id=self.record.run_id,
                trace_id=self.record.trace_id,
                metadata_keys=tuple(sorted(self.record.metadata)),
            )
        )

    def pull_events(self) -> list[BudgetUsageRecorded]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained

    def _normalize_record(self) -> None:
        self.record = self.record.model_copy(
            update={
                "cost_usd": BudgetAmount.non_negative_usd(
                    self.record.cost_usd
                ).as_float(),
                "model": clean_budget_usage_model(self.record.model),
                "input_tokens": budget_token_count(
                    self.record.input_tokens,
                    "input_tokens",
                ),
                "output_tokens": budget_token_count(
                    self.record.output_tokens,
                    "output_tokens",
                ),
                "metadata": dict(self.record.metadata or {}),
            }
        )


__all__ = [
    "BudgetUsage",
    "BudgetUsageRecorded",
    "InvalidBudgetUsageError",
    "budget_token_count",
    "clean_budget_usage_model",
]
