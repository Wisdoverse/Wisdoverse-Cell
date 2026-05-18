"""Application use cases for control-plane agent registry operations."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .adapter_registry import DEFAULT_ADAPTER_REGISTRY, AdapterRegistry
from .agent_registry_ports import ControlPlaneAgentRegistryStore
from .models import AgentRole, AuditEvent, CompanyContext


class AgentAlreadyExistsError(Exception):
    """Raised when an agent role already exists."""


class AgentNotFoundError(Exception):
    """Raised when an agent role cannot be found."""


class UnsupportedAdapterTypeError(Exception):
    """Raised when an agent role references an unknown adapter type."""


AGENT_UPDATE_FIELDS = (
    "display_name",
    "agent_kind",
    "interaction_mode",
    "role",
    "title",
    "domain",
    "reports_to_agent_id",
    "adapter_type",
    "adapter_config",
    "context_sources",
    "capabilities",
    "responsibilities",
    "subscribed_events",
    "published_events",
    "permissions",
    "budget_policy_id",
    "escalation_policy",
    "metadata",
)


async def list_agent_roles(
    store: ControlPlaneAgentRegistryStore,
    *,
    company_id: str,
    status: str | None = None,
    agent_kind: str | None = None,
    interaction_mode: str | None = None,
    adapter_type: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[Any]:
    """List agent roles through the registry boundary."""
    return await store.list_agent_roles(
        company_id=company_id,
        status=status,
        agent_kind=agent_kind,
        interaction_mode=interaction_mode,
        adapter_type=adapter_type,
        search=search,
        limit=limit,
    )


async def get_agent_role(
    store: ControlPlaneAgentRegistryStore,
    *,
    company_id: str,
    agent_id: str,
) -> Any:
    """Return one agent role or raise a registry-domain not-found error."""
    row = await store.get_agent_role(company_id=company_id, agent_id=agent_id)
    if row is None:
        raise AgentNotFoundError(agent_id)
    return row


async def create_agent_role_with_audit(
    store: ControlPlaneAgentRegistryStore,
    role: AgentRole,
    *,
    adapter_registry: AdapterRegistry = DEFAULT_ADAPTER_REGISTRY,
) -> Any:
    """Create an agent role and record its audit event."""
    await _ensure_company(store, role.company_id)
    existing = await store.get_agent_role(
        company_id=role.company_id,
        agent_id=role.agent_id,
    )
    if existing is not None:
        raise AgentAlreadyExistsError(role.agent_id)
    await _validate_adapter(adapter_registry, role.adapter_type)

    row = await store.create_agent_role(role)
    await store.append_audit_event(
        AuditEvent(
            company_id=role.company_id,
            action=EventTypes.AGENT_ROLE_CREATED,
            target_type="agent_role",
            target_id=row.agent_id,
            actor_type="user",
            actor_id=role.created_by,
            detail={
                "agent_id": row.agent_id,
                "role_id": row.role_id,
                "agent_kind": row.agent_kind,
                "interaction_mode": row.interaction_mode,
                "role": row.role,
                "adapter_type": row.adapter_type,
                "reports_to_agent_id": row.reports_to_agent_id,
            },
        )
    )
    return row


async def update_agent_role_with_audit(
    store: ControlPlaneAgentRegistryStore,
    role: AgentRole,
    *,
    adapter_registry: AdapterRegistry = DEFAULT_ADAPTER_REGISTRY,
) -> Any:
    """Update an agent role and record its audit event."""
    await _validate_adapter(adapter_registry, role.adapter_type)

    row = await store.update_agent_role(
        company_id=role.company_id,
        agent_id=role.agent_id,
        values={field: getattr(role, field) for field in AGENT_UPDATE_FIELDS},
    )
    if row is None:
        raise AgentNotFoundError(role.agent_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=role.company_id,
            action=EventTypes.AGENT_ROLE_UPDATED,
            target_type="agent_role",
            target_id=row.agent_id,
            actor_type="user",
            actor_id=role.created_by,
            detail={
                "agent_id": row.agent_id,
                "role_id": row.role_id,
                "changed_fields": list(AGENT_UPDATE_FIELDS),
            },
        )
    )
    return row


async def update_agent_status_with_audit(
    store: ControlPlaneAgentRegistryStore,
    *,
    company_id: str,
    agent_id: str,
    status: str,
    actor_id: str,
) -> Any:
    """Update an agent role status and record its audit event."""
    row = await store.update_agent_role_status(
        company_id=company_id,
        agent_id=agent_id,
        status=status.strip(),
    )
    if row is None:
        raise AgentNotFoundError(agent_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=EventTypes.AGENT_ROLE_STATUS_UPDATED,
            target_type="agent_role",
            target_id=row.agent_id,
            actor_type="user",
            actor_id=actor_id,
            detail={"status": row.status},
        )
    )
    return row


async def _ensure_company(
    store: ControlPlaneAgentRegistryStore,
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


async def _validate_adapter(
    adapter_registry: AdapterRegistry,
    adapter_type: str,
) -> None:
    if not adapter_registry.is_registered(adapter_type):
        raise UnsupportedAdapterTypeError(adapter_type)
