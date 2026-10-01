"""Retention application boundary; deployed operators explicitly select a batch."""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from .domain.physical_retention import RetentionCommand, RetentionReceipt


class RetentionStore(Protocol):
    async def apply(
        self, command: RetentionCommand, *, request_id: str | None, now: datetime, cutoff: datetime
    ) -> RetentionReceipt: ...


class RetentionUseCase:
    def __init__(self, store: RetentionStore, *, retention_days: int = 90) -> None:
        if not 90 <= retention_days <= 3650:
            raise ValueError("retention_policy_out_of_bounds")
        self._store = store
        self._days = retention_days

    async def execute(
        self, command: RetentionCommand, *, request_id: str | None
    ) -> RetentionReceipt:
        if not command.dry_run and (not request_id or len(request_id) > 48):
            raise ValueError("retention_idempotency_key_required")
        now = datetime.now(UTC)
        return await self._store.apply(
            command, request_id=request_id, now=now, cutoff=now - timedelta(days=self._days)
        )
