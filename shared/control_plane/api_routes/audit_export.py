"""Company-scoped, redacted audit export endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from shared.api import raise_control_plane_api_error

from ..audit_export_store import AuditExportCursorError
from ..domain.audit_retention import AuditRetentionError, export_audit_events
from ..operator_auth import OperatorPrincipal, require_operator
from ..store_factory import ControlPlaneStores
from .dependencies import StoresDependency

AUDIT_EXPORT_RETENTION_DAYS = 90


def create_audit_export_router(*, get_stores: StoresDependency) -> APIRouter:
    router = APIRouter()

    @router.get("/audit-export")
    async def export_audit(
        company_id: str = Query(min_length=1, max_length=48),
        since: datetime = Query(),
        until: datetime = Query(),
        after_id: str | None = Query(default=None, min_length=1, max_length=48),
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        company_id = company_id.strip()
        if not company_id:
            raise_control_plane_api_error(status_code=400, detail="company_id_required")
        principal.require("audit:export", company_id)
        now = datetime.now(UTC)
        try:
            export_audit_events(
                (),
                company_id=company_id,
                since=since,
                until=until,
                retention_days=AUDIT_EXPORT_RETENTION_DAYS,
                now=now,
            )
        except AuditRetentionError as exc:
            raise_control_plane_api_error(status_code=400, detail=str(exc))
        try:
            rows = await stores.audit_export.list_page(
                company_id=company_id,
                since=since,
                until=until,
                after_id=after_id,
                limit=limit,
            )
        except AuditExportCursorError as exc:
            raise_control_plane_api_error(status_code=400, detail=str(exc))
        try:
            page = export_audit_events(
                rows,
                company_id=company_id,
                since=since,
                until=until,
                retention_days=AUDIT_EXPORT_RETENTION_DAYS,
                now=now,
            )
        except AuditRetentionError as exc:
            raise_control_plane_api_error(status_code=400, detail=str(exc))
        payload = page.to_dict()
        payload["next_cursor"] = rows[-1].audit_event_id if len(rows) == limit else None
        return payload

    return router
