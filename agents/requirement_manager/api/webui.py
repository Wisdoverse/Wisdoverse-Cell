"""WebUI compatibility API surface for operator-owned agent settings."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from shared.config import settings
from shared.control_plane.agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    clean_system_prompt,
    clean_updated_by,
    ensure_prompt_config_target,
    get_or_default_prompt_config,
    prompt_config_to_dict,
)
from shared.control_plane.database import control_plane_db_manager
from shared.control_plane.models import AuditEvent, CompanyContext
from shared.control_plane.repository import ControlPlaneRepository
from shared.schemas.event import EventTypes

router = APIRouter(prefix="/api/v1", tags=["webui"])


class AgentPromptConfigRequest(BaseModel):
    system_prompt: str = Field(default="", max_length=AGENT_PROMPT_MAX_LENGTH)
    updated_by: str = Field(default="webui", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def _clean_system_prompt(cls, value: Any) -> str:
        return clean_system_prompt(value)

    @field_validator("updated_by", mode="before")
    @classmethod
    def _clean_updated_by(cls, value: Any) -> str:
        return clean_updated_by(value)


async def _ensure_company(repo: ControlPlaneRepository, company_id: str) -> None:
    if await repo.get_company(company_id) is not None:
        return
    await repo.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


@router.get("/agents/{agent_id}/prompt-config")
async def get_agent_prompt_config(
    agent_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Return the persisted system-prompt override for an agent detail page."""

    resolved_company_id = company_id or settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        try:
            return await get_or_default_prompt_config(
                repo,
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent_not_found") from exc


@router.put("/agents/{agent_id}/prompt-config")
async def update_agent_prompt_config(
    agent_id: str,
    body: AgentPromptConfigRequest,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Persist a system-prompt override used by deployed agent runtime code."""

    resolved_company_id = company_id or settings.control_plane_company_id
    async with control_plane_db_manager.session() as session:
        repo = ControlPlaneRepository(session)
        await _ensure_company(repo, resolved_company_id)
        try:
            await ensure_prompt_config_target(
                repo,
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="agent_not_found") from exc
        row = await repo.upsert_agent_prompt_config(
            company_id=resolved_company_id,
            agent_id=agent_id,
            system_prompt=body.system_prompt,
            updated_by=body.updated_by,
            metadata=body.metadata,
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.AGENT_PROMPT_CONFIG_UPDATED,
                target_type="agent_prompt_config",
                target_id=agent_id,
                actor_type="user",
                actor_id=body.updated_by,
                detail={
                    "agent_id": agent_id,
                    "prompt_length": len(body.system_prompt),
                    "metadata_keys": sorted(body.metadata.keys()),
                },
            )
        )
        return prompt_config_to_dict(
            row,
            company_id=resolved_company_id,
            agent_id=agent_id,
        )
