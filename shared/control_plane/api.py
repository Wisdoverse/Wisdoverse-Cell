"""FastAPI router for the shared control-plane ledger."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings

from .api_routes.agents import create_agent_router
from .api_routes.approvals import create_approval_router
from .api_routes.artifacts import create_artifact_router
from .api_routes.audit import create_audit_router
from .api_routes.budgets import create_budget_router
from .api_routes.companies import create_company_router
from .api_routes.decisions import create_decision_router
from .api_routes.evolution_proposals import create_evolution_proposal_router
from .api_routes.goals import create_goal_router
from .api_routes.runs import create_run_router
from .api_routes.work_items import create_work_item_router
from .database import control_plane_db_manager
from .store_factory import ControlPlaneStores
from .unit_of_work import ControlPlaneUnitOfWork

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def create_control_plane_router(
    *,
    session_provider: SessionProvider | None = None,
) -> APIRouter:
    provider = session_provider or control_plane_db_manager.session
    router = APIRouter(prefix="/api/v1/control-plane", tags=["control-plane"])

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
