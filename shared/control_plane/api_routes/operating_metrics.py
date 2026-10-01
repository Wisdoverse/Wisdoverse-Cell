"""Read-only, company-scoped operating metrics endpoint."""

from collections.abc import AsyncGenerator, Callable
from typing import Any, Protocol

from fastapi import APIRouter, Depends, Query, Response

from shared.config import settings

from ..operating_metrics_store import render_prometheus_metrics
from ..operator_auth import OperatorPrincipal, require_operator


class OperatingMetricsReader(Protocol):
    async def get_metrics(self, company_id: str) -> dict[str, Any]: ...


OperatingMetricsStoreDependency = Callable[[], AsyncGenerator[OperatingMetricsReader, None]]


def create_operating_metrics_router(*, get_store: OperatingMetricsStoreDependency) -> APIRouter:
    router = APIRouter()

    @router.get("/operating-metrics")
    async def get_operating_metrics(
        company_id: str | None = Query(default=None, min_length=1, max_length=48),
        store: OperatingMetricsReader = Depends(get_store),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> dict[str, Any]:
        actual_company_id = (company_id or settings.control_plane_company_id).strip()
        principal.require("control-plane:read", actual_company_id)
        return await store.get_metrics(actual_company_id)

    @router.get("/operating-metrics/prometheus", response_class=Response)
    async def get_operating_metrics_prometheus(
        company_id: str | None = Query(default=None, min_length=1, max_length=48),
        store: OperatingMetricsReader = Depends(get_store),
        principal: OperatorPrincipal = Depends(require_operator),
    ) -> Response:
        actual_company_id = (company_id or settings.control_plane_company_id).strip()
        principal.require("control-plane:read", actual_company_id)
        metrics = await store.get_metrics(actual_company_id)
        return Response(
            content=render_prometheus_metrics(metrics),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return router


__all__ = ["OperatingMetricsStoreDependency", "create_operating_metrics_router"]
