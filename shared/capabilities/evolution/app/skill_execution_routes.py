"""Internal versioned configuration/execution evidence HTTP interface."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends

from shared.api import raise_api_error
from shared.config import settings
from shared.evolution.db.database import db_manager
from shared.evolution.db.skill_execution_store import SqlAlchemySkillExecutionStore
from shared.evolution.skill_execution_contract import (
    SkillExecutionResult,
    SkillSelection,
    SkillSelectionRequest,
)
from shared.middleware.internal_auth import verify_internal_key

from ..core.skill_execution import SkillExecutionUseCase

router = APIRouter(
    prefix="/api/v1/evolution/skill-executions", dependencies=[Depends(verify_internal_key)]
)


async def get_skill_execution() -> AsyncIterator[SkillExecutionUseCase]:
    async with db_manager.session() as session:
        secret = settings.evolution_deployment_signing_key.get_secret_value()
        yield SkillExecutionUseCase(SqlAlchemySkillExecutionStore(session, secret), secret)


@router.post("/resolve", response_model=SkillSelection)
async def resolve(
    request: SkillSelectionRequest, use_case: SkillExecutionUseCase = Depends(get_skill_execution)
) -> SkillSelection:
    try:
        result = await use_case.resolve(request)
    except ValueError as exc:
        raise_api_error(status_code=409, code="evolution.skill_selection_failed", message=str(exc))
    if result is None:
        raise_api_error(
            status_code=404,
            code="evolution.governed_skill_not_found",
            message="governed_skill_not_found",
        )
    return result


@router.post("/results")
async def record(
    result: SkillExecutionResult, use_case: SkillExecutionUseCase = Depends(get_skill_execution)
) -> dict[str, Any]:
    try:
        return await use_case.record(result)
    except ValueError as exc:
        raise_api_error(status_code=409, code="evolution.skill_result_failed", message=str(exc))
