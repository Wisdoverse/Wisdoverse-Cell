"""Budget HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..budget_use_cases import (
    ActiveBudgetPolicyConflictError,
    BudgetPolicyNotFoundError,
    create_budget_policy_with_audit,
    update_budget_policy_with_audit,
)
from ..budget_use_cases import get_budget_policy as get_budget_policy_from_store
from ..budget_use_cases import list_budget_policies as list_budget_policies_from_store
from ..budget_use_cases import list_budget_usage as list_budget_usage_from_store
from ..domain.budget_policy import (
    BUDGET_POLICY_STATUS_ACTIVE,
    InvalidBudgetPolicyError,
    InvalidBudgetPolicyTransitionError,
    is_budget_policy_status,
    normalize_budget_policy_status,
)
from ..models import BudgetPeriod, BudgetPolicy, BudgetScope
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import (
    CompanyResolver,
    StoresDependency,
    UnitOfWorkDependency,
    clean_string_list,
)


class BudgetPolicyCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    scope: BudgetScope
    period: BudgetPeriod
    limit_usd: float = Field(gt=0)
    scope_id: str | None = Field(default=None, max_length=64)
    warning_threshold: float = Field(default=0.8, gt=0, le=1)
    status: str = Field(default=BUDGET_POLICY_STATUS_ACTIVE, min_length=1, max_length=32)
    model_allowlist: list[str] = Field(default_factory=list, max_length=100)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scope_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("status", mode="before")
    @classmethod
    def _clean_status(cls, value: Any) -> str:
        return normalize_budget_policy_status(str(value or ""))

    @field_validator("created_by", mode="before")
    @classmethod
    def _clean_created_by(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if not is_budget_policy_status(value):
            raise ValueError("budget policy status must be active, paused, or archived")
        return value

    @field_validator("model_allowlist", mode="before")
    @classmethod
    def _clean_model_allowlist(cls, value: Any) -> list[str]:
        return clean_string_list(value)

    @model_validator(mode="after")
    def _validate_scope_id(self) -> "BudgetPolicyCreateRequest":
        if self.scope == BudgetScope.COMPANY:
            if self.scope_id is not None:
                raise ValueError("company budget policies must not set scope_id")
        elif not self.scope_id:
            raise ValueError("goal, agent, and work_item budget policies require scope_id")
        return self


class BudgetPolicyUpdateRequest(BaseModel):
    limit_usd: float | None = Field(default=None, gt=0)
    warning_threshold: float | None = Field(default=None, gt=0, le=1)
    status: str | None = Field(default=None, min_length=1, max_length=32)
    model_allowlist: list[str] | None = Field(default=None, max_length=100)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _clean_optional_status(cls, value: Any) -> str | None:
        if value is None:
            return None
        return normalize_budget_policy_status(str(value or ""))

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str | None) -> str | None:
        if value is not None and not is_budget_policy_status(value):
            raise ValueError("budget policy status must be active, paused, or archived")
        return value

    @field_validator("actor_id", mode="before")
    @classmethod
    def _clean_actor_id(cls, value: Any) -> str:
        return str(value or "api").strip() or "api"

    @field_validator("model_allowlist", mode="before")
    @classmethod
    def _clean_optional_model_allowlist(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        return clean_string_list(value)

    @model_validator(mode="after")
    def _require_change(self) -> "BudgetPolicyUpdateRequest":
        if (
            self.limit_usd is None
            and self.warning_threshold is None
            and self.status is None
            and self.model_allowlist is None
            and self.metadata is None
        ):
            raise ValueError("at least one budget policy field must be provided")
        return self


def create_budget_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/budgets/policies")
    async def list_budget_policies(
        company_id: str | None = None,
        scope: BudgetScope | None = None,
        scope_id: str | None = None,
        period: BudgetPeriod | None = None,
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        status = normalize_budget_policy_status(status) if status is not None else None
        if status is not None and not is_budget_policy_status(status):
            raise_control_plane_api_error(status_code=400, detail="invalid_budget_policy_status")
        store = stores.budgets
        rows = await list_budget_policies_from_store(
            store,
            company_id=resolve_company(company_id),
            scope=scope,
            scope_id=scope_id,
            period=period,
            status=status,
            limit=limit,
        )
        return {
            "budget_policies": [row_to_dict(row) for row in rows],
            "total": len(rows),
        }

    @router.post(
        "/budgets/policies",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_budget_policy(
        body: BudgetPolicyCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.budgets
        company_id = resolve_company(body.company_id)
        try:
            row = await create_budget_policy_with_audit(
                store,
                BudgetPolicy(
                    company_id=company_id,
                    scope=body.scope,
                    scope_id=body.scope_id,
                    period=body.period,
                    limit_usd=body.limit_usd,
                    warning_threshold=body.warning_threshold,
                    status=body.status,
                    model_allowlist=body.model_allowlist,
                    metadata=body.metadata,
                ),
                created_by=body.created_by,
            )
        except ActiveBudgetPolicyConflictError:
            raise_control_plane_api_error(
                status_code=409,
                detail="active_budget_policy_exists",
            )
        except InvalidBudgetPolicyError:
            raise_control_plane_api_error(status_code=400, detail="invalid_budget_policy")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/budgets/policies/{budget_id}")
    async def get_budget_policy(
        budget_id: str,
        company_id: str | None = None,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.budgets
        try:
            row = await get_budget_policy_from_store(
                store,
                company_id=resolve_company(company_id),
                budget_id=budget_id,
            )
        except BudgetPolicyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="budget_policy_not_found")
        return row_to_dict(row)

    @router.patch("/budgets/policies/{budget_id}")
    async def update_budget_policy(
        budget_id: str,
        body: BudgetPolicyUpdateRequest,
        company_id: str | None = None,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        store = stores.budgets
        resolved_company_id = resolve_company(company_id)
        update_values = body.model_dump(exclude_unset=True)
        update_values.pop("actor_id", None)
        try:
            row = await update_budget_policy_with_audit(
                store,
                company_id=resolved_company_id,
                budget_id=budget_id,
                limit_usd=body.limit_usd,
                warning_threshold=body.warning_threshold,
                status=body.status,
                model_allowlist=body.model_allowlist,
                metadata=body.metadata,
                actor_id=body.actor_id,
                changed_fields=list(update_values),
            )
        except BudgetPolicyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="budget_policy_not_found")
        except ActiveBudgetPolicyConflictError:
            raise_control_plane_api_error(
                status_code=409,
                detail="active_budget_policy_exists",
            )
        except InvalidBudgetPolicyTransitionError:
            raise_control_plane_api_error(
                status_code=400,
                detail="invalid_budget_policy_transition",
            )
        except InvalidBudgetPolicyError:
            raise_control_plane_api_error(status_code=400, detail="invalid_budget_policy")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/budgets/usage")
    async def list_budget_usage(
        company_id: str | None = None,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.budgets
        rows = await list_budget_usage_from_store(
            store,
            company_id=resolve_company(company_id),
            budget_id=budget_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )
        return {"usage": [row_to_dict(row) for row in rows]}

    return router
