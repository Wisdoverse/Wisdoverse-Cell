"""Authenticated operator review queues a confirmed requirement for PJM."""

from fastapi import APIRouter, Depends, Header, Path, Request

from shared.api import raise_api_error
from shared.config import settings
from shared.control_plane.operator_auth import OperatorPrincipal, require_operator

from ..adapters.delivery_context import HttpDeliveryContextVerifier
from ..core.delivery_handoff import DeliveryHandoffUseCase
from ..core.domain.delivery_handoff import (
    DeliveryHandoffCommand,
    DeliveryHandoffReceipt,
    DeliveryReviewSnapshot,
)
from ..db.database import db_manager
from ..db.delivery_handoff import SqlAlchemyDeliveryHandoffStore

router = APIRouter(prefix="/api/v1/requirements", tags=["delivery-handoff"])


def get_handoff_use_case(request: Request) -> DeliveryHandoffUseCase:
    if not settings.delivery_handoff_enabled or not settings.delivery_context_base_url:
        raise_api_error(
            status_code=503, code="delivery.disabled", message="delivery_handoff_disabled"
        )
    return DeliveryHandoffUseCase(
        SqlAlchemyDeliveryHandoffStore(db_manager.session),
        company_id=settings.control_plane_company_id,
        context_verifier=HttpDeliveryContextVerifier(
            settings.delivery_context_base_url,
            authorization=request.headers.get("X-Control-Plane-Operator-Token", ""),
            internal_key=settings.internal_service_key,
        ),
    )


@router.get("/{requirement_id}/delivery-review", response_model=DeliveryReviewSnapshot)
async def review_delivery_handoff(
    requirement_id: str = Path(min_length=1, max_length=32),
    principal: OperatorPrincipal = Depends(require_operator),
    use_case: DeliveryHandoffUseCase = Depends(get_handoff_use_case),
) -> DeliveryReviewSnapshot:
    principal.require("work:execute", settings.control_plane_company_id)
    try:
        return await use_case.review(requirement_id)
    except ValueError as exc:
        raise_api_error(status_code=404, code="delivery.requirement_not_found", message=str(exc))


@router.post("/{requirement_id}/delivery-handoff", response_model=DeliveryHandoffReceipt)
async def queue_delivery_handoff(
    command: DeliveryHandoffCommand,
    requirement_id: str = Path(min_length=1, max_length=32),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=64),
    trace_id: str | None = Header(default=None, alias="X-Trace-ID", max_length=64),
    principal: OperatorPrincipal = Depends(require_operator),
    use_case: DeliveryHandoffUseCase = Depends(get_handoff_use_case),
) -> DeliveryHandoffReceipt:
    principal.require("work:execute", command.company_id)
    try:
        return await use_case.execute(
            requirement_id,
            command,
            reviewed_by=principal.actor_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
    except ValueError as exc:
        code = str(exc)
        raise_api_error(
            status_code=404 if code == "requirement_not_found" else 409,
            code=f"delivery.{code}",
            message=code,
        )
