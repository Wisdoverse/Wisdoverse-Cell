"""Authenticated runtime receiver for signed skill release commands."""

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, Query

from shared.api import raise_api_error
from shared.config import settings
from shared.evolution.db.database import db_manager
from shared.evolution.db.release_store import (
    SqlAlchemySkillReleaseStore,
)
from shared.evolution.release_contract import SkillReleaseCommand
from shared.middleware.internal_auth import verify_internal_key

from ..core.release_use_cases import SkillReleaseUseCase

router = APIRouter(prefix="/api/v1/evolution", dependencies=[Depends(verify_internal_key)])


async def get_release_use_case() -> AsyncIterator[SkillReleaseUseCase]:
    async with db_manager.session() as session:
        yield SkillReleaseUseCase(
            SqlAlchemySkillReleaseStore(session),
            settings.evolution_deployment_signing_key.get_secret_value(),
        )


@router.post("/skill-releases")
async def apply_skill_release(
    command: SkillReleaseCommand,
    x_evolution_signature: str = Header(default="", alias="X-Evolution-Signature"),
    use_case: SkillReleaseUseCase = Depends(get_release_use_case),
) -> dict[str, Any]:
    try:
        return await use_case.apply(command, x_evolution_signature)
    except ValueError as exc:
        code = str(exc)
        if code == "release_command_id_payload_conflict":
            raise_api_error(status_code=409, code=f"evolution.{code}", message=code)
        if code in {
            "evolution_command_expired",
            "evolution_command_signature_invalid",
            "evolution_deployment_signing_key_required",
        }:
            raise_api_error(status_code=401, code=f"evolution.{code}", message=code)
        if code == "release_company_not_owned":
            raise_api_error(status_code=403, code=f"evolution.{code}", message=code)
        raise_api_error(
            status_code=409 if "conflict" in code or "compare_and_swap" in code else 400,
            code=f"evolution.{code}",
            message=code,
        )


@router.get("/skill-releases/{deployment_id}")
async def get_skill_release(
    deployment_id: str,
    use_case: SkillReleaseUseCase = Depends(get_release_use_case),
    _internal: None = Depends(verify_internal_key),
) -> dict[str, Any]:
    result = await use_case.get(deployment_id)
    if result is None:
        raise_api_error(
            status_code=404,
            code="evolution.skill_release_not_found",
            message="skill_release_not_found",
        )
    return result


@router.get("/skill-configs/{skill_id}/versions/{version}")
async def get_skill_config_version(
    skill_id: str,
    version: str,
    use_case: SkillReleaseUseCase = Depends(get_release_use_case),
    _internal: None = Depends(verify_internal_key),
) -> dict[str, Any]:
    result = await use_case.get_skill_config(skill_id, version)
    if result is None:
        raise_api_error(
            status_code=404,
            code="evolution.skill_config_not_found",
            message="skill_config_not_found",
        )
    return result


@router.get("/skill-release-commands/{command_id}")
async def get_skill_release_command(
    command_id: str,
    skill_id: str | None = Query(default=None, min_length=1, max_length=128),
    baseline_version: int | None = Query(default=None, ge=1),
    candidate_version: int | None = Query(default=None, ge=1),
    use_case: SkillReleaseUseCase = Depends(get_release_use_case),
    _internal: None = Depends(verify_internal_key),
) -> dict[str, Any]:
    supplied = [skill_id is not None, baseline_version is not None, candidate_version is not None]
    if any(supplied) and not all(supplied):
        raise_api_error(
            status_code=422,
            code="evolution.incomplete_release_lookup",
            message="incomplete_release_lookup",
        )
    if skill_id is None:
        result = await use_case.get_command(command_id)
    else:
        result = await use_case.get_command(
            command_id,
            skill_id=skill_id,
            baseline_version=baseline_version,
            candidate_version=candidate_version,
        )
    if result is None:
        raise_api_error(
            status_code=404,
            code="evolution.skill_release_command_not_found",
            message="skill_release_command_not_found",
        )
    return result
