"""Capability-bound execution controls and explicit operator recovery."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from shared.api import raise_control_plane_api_error

from ..domain.execution_policy import ExecutionDenied
from ..operator_auth import OperatorPrincipal, require_operator
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import UnitOfWorkDependency


class ExecutionControlRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=48)
    action: str = Field(pattern="^(pause|resume|terminate)$")
    reason: str = Field(min_length=1, max_length=4000)


class ExecutionRecoveryRequest(BaseModel):
    company_id: str = Field(min_length=1, max_length=48)
    reason: str = Field(min_length=1, max_length=4000)
    effects_reconciled: bool


def create_execution_router(*, get_uow: UnitOfWorkDependency) -> APIRouter:
    router = APIRouter()

    @router.post("/executions/{run_id}/control")
    async def control(
        run_id: str,
        body: ExecutionControlRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        principal.require("execution:control", body.company_id)
        try:
            result = await uow.stores.executions.request_control(
                run_id=run_id,
                company_id=body.company_id,
                action=body.action,
                reason=body.reason,
                actor_id=principal.actor_id,
            )
        except ExecutionDenied as exc:
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.reason)
        await uow.commit()
        return result

    @router.post("/executions/{run_id}/recover")
    async def recover(
        run_id: str,
        body: ExecutionRecoveryRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ):
        principal.require("execution:recover", body.company_id)
        if body.effects_reconciled is not True:
            raise_control_plane_api_error(status_code=409, detail="external_effect_review_required")
        try:
            result = await uow.stores.executions.recover(
                run_id=run_id,
                company_id=body.company_id,
                reason=body.reason,
                actor_id=principal.actor_id,
            )
        except ExecutionDenied as exc:
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.reason)
        await uow.commit()
        return result

    return router
