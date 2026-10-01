"""Bounded HTTP port to the runtime that owns frozen skill configurations."""

import httpx

from shared.config import settings

from .skill_execution_contract import (
    SkillExecutionResult,
    SkillSelection,
    SkillSelectionRequest,
    verify_selection,
)


class HttpSkillExecutionGateway:
    async def resolve(self, request: SkillSelectionRequest) -> SkillSelection | None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(
                settings.evolution_runtime_url.rstrip("/")
                + "/api/v1/evolution/skill-executions/resolve",
                json=request.model_dump(mode="json"),
                headers={"X-Internal-Key": settings.internal_service_key},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            selection = SkillSelection.model_validate(response.json())
        verify_selection(selection, settings.evolution_deployment_signing_key.get_secret_value())
        if any(getattr(selection, key) != value for key, value in request.model_dump().items()):
            raise ValueError("evolution_skill_selection_subject_mismatch")
        return selection

    async def record(self, result: SkillExecutionResult) -> None:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(
                settings.evolution_runtime_url.rstrip("/")
                + "/api/v1/evolution/skill-executions/results",
                json=result.model_dump(mode="json"),
                headers={"X-Internal-Key": settings.internal_service_key},
            )
            response.raise_for_status()
