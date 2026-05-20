"""Application use cases for control-plane company contexts."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .company_ports import ControlPlaneCompanyStore
from .domain_records import company_record
from .models import AuditEvent, CompanyContext


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
    rows = await store.list_companies(search=search, limit=limit)
    return [company_record(row) for row in rows]


async def get_company(
    store: ControlPlaneCompanyStore,
    *,
    company_id: str,
) -> CompanyContext:
    """Return one company or raise not found."""
    row = await store.get_company(company_id)
    if row is None:
        raise CompanyNotFoundError(company_id)
    return company_record(row)


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
    row = await store.create_company(CompanyContext(**company_values))
    await store.append_audit_event(
        AuditEvent(
            company_id=row.company_id,
            action=EventTypes.COMPANY_CREATED,
            target_type="company",
            target_id=row.company_id,
            actor_type="user",
            actor_id=created_by,
            detail={
                "company_id": row.company_id,
                "name": row.name,
            },
        )
    )
    return company_record(row)


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
    row = await store.update_company_context(
        company_id,
        name=name,
        mission=mission,
        metadata=metadata,
    )
    if row is None:
        raise CompanyNotFoundError(company_id)

    await store.append_audit_event(
        AuditEvent(
            company_id=row.company_id,
            action=EventTypes.COMPANY_UPDATED,
            target_type="company",
            target_id=row.company_id,
            actor_type="user",
            actor_id=actor_id,
            detail={
                "company_id": row.company_id,
                "name": row.name,
            },
        )
    )
    return company_record(row)
