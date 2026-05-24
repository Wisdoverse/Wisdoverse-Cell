"""Evolution proposal HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..domain.evolution_proposal import InvalidEvolutionRolloutTransitionError
from ..evolution_proposal_use_cases import (
    EvolutionProposalApprovalNotFoundError,
    EvolutionProposalApprovalRequiredError,
    EvolutionProposalNotFoundError,
    create_evolution_proposal_with_audit,
    update_evolution_proposal_status_with_audit,
)
from ..evolution_proposal_use_cases import (
    get_evolution_proposal as get_evolution_proposal_from_store,
)
from ..evolution_proposal_use_cases import (
    list_evolution_proposals as list_evolution_proposals_from_store,
)
from ..models import (
    ApprovalStatus,
    EvolutionProposal,
    EvolutionRolloutState,
    EvolutionTier,
)
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency


class EvolutionProposalCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    tier: EvolutionTier
    scope: str = Field(min_length=1, max_length=256)
    evidence: dict[str, Any] = Field(default_factory=dict)
    expected_benefit: str = Field(min_length=1, max_length=20_000)
    risk: str = Field(min_length=1, max_length=20_000)
    approval_id: str | None = Field(default=None, max_length=48)
    approval_required: bool = True
    proposed_by: str = Field(default="evolution-module", min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scope", "expected_benefit", "risk", "proposed_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("approval_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class EvolutionProposalStatusUpdateRequest(BaseModel):
    approval_state: ApprovalStatus | None = None
    rollout_state: EvolutionRolloutState | None = None
    approval_id: str | None = Field(default=None, max_length=48)
    actor_id: str = Field(default="api", min_length=1, max_length=128)

    @field_validator("approval_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("actor_id", mode="before")
    @classmethod
    def _clean_actor_id(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"

    @model_validator(mode="after")
    def _require_change(self) -> "EvolutionProposalStatusUpdateRequest":
        if self.approval_state is None and self.rollout_state is None and self.approval_id is None:
            raise ValueError("at least one proposal status field must be provided")
        return self


def create_evolution_proposal_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/evolution-proposals")
    async def list_evolution_proposals(
        company_id: str | None = None,
        tier: EvolutionTier | None = None,
        approval_state: ApprovalStatus | None = None,
        rollout_state: EvolutionRolloutState | None = None,
        scope: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.evolution_proposals
        rows = await list_evolution_proposals_from_store(
            store,
            company_id=resolve_company(company_id),
            tier=tier.value if tier else None,
            approval_state=approval_state.value if approval_state else None,
            rollout_state=rollout_state.value if rollout_state else None,
            scope=scope,
            limit=limit,
        )
        return {
            "evolution_proposals": [row_to_dict(row) for row in rows],
            "total": len(rows),
        }

    @router.post(
        "/evolution-proposals",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_evolution_proposal(
        body: EvolutionProposalCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.evolution_proposals
        company_id = resolve_company(body.company_id)
        try:
            row = await create_evolution_proposal_with_audit(
                store,
                EvolutionProposal(
                    company_id=company_id,
                    tier=body.tier,
                    scope=body.scope,
                    evidence=body.evidence,
                    expected_benefit=body.expected_benefit,
                    risk=body.risk,
                    approval_id=body.approval_id,
                    metadata=body.metadata,
                ),
                approval_required=body.approval_required,
                proposed_by=body.proposed_by,
            )
        except EvolutionProposalApprovalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="approval_not_found")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/evolution-proposals/{proposal_id}")
    async def get_evolution_proposal(
        proposal_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.evolution_proposals
        try:
            row = await get_evolution_proposal_from_store(
                store,
                company_id=resolve_company(company_id),
                proposal_id=proposal_id,
            )
        except EvolutionProposalNotFoundError:
            raise_control_plane_api_error(
                status_code=404,
                detail="evolution_proposal_not_found",
            )
        return row_to_dict(row)

    @router.patch("/evolution-proposals/{proposal_id}/status")
    async def update_evolution_proposal_status(
        proposal_id: str,
        body: EvolutionProposalStatusUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.evolution_proposals
        resolved_company_id = resolve_company(company_id)
        try:
            row = await update_evolution_proposal_status_with_audit(
                store,
                company_id=resolved_company_id,
                proposal_id=proposal_id,
                approval_state=body.approval_state,
                rollout_state=body.rollout_state,
                approval_id=body.approval_id,
                actor_id=body.actor_id,
            )
        except EvolutionProposalNotFoundError:
            raise_control_plane_api_error(
                status_code=404,
                detail="evolution_proposal_not_found",
            )
        except EvolutionProposalApprovalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="approval_not_found")
        except EvolutionProposalApprovalRequiredError:
            raise_control_plane_api_error(status_code=400, detail="approval_required")
        except InvalidEvolutionRolloutTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_rollout_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    return router
