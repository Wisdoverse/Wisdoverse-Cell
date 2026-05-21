"""Agent run HTTP routes for the Control Plane API."""

from fastapi import APIRouter, Depends, Query

from shared.api import raise_control_plane_api_error

from ..agent_run_use_cases import AgentRunNotFoundError
from ..agent_run_use_cases import get_agent_run as get_agent_run_from_store
from ..agent_run_use_cases import list_agent_runs as list_agent_runs_from_store
from ..api_serialization import row_to_dict
from ..store_factory import ControlPlaneStores
from .dependencies import CompanyResolver, StoresDependency


def create_run_router(
    *,
    get_stores: StoresDependency,
    resolve_company: CompanyResolver,
) -> APIRouter:
    router = APIRouter()

    @router.get("/runs")
    async def list_runs(
        company_id: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.agent_runs
        rows = await list_agent_runs_from_store(
            store,
            company_id=resolve_company(company_id),
            status=status,
            agent_id=agent_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {"runs": [row_to_dict(row) for row in rows]}

    @router.get("/runs/{run_id}")
    async def get_run(
        run_id: str,
        stores: ControlPlaneStores = Depends(get_stores),
    ):
        store = stores.agent_runs
        try:
            row = await get_agent_run_from_store(store, run_id=run_id)
        except AgentRunNotFoundError:
            raise_control_plane_api_error(status_code=404, detail="run_not_found")
        return row_to_dict(row)

    return router
