"""Pure execution policy: frozen intent, capabilities and bounded money."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ExecutionDenied(ValueError):
    def __init__(self, reason: str, status_code: int = 409) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def bounded_cost(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ExecutionDenied("invalid_execution_cost", 400) from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000"):
        raise ExecutionDenied("invalid_execution_cost", 400)
    return amount.quantize(Decimal("0.000001"))


def intent_hash(agent: Any, payload: dict[str, Any], work_item_id: str | None) -> str:
    """An approval cannot survive changed tools, permissions or parameters."""
    value = {
        "company_id": agent.company_id,
        "agent_id": agent.agent_id,
        "adapter_type": agent.adapter_type,
        "adapter_config": agent.adapter_config,
        "permissions": sorted(agent.permissions or []),
        "budget_policy_id": agent.budget_policy_id,
        "escalation_policy": agent.escalation_policy,
        "work_item_id": work_item_id,
        "input": payload,
    }
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ExecutionDenied("invalid_execution_intent", 400) from exc
    return hashlib.sha256(encoded.encode()).hexdigest()


def authorize_adapter(agent: Any) -> Decimal:
    if agent.status != "active":
        raise ExecutionDenied("agent_not_runnable")
    # Builtin records intent and has no tool capability or external side effect.
    if agent.adapter_type == "builtin":
        return Decimal(0)
    required = {"work.execute", f"adapter:{agent.adapter_type}"}
    action = str((agent.adapter_config or {}).get("action", "wakeup"))
    required.add(f"tool:{action}")
    if not required.issubset(set(agent.permissions or [])):
        raise ExecutionDenied("execution_permission_denied", 403)
    if "max_cost_usd" not in (agent.adapter_config or {}):
        raise ExecutionDenied("execution_cost_ceiling_required", 400)
    return bounded_cost(agent.adapter_config["max_cost_usd"])


def period_start(period: str, now: datetime) -> datetime:
    now = now.astimezone(UTC)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "quarterly":
        return now.replace(
            month=((now.month - 1) // 3) * 3 + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    if period == "total":
        return datetime(1970, 1, 1, tzinfo=UTC)
    raise ExecutionDenied("unsupported_budget_period", 400)
