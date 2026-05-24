"""BudgetPolicy aggregate root and status policy.

Budget policy status values gate operator-visible conflict behavior:
only one active policy may exist for a company/scope/period tuple.
Keep the vocabulary here so API validation, use cases, and adapters do
not duplicate raw status strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..models import BudgetPolicy as BudgetPolicyRecord
from ..models import BudgetScope
from .budget_amount import BudgetAmount, BudgetWarningThreshold
from .events import ControlPlaneDomainEvent
from .services import ControlPlaneDomainService
from .state_machine import ControlPlaneStateMachine


class BudgetPolicyStatus(StrEnum):
    """Published Control Plane status vocabulary for durable budget policies."""

    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


BUDGET_POLICY_STATUS_ACTIVE = BudgetPolicyStatus.ACTIVE.value
BUDGET_POLICY_STATUS_PAUSED = BudgetPolicyStatus.PAUSED.value
BUDGET_POLICY_STATUS_ARCHIVED = BudgetPolicyStatus.ARCHIVED.value

BUDGET_POLICY_STATUSES = frozenset(
    {
        BUDGET_POLICY_STATUS_ACTIVE,
        BUDGET_POLICY_STATUS_PAUSED,
        BUDGET_POLICY_STATUS_ARCHIVED,
    }
)


class InvalidBudgetPolicyError(ValueError):
    """Raised when a BudgetPolicy record violates policy invariants."""


class InvalidBudgetPolicyStatusError(ValueError):
    """Raised when a BudgetPolicy status is outside the published vocabulary."""


class InvalidBudgetPolicyTransitionError(ValueError):
    """Raised when a BudgetPolicy status transition is not allowed."""


class BudgetPolicyConflictError(ValueError):
    """Raised when two active budget policies target the same scope."""

    def __init__(self, budget_id: str) -> None:
        super().__init__(budget_id)
        self.budget_id = budget_id


def normalize_budget_policy_status(status: str) -> str:
    """Return the canonical status spelling used by control-plane budgets."""
    return status.strip().lower()


def budget_policy_status(value: BudgetPolicyStatus | str | None) -> BudgetPolicyStatus | None:
    """Return a typed BudgetPolicyStatus from enum/string input."""
    if value is None:
        return None
    if isinstance(value, BudgetPolicyStatus):
        return value
    try:
        return BudgetPolicyStatus(normalize_budget_policy_status(str(value)))
    except ValueError as exc:
        raise InvalidBudgetPolicyStatusError(str(value)) from exc


def is_budget_policy_status(status: str) -> bool:
    """True when `status` is part of the BudgetPolicy published vocabulary."""
    return normalize_budget_policy_status(status) in BUDGET_POLICY_STATUSES


def is_active_budget_policy_status(status: str | None) -> bool:
    """True when `status` should participate in active-policy conflicts."""
    return (
        status is not None and normalize_budget_policy_status(status) == BUDGET_POLICY_STATUS_ACTIVE
    )


class BudgetPolicyConflictPolicy(ControlPlaneDomainService):
    """Domain service for active budget-policy uniqueness rules."""

    __slots__ = ()

    def requires_unique_active_policy(
        self,
        status: BudgetPolicyStatus | str | None,
    ) -> bool:
        """True when a budget policy status must be checked for conflicts."""
        if isinstance(status, BudgetPolicyStatus):
            return status == BudgetPolicyStatus.ACTIVE
        return is_active_budget_policy_status(status)

    def ensure_no_active_conflict(
        self,
        *,
        existing: BudgetPolicyRecord | None,
        current_budget_id: str | None = None,
    ) -> None:
        """Raise when an existing active policy conflicts with this command."""
        if existing is not None and existing.budget_id != current_budget_id:
            raise BudgetPolicyConflictError(existing.budget_id)


VALID_TRANSITIONS: dict[BudgetPolicyStatus, frozenset[BudgetPolicyStatus]] = {
    BudgetPolicyStatus.ACTIVE: frozenset(
        {
            BudgetPolicyStatus.PAUSED,
            BudgetPolicyStatus.ARCHIVED,
        }
    ),
    BudgetPolicyStatus.PAUSED: frozenset(
        {
            BudgetPolicyStatus.ACTIVE,
            BudgetPolicyStatus.ARCHIVED,
        }
    ),
    BudgetPolicyStatus.ARCHIVED: frozenset(),
}

STATE_MACHINE = ControlPlaneStateMachine.from_transitions(VALID_TRANSITIONS)

TERMINAL_STATUSES: frozenset[BudgetPolicyStatus] = STATE_MACHINE.terminal_states


def _record_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _scope_id_for_policy(scope: BudgetScope | str, scope_id: str | None) -> str | None:
    scope_value = _record_value(scope)
    cleaned_scope_id = str(scope_id).strip() if scope_id is not None else None
    if scope_value == BudgetScope.COMPANY.value:
        if cleaned_scope_id:
            raise InvalidBudgetPolicyError("company_scope_id_forbidden")
        return None
    if not cleaned_scope_id:
        raise InvalidBudgetPolicyError("scope_id_required")
    return cleaned_scope_id


def _clean_model_allowlist(values: list[str] | tuple[str, ...]) -> list[str]:
    return [cleaned for value in values if (cleaned := str(value).strip())]


@dataclass(frozen=True, slots=True)
class BudgetPolicyCreated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when a BudgetPolicy is created."""

    budget_id: str
    company_id: str
    scope: str
    scope_id: str | None
    period: str
    limit_usd: float
    warning_threshold: float
    status: BudgetPolicyStatus
    model_allowlist: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BudgetPolicyUpdated(ControlPlaneDomainEvent):
    """PII-safe in-memory event raised when a BudgetPolicy is updated."""

    budget_id: str
    company_id: str
    scope: str
    scope_id: str | None
    period: str
    from_status: BudgetPolicyStatus
    to_status: BudgetPolicyStatus
    changed_fields: tuple[str, ...]


@dataclass
class BudgetPolicy:
    """BudgetPolicy aggregate root for spend-governance records."""

    record: BudgetPolicyRecord
    _events: list[BudgetPolicyCreated | BudgetPolicyUpdated] = field(default_factory=list)

    @classmethod
    def for_creation(cls, record: BudgetPolicyRecord) -> BudgetPolicy:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @classmethod
    def from_record(cls, record: BudgetPolicyRecord) -> BudgetPolicy:
        aggregate = cls(record=record)
        aggregate._normalize_record()
        return aggregate

    @property
    def budget_id(self) -> str:
        return self.record.budget_id

    @property
    def status(self) -> BudgetPolicyStatus:
        status = budget_policy_status(self.record.status)
        if status is None:
            raise InvalidBudgetPolicyStatusError(
                f"BudgetPolicy {self.budget_id}: missing status"
            )
        return status

    @property
    def is_terminal(self) -> bool:
        """True when no further budget-policy lifecycle transition is allowed."""
        return STATE_MACHINE.is_terminal(self.status)

    def apply_update(
        self,
        *,
        limit_usd: float | None = None,
        warning_threshold: float | None = None,
        status: str | None = None,
        model_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        changed_fields: list[str],
    ) -> None:
        """Apply a validated budget-policy update to the aggregate record."""
        previous_status = self.status
        update_values: dict[str, Any] = {}
        if limit_usd is not None:
            update_values["limit_usd"] = BudgetAmount.positive_usd(limit_usd).as_float()
        if warning_threshold is not None:
            update_values["warning_threshold"] = (
                BudgetWarningThreshold.from_ratio(warning_threshold).as_float()
            )
        if status is not None:
            update_values["status"] = self._transition_status(status).value
        if model_allowlist is not None:
            update_values["model_allowlist"] = _clean_model_allowlist(model_allowlist)
        if metadata is not None:
            update_values["metadata"] = dict(metadata)

        if update_values:
            self.record = self.record.model_copy(update=update_values)
            self._normalize_record()

        self._events.append(
            BudgetPolicyUpdated(
                budget_id=self.record.budget_id,
                company_id=self.record.company_id,
                scope=_record_value(self.record.scope),
                scope_id=self.record.scope_id,
                period=_record_value(self.record.period),
                from_status=previous_status,
                to_status=self.status,
                changed_fields=tuple(sorted(changed_fields)),
            )
        )

    def mark_created(self) -> None:
        """Raise the creation event after persistence has accepted the record."""
        self._events.append(
            BudgetPolicyCreated(
                budget_id=self.record.budget_id,
                company_id=self.record.company_id,
                scope=_record_value(self.record.scope),
                scope_id=self.record.scope_id,
                period=_record_value(self.record.period),
                limit_usd=self.record.limit_usd,
                warning_threshold=self.record.warning_threshold,
                status=self.status,
                model_allowlist=tuple(self.record.model_allowlist),
            )
        )

    def pull_events(self) -> list[BudgetPolicyCreated | BudgetPolicyUpdated]:
        """Drain raised domain events for audit/outbox collection."""
        drained = list(self._events)
        self._events.clear()
        return drained

    def _transition_status(self, target: BudgetPolicyStatus | str) -> BudgetPolicyStatus:
        target_status = budget_policy_status(target)
        if target_status is None:
            raise InvalidBudgetPolicyStatusError(
                f"BudgetPolicy {self.budget_id}: missing transition target"
            )
        if target_status == self.status:
            return target_status
        STATE_MACHINE.ensure_can_transition(
            self.status,
            target_status,
            subject=f"BudgetPolicy {self.budget_id}",
            error_type=InvalidBudgetPolicyTransitionError,
        )
        return target_status

    def _normalize_record(self) -> None:
        scope_id = _scope_id_for_policy(self.record.scope, self.record.scope_id)
        self.record = self.record.model_copy(
            update={
                "scope_id": scope_id,
                "limit_usd": BudgetAmount.positive_usd(self.record.limit_usd).as_float(),
                "warning_threshold": BudgetWarningThreshold.from_ratio(
                    self.record.warning_threshold
                ).as_float(),
                "status": self.status.value,
                "model_allowlist": _clean_model_allowlist(self.record.model_allowlist),
                "metadata": dict(self.record.metadata or {}),
            }
        )


__all__ = [
    "BUDGET_POLICY_STATUS_ACTIVE",
    "BUDGET_POLICY_STATUS_ARCHIVED",
    "BUDGET_POLICY_STATUS_PAUSED",
    "BUDGET_POLICY_STATUSES",
    "BudgetPolicy",
    "BudgetPolicyConflictError",
    "BudgetPolicyConflictPolicy",
    "BudgetPolicyCreated",
    "BudgetPolicyStatus",
    "BudgetPolicyUpdated",
    "InvalidBudgetPolicyError",
    "InvalidBudgetPolicyStatusError",
    "InvalidBudgetPolicyTransitionError",
    "STATE_MACHINE",
    "TERMINAL_STATUSES",
    "VALID_TRANSITIONS",
    "budget_policy_status",
    "is_active_budget_policy_status",
    "is_budget_policy_status",
    "normalize_budget_policy_status",
]
