"""Ports for PJM alert persistence."""

from typing import Protocol


class PJMAlertLogStore(Protocol):
    """Persistence port for alert logging."""

    async def record_alerts(self, alerts: list[dict]) -> None:
        """Persist generated alert records."""
