"""Application use cases for control-plane agent registry operations."""

from __future__ import annotations

from shared.core.identifiers import AgentRoleId, CompanyId
from shared.schemas.event import EventTypes

from .adapter_registry import DEFAULT_ADAPTER_REGISTRY, AdapterRegistry
from .agent_registry_ports import ControlPlaneAgentRegistryStore
from .domain.agent_role import (
    AgentRole as AgentRoleAggregate,
)
from .domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
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
) -> list[AgentRole]:
    """List agent roles through the registry boundary."""
    return await store.list_agent_roles(
        company_id=CompanyId(company_id),
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
) -> AgentRole:
    """Return one agent role or raise a registry-domain not-found error."""
    role = await store.get_agent_role(
        company_id=CompanyId(company_id),
        agent_id=AgentRoleId(agent_id),
    )
    if role is None:
        raise AgentNotFoundError(agent_id)
    return role


async def create_agent_role_with_audit(
    store: ControlPlaneAgentRegistryStore,
    role: AgentRole,
    *,
    adapter_registry: AdapterRegistry = DEFAULT_ADAPTER_REGISTRY,
) -> AgentRole:
    """Create an agent role and record its audit event."""
    await _ensure_company(store, role.company_id)
    existing = await store.get_agent_role(
        company_id=CompanyId(role.company_id),
        agent_id=AgentRoleId(role.agent_id),
    )
    if existing is not None:
        raise AgentAlreadyExistsError(role.agent_id)
    await _validate_adapter(adapter_registry, role.adapter_type)

    created = await store.create_agent_role(role)
    await store.append_audit_event(
        AuditEvent(
            company_id=role.company_id,
            action=EventTypes.AGENT_ROLE_CREATED,
            target_type="agent_role",
            target_id=created.agent_id,
            actor_type="user",
            actor_id=role.created_by,
            detail={
                "agent_id": created.agent_id,
                "role_id": created.role_id,
                "agent_kind": created.agent_kind,
                "interaction_mode": created.interaction_mode,
                "role": created.role,
                "adapter_type": created.adapter_type,
                "reports_to_agent_id": created.reports_to_agent_id,
            },
        )
    )
    return created


async def update_agent_role_with_audit(
    store: ControlPlaneAgentRegistryStore,
    role: AgentRole,
    *,
    adapter_registry: AdapterRegistry = DEFAULT_ADAPTER_REGISTRY,
) -> AgentRole:
    """Update an agent role and record its audit event."""
    await _validate_adapter(adapter_registry, role.adapter_type)

    updated = await store.update_agent_role(
        company_id=CompanyId(role.company_id),
        agent_id=AgentRoleId(role.agent_id),
        values={field: getattr(role, field) for field in AGENT_UPDATE_FIELDS},
    )
    if updated is None:
        raise AgentNotFoundError(role.agent_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=role.company_id,
            action=EventTypes.AGENT_ROLE_UPDATED,
            target_type="agent_role",
            target_id=updated.agent_id,
            actor_type="user",
            actor_id=role.created_by,
            detail={
                "agent_id": updated.agent_id,
                "role_id": updated.role_id,
                "changed_fields": list(AGENT_UPDATE_FIELDS),
            },
        )
    )
    return updated


async def update_agent_status_with_audit(
    store: ControlPlaneAgentRegistryStore,
    *,
    company_id: str,
    agent_id: str,
    status: str,
    actor_id: str,
) -> AgentRole:
    """Update an agent role status and record its audit event."""
    existing = await store.get_agent_role(
        company_id=CompanyId(company_id),
        agent_id=AgentRoleId(agent_id),
    )
    if existing is None:
        raise AgentNotFoundError(agent_id)

    aggregate = AgentRoleAggregate.from_record(existing)
    aggregate.transition_to(status)
    updated = await store.update_agent_role_status(
        company_id=CompanyId(company_id),
        agent_id=AgentRoleId(agent_id),
        status=aggregate.status.value,
    )
    if updated is None:
        raise AgentNotFoundError(agent_id)

    await append_control_plane_domain_event_audits(
        store,
        aggregate.pull_events(),
        DomainEventAuditContext(
            actor_type="user",
            actor_id=actor_id,
        ),
    )
    return updated


async def _ensure_company(
    store: ControlPlaneAgentRegistryStore,
    company_id: str,
) -> None:
    if await store.get_company(CompanyId(company_id)) is not None:
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
