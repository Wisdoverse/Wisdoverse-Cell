"""FastAPI router for the shared control-plane ledger."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings

from .api_routes.agents import create_agent_router
from .api_routes.approvals import create_approval_router
from .api_routes.artifacts import create_artifact_router
from .api_routes.audit import create_audit_router
from .api_routes.audit_export import create_audit_export_router
from .api_routes.budgets import create_budget_router
from .api_routes.companies import create_company_router
from .api_routes.company_templates import create_company_template_router
from .api_routes.decisions import create_decision_router
from .api_routes.evolution_evaluations import create_evolution_evaluation_router
from .api_routes.evolution_proposals import create_evolution_proposal_router
from .api_routes.evolution_releases import create_evolution_release_router
from .api_routes.executions import create_execution_router
from .api_routes.goals import create_goal_router
from .api_routes.knowledge import create_knowledge_router
from .api_routes.operating_metrics import create_operating_metrics_router
from .api_routes.runs import create_run_router
from .api_routes.work_items import create_work_item_router
from .database import control_plane_db_manager
from .operator_auth import _action, authorize_control_plane_request, require_operator
from .store_factory import ControlPlaneStores
from .unit_of_work import ControlPlaneUnitOfWork

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def create_control_plane_router(
    *,
    session_provider: SessionProvider | None = None,
) -> APIRouter:
    provider = session_provider or control_plane_db_manager.session
    router = APIRouter(prefix="/api/v1/control-plane", tags=["control-plane"],
                      dependencies=[Depends(authorize_control_plane_request)])

    async def get_stores() -> AsyncGenerator[ControlPlaneStores, None]:
        async with provider() as session:
            yield ControlPlaneStores(session)

    async def get_uow() -> AsyncGenerator[ControlPlaneUnitOfWork, None]:
        if session_provider is None:
            session_context = control_plane_db_manager.async_session()
        else:
            session_context = provider()

        async with session_context as session:
            uow = ControlPlaneUnitOfWork(session)
            try:
                yield uow
            except Exception:
                if not uow.completed:
                    await uow.rollback()
                raise
            finally:
                if not uow.completed:
                    await uow.rollback()

    def resolve_company(company_id: str | None) -> str:
        return company_id or settings.control_plane_company_id

    async def authorize_resource(request: Request, stores: ControlPlaneStores = Depends(get_stores)):
        principal = await require_operator(request)
        lookups = {
            "approval_id": stores.approvals.get_approval,
            "run_id": stores.agent_runs.get_agent_run,
            "artifact_id": stores.artifacts.get_artifact,
            "goal_id": stores.goals.get_goal,
            "proposal_id": stores.evolution_proposals.get_evolution_proposal,
            "work_item_id": stores.work_items.get_work_item,
        }
        for parameter, lookup in lookups.items():
            identifier = request.path_params.get(parameter)
            if identifier:
                record = await lookup(identifier)
                if record is not None:
                    principal.require(_action(request.method, request.url.path), record.company_id)

    router.dependencies.append(Depends(authorize_resource))

    async def get_evaluation_store(uow: ControlPlaneUnitOfWork = Depends(get_uow)):
        yield uow.stores.evolution_evaluations

    async def get_operating_metrics_store(stores: ControlPlaneStores = Depends(get_stores)):
        yield stores.operating_metrics

    router.include_router(create_company_template_router(get_uow=get_uow))
    router.include_router(create_audit_export_router(get_stores=get_stores))
    router.include_router(create_operating_metrics_router(get_store=get_operating_metrics_store))
    router.include_router(create_execution_router(get_uow=get_uow))
    router.include_router(create_evolution_release_router(get_uow=get_uow))
    router.include_router(create_knowledge_router(
        get_stores=get_stores, get_uow=get_uow, resolve_company=resolve_company))
    router.include_router(create_evolution_evaluation_router(
        get_store=get_evaluation_store, get_uow=get_uow, resolve_company=resolve_company))

    router.include_router(
        create_company_router(
            get_stores=get_stores,
            get_uow=get_uow,
        )
    )

    router.include_router(
        create_goal_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_work_item_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_decision_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_artifact_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_evolution_proposal_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_run_router(
            get_stores=get_stores,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_agent_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_approval_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_budget_router(
            get_stores=get_stores,
            get_uow=get_uow,
            resolve_company=resolve_company,
        )
    )

    router.include_router(
        create_audit_router(
            get_stores=get_stores,
            resolve_company=resolve_company,
        )
    )

    return router
