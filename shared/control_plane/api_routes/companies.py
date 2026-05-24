"""Company HTTP routes for the Control Plane API."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.api import raise_control_plane_api_error

from ..api_serialization import row_to_dict
from ..company_use_cases import (
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    create_company_with_audit,
    update_company_with_audit,
)
from ..company_use_cases import get_company as get_company_from_store
from ..company_use_cases import list_companies as list_companies_from_store
from ..domain.company_context import InvalidCompanyContextError
from ..store_factory import ControlPlaneStores
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import StoresDependency, UnitOfWorkDependency


class CompanyCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=256)
    mission: str = Field(default="", max_length=10_000)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "mission", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("company_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    mission: str | None = Field(default=None, max_length=10_000)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] | None = None

    @field_validator("name", "mission", mode="before")
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
    def _require_change(self) -> "CompanyUpdateRequest":
        if self.name is None and self.mission is None and self.metadata is None:
            raise ValueError("at least one company field must be provided")
        return self


def create_company_router(
    *,
    get_stores: StoresDependency,
    get_uow: UnitOfWorkDependency,
) -> APIRouter:
    router = APIRouter()

    @router.get("/companies")
    async def list_companies(
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        rows = await list_companies_from_store(stores.companies, search=search, limit=limit)
        return {"companies": [row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/companies",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_company(
        body: CompanyCreateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            row = await create_company_with_audit(
                stores.companies,
                company_id=body.company_id,
                name=body.name,
                mission=body.mission,
                metadata=body.metadata,
                created_by=body.created_by,
            )
        except CompanyAlreadyExistsError:
            raise_control_plane_api_error(status_code=409, detail="company_already_exists")
        except InvalidCompanyContextError:
            raise_control_plane_api_error(status_code=400, detail="invalid_company_context")
        await uow.commit()
        return row_to_dict(row)

    @router.get("/companies/{company_id}")
    async def get_company(
        company_id: str,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        try:
            row = await get_company_from_store(stores.companies, company_id=company_id)
        except CompanyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="company_not_found")
        return row_to_dict(row)

    @router.patch("/companies/{company_id}")
    async def update_company(
        company_id: str,
        body: CompanyUpdateRequest,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ):
        stores = uow.stores
        try:
            row = await update_company_with_audit(
                stores.companies,
                company_id=company_id,
                name=body.name,
                mission=body.mission,
                metadata=body.metadata,
                actor_id=body.actor_id,
            )
        except CompanyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="company_not_found")
        except InvalidCompanyContextError:
            raise_control_plane_api_error(status_code=400, detail="invalid_company_context")
        await uow.commit()
        return row_to_dict(row)

    return router
