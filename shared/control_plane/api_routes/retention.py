"""Explicit authenticated retention preview and bounded company cleanup."""

from fastapi import APIRouter, Depends, Header

from shared.api import raise_control_plane_api_error
from shared.config import settings

from ..domain.physical_retention import RetentionCommand, RetentionReceipt
from ..models import AuditEvent
from ..operator_auth import OperatorPrincipal, require_operator
from ..retention_use_cases import RetentionUseCase
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import UnitOfWorkDependency


def create_retention_router(*, get_uow: UnitOfWorkDependency) -> APIRouter:
    router = APIRouter()

    @router.post("/retention", response_model=RetentionReceipt)
    async def apply_retention(
        command: RetentionCommand,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> RetentionReceipt:
        principal.require("audit:retention", command.company_id)
        if not command.dry_run and not settings.control_plane_retention_enabled:
            raise_control_plane_api_error(status_code=503, detail="physical_retention_disabled")
        try:
            result = await RetentionUseCase(
                uow.stores.retention, retention_days=settings.control_plane_audit_retention_days
            ).execute(command, request_id=idempotency_key)
            if not command.dry_run:
                await uow.stores.audit_events.append_audit_event(
                    AuditEvent(
                        company_id=command.company_id,
                        action="retention.applied",
                        target_type="company",
                        target_id=command.company_id,
                        actor_type="operator",
                        actor_id=principal.actor_id,
                        idempotency_key=f"retention:{idempotency_key}",
                        detail=result.model_dump(mode="json"),
                    )
                )
            await uow.commit()
            return result
        except ValueError as exc:
            raise_control_plane_api_error(status_code=409, detail=str(exc))

    return router
