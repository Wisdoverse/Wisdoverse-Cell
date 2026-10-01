"""HTTP routes for immutable fixed-case evolution evaluation reports."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field

from shared.api import raise_control_plane_api_error
from shared.evolution.evaluation_batch import EvaluationBatch, EvaluationPolicy

from ..evolution_evaluation_ports import ControlPlaneEvolutionEvaluationStore
from ..evolution_evaluation_use_cases import (
    EvolutionEvaluationCompatibilityError,
    EvolutionEvaluationProposalNotFoundError,
    list_evaluation_comparisons,
    record_evaluation_comparison,
)
from ..unit_of_work import ControlPlaneUnitOfWork

EvaluationStoreDependency = Callable[[], AsyncGenerator[ControlPlaneEvolutionEvaluationStore, None]]
CompanyResolver = Callable[[str | None], str]


class EvolutionEvaluationCreateRequest(BaseModel):
    """Body containing two fixed-case batches and the declared promotion policy."""

    company_id: str = Field(min_length=1, max_length=48)
    baseline: EvaluationBatch
    candidate: EvaluationBatch
    policy: EvaluationPolicy
    actor_id: str = Field(default="api", min_length=1, max_length=128)


def create_evolution_evaluation_router(
    *,
    get_store: EvaluationStoreDependency,
    get_uow: Callable[..., Any],
    resolve_company: CompanyResolver,
) -> APIRouter:
    """Create evaluation report routes with store and transaction dependencies.

    The application composition should bind `get_store` to the same session as
    `get_uow`, so the append-only report and its audit event commit together.
    """

    router = APIRouter()

    @router.post(
        "/evolution-proposals/{proposal_id}/evaluations",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_evaluation(
        proposal_id: str,
        body: EvolutionEvaluationCreateRequest,
        store: ControlPlaneEvolutionEvaluationStore = Depends(get_store),
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ) -> dict[str, Any]:
        company_id = resolve_company(body.company_id)
        try:
            report = await record_evaluation_comparison(
                store,
                company_id=company_id,
                proposal_id=proposal_id,
                baseline=body.baseline,
                candidate=body.candidate,
                policy=body.policy,
                actor_id=body.actor_id,
            )
        except EvolutionEvaluationProposalNotFoundError:
            raise_control_plane_api_error(
                status_code=404,
                detail="evolution_proposal_not_found",
            )
        except EvolutionEvaluationCompatibilityError:
            raise_control_plane_api_error(
                status_code=400,
                detail="evaluation_arms_incompatible",
            )
        await uow.commit()
        return report.model_dump(mode="json")

    @router.get("/evolution-proposals/{proposal_id}/evaluations")
    async def list_evaluations(
        proposal_id: str,
        company_id: str | None = Query(default=None, min_length=1, max_length=48),
        store: ControlPlaneEvolutionEvaluationStore = Depends(get_store),
    ) -> dict[str, Any]:
        try:
            reports = await list_evaluation_comparisons(
                store,
                company_id=resolve_company(company_id),
                proposal_id=proposal_id,
            )
        except EvolutionEvaluationProposalNotFoundError:
            raise_control_plane_api_error(
                status_code=404,
                detail="evolution_proposal_not_found",
            )
        return {
            "evaluations": [report.model_dump(mode="json") for report in reports],
            "total": len(reports),
            "report_kind": "fixed_evaluation_case_comparison",
        }

    return router


__all__ = [
    "EvaluationStoreDependency",
    "EvolutionEvaluationCreateRequest",
    "create_evolution_evaluation_router",
]
