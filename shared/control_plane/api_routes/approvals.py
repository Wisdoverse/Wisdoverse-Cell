"""Approval HTTP routes for the Control Plane API."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..approval_gate import ApprovalRequiredError
from ..approval_use_cases import list_approvals as list_approvals_from_store
from ..approval_use_cases import resolve_approval_and_sync_proposal
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency


class ApprovalActionRequest(BaseModel):
    resolved_by: str = Field(default="api", min_length=1, max_length=128)


def create_approval_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/approvals")
    async def list_approvals(
        company_id: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.approvals
        rows = await list_approvals_from_store(
            store,
            company_id=resolve_company(company_id),
            status=status,
            run_id=run_id,
            trace_id=trace_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {"approvals": [row_to_dict(row) for row in rows]}

    @router.post("/approvals/{approval_id}/approve")
    async def approve(
        approval_id: str,
        body: ApprovalActionRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.approvals
        try:
            decision = await resolve_approval_and_sync_proposal(
                store,
                approval_id=approval_id,
                resolved_by=body.resolved_by,
                approved=True,
            )
        except ApprovalRequiredError as exc:
            raise_control_plane_api_error(status_code=404, detail=str(exc))
        await uow.commit()
        return decision.__dict__

    @router.post("/approvals/{approval_id}/reject")
    async def reject(
        approval_id: str,
        body: ApprovalActionRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.approvals
        try:
            decision = await resolve_approval_and_sync_proposal(
                store,
                approval_id=approval_id,
                resolved_by=body.resolved_by,
                approved=False,
            )
        except ApprovalRequiredError as exc:
            raise_control_plane_api_error(status_code=404, detail=str(exc))
        await uow.commit()
        return decision.__dict__

    return router
