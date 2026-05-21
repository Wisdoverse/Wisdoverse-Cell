"""Audit timeline HTTP routes for the Control Plane API."""

from fastapi import APIRouter, Depends, Query

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict, serialize_value
from ..audit_timeline_use_cases import TimelineScopeRequiredError
from ..audit_timeline_use_cases import build_timeline as build_timeline_from_store
from ..audit_timeline_use_cases import list_audit_events as list_audit_events_from_store
from ..store_factory import ControlPlaneStores
from .dependencies import CompanyResolver, StoresDependency


def create_audit_router(
    *,
    get_stores: StoresDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/audit-events")
    async def list_audit_events(
        company_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        work_item_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.audit_timeline
        rows = await list_audit_events_from_store(
            store,
            company_id=resolve_company(company_id),
            trace_id=trace_id,
            run_id=run_id,
            work_item_id=work_item_id,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )
        return {"audit_events": [row_to_dict(row) for row in rows]}

    @router.get("/timeline")
    async def get_timeline(
        company_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.audit_timeline
        try:
            items = await build_timeline_from_store(
                store,
                company_id=resolve_company(company_id),
                trace_id=trace_id,
                run_id=run_id,
                limit=limit,
            )
        except TimelineScopeRequiredError:
            raise_control_plane_api_error(status_code=400, detail="trace_id_or_run_id_required")
        return {
            "timeline": [
                {
                    "type": item.item_type,
                    "at": serialize_value(item.at),
                    "data": row_to_dict(item.data),
                }
                for item in items
            ]
        }

    return router
