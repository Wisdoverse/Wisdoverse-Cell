"""Goal HTTP routes for the Control Plane API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..domain.goal import InvalidGoalTransitionError
from ..goal_use_cases import (
    GoalNotFoundError,
    ParentGoalNotFoundError,
    create_goal_with_audit,
    update_goal_status_with_audit,
)
from ..goal_use_cases import get_goal as get_goal_from_store
from ..goal_use_cases import list_goals as list_goals_from_store
from ..models import Goal, GoalStatus
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import CompanyResolver, StoresDependency, UnitOfWorkDependency, clean_string_list


class GoalCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10_000)
    status: GoalStatus = GoalStatus.DRAFT
    parent_goal_id: str | None = Field(default=None, max_length=48)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    success_metric: str = Field(default="", max_length=2_000)
    target_value: float | None = None
    current_value: float | None = None
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "success_metric", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("parent_goal_id", "owner_agent_id", "owner_user_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def _clean_tags(cls, value: Any) -> list[str]:
        return clean_string_list(value)


class GoalStatusUpdateRequest(BaseModel):
    status: GoalStatus
    current_value: float | None = None
    actor_id: str = Field(default="api", min_length=1, max_length=128)


def create_goal_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/goals")
    async def list_goals(
        company_id: str | None = None,
        status: GoalStatus | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.goals
        rows = await list_goals_from_store(
            store,
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )
        return {"goals": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/goals",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_goal(
        body: GoalCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.goals
        company_id = resolve_company(body.company_id)
        try:
            row = await create_goal_with_audit(
                store,
                Goal(
                    company_id=company_id,
                    title=body.title,
                    description=body.description,
                    status=body.status,
                    parent_goal_id=body.parent_goal_id,
                    owner_agent_id=body.owner_agent_id,
                    owner_user_id=body.owner_user_id,
                    success_metric=body.success_metric,
                    target_value=body.target_value,
                    current_value=body.current_value,
                    due_at=body.due_at,
                    tags=body.tags,
                    metadata=body.metadata,
                ),
                created_by=body.created_by,
            )
        except ParentGoalNotFoundError:
            raise_control_plane_api_error(status_code=400, detail="parent_goal_not_found")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/goals/{goal_id}")
    async def get_goal(
        goal_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.goals
        try:
            row = await get_goal_from_store(
                store,
                company_id=resolve_company(company_id),
                goal_id=goal_id,
            )
        except GoalNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="goal_not_found")
        return row_to_dict(row)

    @router.patch("/goals/{goal_id}/status")
    async def update_goal_status(
        goal_id: str,
        body: GoalStatusUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.goals
        resolved_company_id = resolve_company(company_id)
        try:
            row = await update_goal_status_with_audit(
                store,
                company_id=resolved_company_id,
                goal_id=goal_id,
                status=body.status,
                current_value=body.current_value,
                actor_id=body.actor_id,
            )
        except GoalNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="goal_not_found")
        except InvalidGoalTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_goal_transition",
            )
        await uow.commit()
        return row_to_dict(row)

    return router
