"""Application boundary for frozen configuration selection and observations."""

from typing import Any, Protocol

from shared.evolution.skill_execution_contract import (
    SkillExecutionResult,
    SkillSelection,
    SkillSelectionRequest,
    verify_selection,
)


class SkillExecutionStore(Protocol):
    async def resolve(self, request: SkillSelectionRequest) -> SkillSelection | None: ...
    async def record(self, result: SkillExecutionResult) -> dict[str, Any]: ...


class SkillExecutionUseCase:
    def __init__(self, store: SkillExecutionStore, secret: str) -> None:
        self._store = store
        self._secret = secret

    async def resolve(self, request: SkillSelectionRequest) -> SkillSelection | None:
        return await self._store.resolve(request)

    async def record(self, result: SkillExecutionResult) -> dict[str, Any]:
        verify_selection(result.selection, self._secret)
        return await self._store.record(result)
