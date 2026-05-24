"""Decision HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..decision_use_cases import (
    DecisionGoalNotFoundError,
    DecisionLinkMismatchError,
    DecisionNotFoundError,
    DecisionRunNotFoundError,
    DecisionWorkItemNotFoundError,
    create_decision_with_audit,
    update_decision_status_with_audit,
)
from ..decision_use_cases import get_decision as get_decision_from_store
from ..decision_use_cases import list_decisions as list_decisions_from_store
from ..domain.decision import InvalidDecisionTransitionError
from ..models import Decision, DecisionStatus
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency


class DecisionCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=256)
    rationale: str = Field(min_length=1, max_length=20_000)
    status: DecisionStatus = DecisionStatus.PROPOSED
    run_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)
    goal_id: str | None = Field(default=None, max_length=48)
    options: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    selected_option: str | None = Field(default=None, max_length=128)
    decided_by: str | None = Field(default=None, max_length=128)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "rationale", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "run_id",
        "work_item_id",
        "goal_id",
        "selected_option",
        "decided_by",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class DecisionStatusUpdateRequest(BaseModel):
    status: DecisionStatus
    selected_option: str | None = Field(default=None, max_length=128)
    decided_by: str | None = Field(default=None, max_length=128)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


def create_decision_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/decisions")
    async def list_decisions(
        company_id: str | None = None,
        status: DecisionStatus | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.decisions
        rows = await list_decisions_from_store(
            store,
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {"decisions": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/decisions",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_decision(
        body: DecisionCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.decisions
        company_id = resolve_company(body.company_id)
        try:
            row = await create_decision_with_audit(
                store,
                Decision(
                    company_id=company_id,
                    title=body.title,
                    rationale=body.rationale,
                    status=body.status,
                    run_id=body.run_id,
                    work_item_id=body.work_item_id,
                    goal_id=body.goal_id,
                    options=body.options,
                    selected_option=body.selected_option,
                    decided_by=body.decided_by,
                    metadata=body.metadata,
                ),
                created_by=body.created_by,
            )
        except DecisionRunNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="run_not_found")
        except DecisionWorkItemNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="work_item_not_found")
        except DecisionGoalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="goal_not_found")
        except DecisionLinkMismatchError:
            raise_control_plane_api_error(status_code=400, detail="link_mismatch")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/decisions/{decision_id}")
    async def get_decision(
        decision_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.decisions
        try:
            row = await get_decision_from_store(
                store,
                company_id=resolve_company(company_id),
                decision_id=decision_id,
            )
        except DecisionNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="decision_not_found")
        return row_to_dict(row)

    @router.patch("/decisions/{decision_id}/status")
    async def update_decision_status(
        decision_id: str,
        body: DecisionStatusUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.decisions
        resolved_company_id = resolve_company(company_id)
        try:
            row = await update_decision_status_with_audit(
                store,
                company_id=resolved_company_id,
                decision_id=decision_id,
                status=body.status,
                selected_option=body.selected_option,
                decided_by=body.decided_by,
                actor_id=body.actor_id,
            )
        except DecisionNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="decision_not_found")
        except InvalidDecisionTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_decision_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    return router
