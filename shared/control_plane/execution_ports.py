"""Application boundary for durable dispatch and cost accounting."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ExecutionTicket:
    execution_id: str
    run_id: str
    owner_id: str
    ceiling_usd: Decimal
    replay: bool = False


class ExecutionGovernanceStore(Protocol):
    async def claim(
        self,
        agent: Any,
        *,
        run_id: str,
        payload: dict[str, Any],
        work_item_id: str | None,
        goal_id: str | None,
        actor_id: str,
        idempotency_key: str,
    ) -> ExecutionTicket: ...

    async def checkpoint(self) -> None: ...

    async def control_action(self, ticket: ExecutionTicket) -> str: ...

    async def mark_uncertain(self, ticket: ExecutionTicket) -> None: ...

    async def settle(
        self, ticket: ExecutionTicket, *, cost_usd: Decimal, failed: bool, estimated: bool = False
    ) -> None: ...
