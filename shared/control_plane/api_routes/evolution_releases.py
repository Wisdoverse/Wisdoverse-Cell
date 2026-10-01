"""Persist L1 release intent before contacting the owning runtime."""

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from shared.api import raise_control_plane_api_error

from ..domain.execution_policy import ExecutionDenied
from ..evolution_deployment_gateway import HttpEvolutionDeploymentGateway
from ..operator_auth import OperatorPrincipal, require_operator
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import UnitOfWorkDependency


class EvolutionReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_id: str = Field(min_length=1, max_length=48)
    evaluation_report_id: str = Field(min_length=1, max_length=48)
    skill_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=64)
    baseline_version: int = Field(ge=1)
    candidate_version: int = Field(ge=1)
    baseline_config_hash: str = Field(pattern="^[a-f0-9]{64}$")
    candidate_config_hash: str = Field(pattern="^[a-f0-9]{64}$")
    action: Literal["shadow", "canary", "promote", "rollback"]


def create_evolution_release_router(*, get_uow: UnitOfWorkDependency) -> APIRouter:
    router = APIRouter()

    @router.post("/evolution-proposals/{proposal_id}/release/reconcile")
    async def reconcile(
        proposal_id: str,
        company_id: str,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> dict[str, Any]:
        principal.require("evolution:release", company_id)
        try:
            command = await uow.stores.evolution_deployments.pending(
                company_id=company_id, proposal_id=proposal_id
            )
            response = await HttpEvolutionDeploymentGateway().lookup(command)
            if response is None:
                raise ExecutionDenied("release_not_applied_pending_review", 409)
            await uow.stores.evolution_deployments.acknowledge(
                command, response, actor_id=principal.actor_id
            )
            await uow.commit()
            return response
        except ExecutionDenied as exc:
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.reason)
        except Exception:
            raise_control_plane_api_error(
                status_code=502, detail="evolution_release_pending_reconciliation"
            )

    @router.post("/evolution-proposals/{proposal_id}/release/recover")
    async def recover_expired(
        proposal_id: str,
        company_id: str,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> dict[str, Any]:
        """Operator-confirmed recovery for an expired command with receiver 404."""
        principal.require("evolution:release", company_id)
        try:
            store = uow.stores.evolution_deployments
            original = await store.pending(company_id=company_id, proposal_id=proposal_id)
            # Do not hold database locks or a transaction open across the HTTP call.
            await uow.commit()
            uow.begin_next_transaction()
            gateway = HttpEvolutionDeploymentGateway()
            receipt = await gateway.lookup(original)
            if receipt is not None:
                await store.acknowledge(original, receipt, actor_id=principal.actor_id)
                await uow.commit()
                return receipt

            # lookup() returns None only for authoritative 404. Transport and
            # server errors raise, so they cannot clear or renew a command.
            replacement = await store.recover_expired_pending(original, actor_id=principal.actor_id)
            await uow.commit()
            uow.begin_next_transaction()
            response = await gateway.lookup(replacement)
            if response is None:
                response = await gateway.apply(replacement)
            await store.acknowledge(replacement, response, actor_id=principal.actor_id)
            await uow.commit()
            return response
        except ExecutionDenied as exc:
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.reason)
        except Exception:
            raise_control_plane_api_error(
                status_code=502, detail="evolution_release_pending_reconciliation"
            )

    @router.post("/evolution-proposals/{proposal_id}/release")
    async def release(
        proposal_id: str,
        body: EvolutionReleaseRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> dict[str, Any]:
        principal.require("evolution:release", body.company_id)
        try:
            command = await uow.stores.evolution_deployments.prepare(
                proposal_id=proposal_id, actor_id=principal.actor_id, **body.model_dump()
            )
            await uow.commit()
            uow.begin_next_transaction()
            gateway = HttpEvolutionDeploymentGateway()
            response = await gateway.lookup(command)
            if response is None:
                response = await gateway.apply(command)
            await uow.stores.evolution_deployments.acknowledge(
                command, response, actor_id=principal.actor_id
            )
        except ExecutionDenied as exc:
            raise_control_plane_api_error(status_code=exc.status_code, detail=exc.reason)
        except Exception:
            raise_control_plane_api_error(
                status_code=502, detail="evolution_release_pending_reconciliation"
            )
        await uow.commit()
        return response

    return router
