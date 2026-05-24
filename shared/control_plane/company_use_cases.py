"""Application use cases for control-plane company contexts."""
from __future__ import annotations

from typing import Any

from .company_ports import ControlPlaneCompanyStore
from .domain.company_context import CompanyContext as CompanyContextAggregate
from .domain_event_audit import (
    DomainEventAuditContext,
    append_control_plane_domain_event_audits,
)
from .models import CompanyContext


class CompanyAlreadyExistsError(Exception):
    """Raised when a company context already exists."""


class CompanyNotFoundError(Exception):
    """Raised when a company context cannot be found."""


async def list_companies(
    store: ControlPlaneCompanyStore,
    *,
    search: str | None = None,
    limit: int = 100,
) -> list[CompanyContext]:
    """List control-plane companies."""
    return await store.list_companies(search=search, limit=limit)


async def get_company(
    store: ControlPlaneCompanyStore,
    *,
    company_id: str,
) -> CompanyContext:
    """Return one company or raise not found."""
    company = await store.get_company(company_id)
    if company is None:
        raise CompanyNotFoundError(company_id)
    return company


async def create_company_with_audit(
    store: ControlPlaneCompanyStore,
    *,
    company_id: str | None,
    name: str,
    mission: str,
    metadata: dict[str, Any],
    created_by: str,
) -> CompanyContext:
    """Create a company context and record its audit event."""
    if company_id and await store.get_company(company_id) is not None:
        raise CompanyAlreadyExistsError(company_id)

    company_values: dict[str, Any] = {
        "name": name,
        "mission": mission,
        "metadata": metadata,
    }
    if company_id:
        company_values["company_id"] = company_id
    aggregate = CompanyContextAggregate.for_creation(CompanyContext(**company_values))
    company = await store.create_company(aggregate.record)
    aggregate.record = company
    aggregate.mark_created()
    await append_control_plane_domain_event_audits(
        store,
        aggregate.pull_events(),
        DomainEventAuditContext(actor_type="user", actor_id=created_by),
    )
    return company


async def update_company_with_audit(
    store: ControlPlaneCompanyStore,
    *,
    company_id: str,
    name: str | None,
    mission: str | None,
    metadata: dict[str, Any] | None,
    actor_id: str,
) -> CompanyContext:
    """Update a company context and record its audit event."""
    existing = await store.get_company(company_id)
    if existing is None:
        raise CompanyNotFoundError(company_id)

    aggregate = CompanyContextAggregate.from_record(existing)
    aggregate.apply_update(name=name, mission=mission, metadata=metadata)
    company = await store.update_company_context(
        company_id,
        name=aggregate.record.name if name is not None else None,
        mission=aggregate.record.mission if mission is not None else None,
        metadata=aggregate.record.metadata if metadata is not None else None,
    )
    if company is None:
        raise CompanyNotFoundError(company_id)

    aggregate.record = company
    await append_control_plane_domain_event_audits(
        store,
        aggregate.pull_events(),
        DomainEventAuditContext(actor_type="user", actor_id=actor_id),
    )
    return company
