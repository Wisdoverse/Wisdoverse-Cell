"""Card-operation aggregate for chat-agent operation logs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class CardOperationResult(StrEnum):
    """Result values for one Feishu card operation log."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"


class InvalidCardOperationError(ValueError):
    """Raised when a card-operation log violates domain invariants."""


def coerce_card_operation_result(
    value: CardOperationResult | str,
) -> CardOperationResult:
    """Normalize persisted or inbound result values into the domain enum."""
    if isinstance(value, CardOperationResult):
        return value
    try:
        return CardOperationResult(value)
    except ValueError as exc:
        allowed = ", ".join(result.value for result in CardOperationResult)
        raise ValueError(
            f"unknown card-operation result {value!r}; must be one of {allowed}"
        ) from exc


def _extract_assignee(fields: dict[str, Any]) -> str:
    dri = fields.get("DRI (负责人)")
    if isinstance(dri, list) and dri:
        first = dri[0]
        if isinstance(first, dict):
            return str(first.get("name", "") or first.get("text", ""))
    return ""


@dataclass(frozen=True, slots=True)
class CardOperationLogged:
    """In-memory domain event raised when a card operation is recorded."""

    user_id: str
    action: str
    result: CardOperationResult
    table_id: str
    record_id: str


@dataclass(slots=True)
class CardOperationLogEntry:
    """Aggregate root for one chat-agent card-operation log record."""

    user_id: str
    user_name: str
    action: str
    result: CardOperationResult | str = CardOperationResult.PENDING
    table_id: str = ""
    record_id: str = ""
    assignee_name: str = ""
    fields_snapshot: str = "{}"
    error_message: str = ""
    pending_events: list[CardOperationLogged] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.action:
            raise InvalidCardOperationError("card-operation log requires action")
        self.result = coerce_card_operation_result(self.result)
        if self.result == CardOperationResult.FAILED and not self.error_message:
            raise InvalidCardOperationError(
                "failed card-operation logs require error_message"
            )
        if not self.fields_snapshot:
            self.fields_snapshot = "{}"

    @classmethod
    def recorded(
        cls,
        *,
        user_id: str,
        user_name: str,
        action: str,
        result: CardOperationResult | str,
        table_id: str = "",
        record_id: str = "",
        fields: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> "CardOperationLogEntry":
        """Create a log entry from operation fields and raise its domain event."""
        entry = cls(
            user_id=user_id,
            user_name=user_name,
            action=action,
            result=result,
            table_id=table_id,
            record_id=record_id,
            assignee_name=_extract_assignee(fields or {}),
            fields_snapshot=(
                json.dumps(fields, ensure_ascii=False) if fields else "{}"
            ),
            error_message=error_message,
        )
        entry.pending_events.append(
            CardOperationLogged(
                user_id=entry.user_id,
                action=entry.action,
                result=entry.result,
                table_id=entry.table_id,
                record_id=entry.record_id,
            )
        )
        return entry

    def pull_events(self) -> list[CardOperationLogged]:
        """Drain pending domain events."""
        events = list(self.pending_events)
        self.pending_events.clear()
        return events


__all__ = [
    "CardOperationLogEntry",
    "CardOperationLogged",
    "CardOperationResult",
    "InvalidCardOperationError",
    "coerce_card_operation_result",
]
