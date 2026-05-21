"""Application use cases for Dev readiness checks."""
from __future__ import annotations

from typing import Any

from .health_ports import DevHealthStore


class DevHealthUseCase:
    """Build Dev readiness responses outside the service shell."""

    def __init__(
        self,
        *,
        health_store: DevHealthStore | None,
        repository_available: bool,
        notifier: Any,
        forge: Any,
        gitlab_client: Any,
        agentforge_required: bool,
        gitlab_required: bool,
    ) -> None:
        self._health_store = health_store
        self._repository_available = repository_available
        self._notifier = notifier
        self._forge = forge
        self._gitlab_client = gitlab_client
        self._agentforge_required = agentforge_required
        self._gitlab_required = gitlab_required

    async def check(self) -> dict[str, bool]:
        checks = {
            "database": await self._database_ready(),
            "notifier": self._notifier is not None,
        }
        if self._agentforge_required:
            checks["agentforge_client"] = self._forge is not None
        if self._gitlab_required:
            checks["gitlab_client"] = self._gitlab_client is not None
        return checks

    async def _database_ready(self) -> bool:
        if self._health_store is not None:
            return await self._health_store.is_database_ready()
        return self._repository_available
