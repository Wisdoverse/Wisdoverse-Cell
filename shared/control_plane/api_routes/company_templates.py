"""HTTP routes for portable company-template import and export."""

from typing import Any

from fastapi import APIRouter, Depends

from shared.api import raise_control_plane_api_error

from ..company_template_store import ExistingStoresCompanyTemplateAdapter
from ..company_template_use_cases import (
    CompanyTemplateCompanyNotFoundError,
    CompanyTemplateNameCollisionError,
    CompanyTemplatePermissionsReviewRequiredError,
    export_company_template_for_company,
    import_company_template,
)
from ..domain.company_template import CompanyTemplateError
from ..unit_of_work import ControlPlaneUnitOfWork
from .dependencies import UnitOfWorkDependency


def create_company_template_router(
    *,
    get_uow: UnitOfWorkDependency,
) -> APIRouter:
    router = APIRouter()

    @router.get("/companies/{company_id}/template")
    async def export_company_template_route(
        company_id: str,
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ) -> dict[str, Any]:
        store = _template_store(uow)
        try:
            template = await export_company_template_for_company(
                store,
                company_id=company_id,
            )
        except CompanyTemplateCompanyNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="company_not_found")
        except CompanyTemplateError:
            raise_control_plane_api_error(status_code=422, detail="invalid_company_template")
        return template.model_dump(mode="json")

    @router.post("/company-templates/import", status_code=201)
    async def import_company_template_route(
        body: dict[str, Any],
        uow: ControlPlaneUnitOfWork = Depends(get_uow),
    ) -> dict[str, Any]:
        if set(body) - {"template", "permissions_reviewed"} or "template" not in body:
            raise_control_plane_api_error(status_code=422, detail="invalid_company_template")
        reviewed = body.get("permissions_reviewed")
        if type(reviewed) is not bool:
            raise_control_plane_api_error(status_code=422, detail="permissions_reviewed_required")
        store = _template_store(uow)
        try:
            result = await import_company_template(
                store,
                body["template"],
                permissions_reviewed=reviewed,
            )
        except CompanyTemplatePermissionsReviewRequiredError:
            raise_control_plane_api_error(
                status_code=409,
                detail="company_template_permissions_review_required",
            )
        except CompanyTemplateNameCollisionError:
            raise_control_plane_api_error(status_code=409, detail="company_template_name_collision")
        except CompanyTemplateError:
            raise_control_plane_api_error(status_code=422, detail="invalid_company_template")

        await uow.commit()
        return {
            "company_id": result.company_id,
            "goal_ids": result.goal_ids,
            "role_ids": result.role_ids,
        }

    return router


def _template_store(uow: ControlPlaneUnitOfWork) -> ExistingStoresCompanyTemplateAdapter:
    stores = uow.stores
    return ExistingStoresCompanyTemplateAdapter(
        companies=stores.companies,
        goals=stores.goals,
        roles=stores.agent_registry,
        budgets=stores.budgets,
    )


__all__ = ["create_company_template_router"]
