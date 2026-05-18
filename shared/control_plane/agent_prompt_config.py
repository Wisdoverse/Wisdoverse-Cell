"""Shared agent prompt-configuration helpers."""

from datetime import date, datetime
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from shared.config import settings
from shared.schemas.event import EventTypes
from shared.utils.logger import get_logger

from .agent_catalog import get_managed_agent_catalog
from .database import control_plane_db_manager
from .models import AuditEvent, CompanyContext
from .prompt_config_ports import ControlPlanePromptConfigStore
from .prompt_config_store import SqlAlchemyControlPlanePromptConfigStore

AGENT_PROMPT_MAX_LENGTH = 50_000

logger = get_logger("control_plane.agent_prompt_config")


def clean_system_prompt(value: Any) -> str:
    prompt = str(value or "").strip()
    if len(prompt) > AGENT_PROMPT_MAX_LENGTH:
        raise ValueError("system_prompt_too_long")
    return prompt


def clean_updated_by(value: Any) -> str:
    return str(value or "webui").strip()[:128] or "webui"


def is_catalog_managed_agent(agent_id: str) -> bool:
    return any(entry.agent_id == agent_id for entry in get_managed_agent_catalog())


async def ensure_prompt_config_target(
    store: ControlPlanePromptConfigStore,
    *,
    company_id: str,
    agent_id: str,
) -> None:
    if await store.get_agent_role(company_id=company_id, agent_id=agent_id) is not None:
        return
    if is_catalog_managed_agent(agent_id):
        return
    raise KeyError(agent_id)


async def ensure_prompt_config_company(
    store: ControlPlanePromptConfigStore,
    company_id: str,
) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def prompt_config_to_dict(
    row: Any | None,
    *,
    company_id: str,
    agent_id: str,
) -> dict[str, Any]:
    if row is None:
        return {
            "company_id": company_id,
            "agent_id": agent_id,
            "system_prompt": "",
            "updated_by": None,
            "metadata": {},
            "created_at": None,
            "updated_at": None,
        }

    return {
        "company_id": row.company_id,
        "agent_id": row.agent_id,
        "system_prompt": row.system_prompt,
        "updated_by": row.updated_by,
        "metadata": row.metadata_json,
        "created_at": _serialize(row.created_at),
        "updated_at": _serialize(row.updated_at),
    }


async def get_or_default_prompt_config(
    store: ControlPlanePromptConfigStore,
    *,
    company_id: str,
    agent_id: str,
) -> dict[str, Any]:
    row = await store.get_agent_prompt_config(company_id=company_id, agent_id=agent_id)
    if row is None:
        await ensure_prompt_config_target(
            store,
            company_id=company_id,
            agent_id=agent_id,
        )
    return prompt_config_to_dict(row, company_id=company_id, agent_id=agent_id)


async def update_prompt_config_with_audit(
    store: ControlPlanePromptConfigStore,
    *,
    company_id: str,
    agent_id: str,
    system_prompt: str,
    updated_by: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    await ensure_prompt_config_company(store, company_id)
    await ensure_prompt_config_target(
        store,
        company_id=company_id,
        agent_id=agent_id,
    )
    row = await store.upsert_agent_prompt_config(
        company_id=company_id,
        agent_id=agent_id,
        system_prompt=system_prompt,
        updated_by=updated_by,
        metadata=metadata,
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.AGENT_PROMPT_CONFIG_UPDATED,
            target_type="agent_prompt_config",
            target_id=agent_id,
            actor_type="user",
            actor_id=updated_by,
            detail={
                "agent_id": agent_id,
                "prompt_length": len(system_prompt),
                "metadata_keys": sorted(metadata.keys()),
            },
        )
    )
    return prompt_config_to_dict(row, company_id=company_id, agent_id=agent_id)


async def resolve_agent_system_prompt(
    agent_id: str,
    fallback: str,
    *,
    company_id: str | None = None,
) -> str:
    if not settings.control_plane_enabled:
        return fallback

    resolved_company_id = company_id or settings.control_plane_company_id
    try:
        async with control_plane_db_manager.read_session_ctx() as session:
            store = SqlAlchemyControlPlanePromptConfigStore(session)
            row = await store.get_agent_prompt_config(
                company_id=resolved_company_id,
                agent_id=agent_id,
            )
    except (OSError, SQLAlchemyError) as exc:
        logger.warning(
            "agent_prompt_config_unavailable",
            agent_id=agent_id,
            error_type=type(exc).__name__,
        )
        return fallback

    if row is None or not row.system_prompt.strip():
        return fallback
    return row.system_prompt
