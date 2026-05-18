"""Bitable confirm/reject API — called by gateway on card button clicks."""
import asyncio
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from shared.infra.denial_tracker import DenialTracker
from shared.integrations.feishu.bitable import bitable_service
from shared.utils.logger import get_logger

from ..core.bitable_operations import (
    BitableConfirmCommand,
    BitableCreateCommand,
    BitableOperationLogCommand,
    BitableOperationUseCase,
    BitableRejectCommand,
)
from ..core.card_ports import require_tool_card_renderer
from ..core.ops_logger import record_op
from ..core.tools import get_pending_op
from ..service.config_factory import build_user_interaction_core_config

logger = get_logger("chat_agent.bitable_api")

_denial_tracker: DenialTracker | None = None


def get_denial_tracker() -> DenialTracker:
    global _denial_tracker  # noqa: PLW0603
    if _denial_tracker is None:
        import redis.asyncio as aioredis

        from shared.config import settings

        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        _denial_tracker = DenialTracker(redis=r)
    return _denial_tracker

_background_tasks: set[asyncio.Task] = set()
_bitable_operation_use_case = BitableOperationUseCase()

router = APIRouter(prefix="/api/bitable", tags=["bitable"])


class ConfirmRequest(BaseModel):
    record_id: str = ""
    fields: dict = {}
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


class CreateRequest(BaseModel):
    fields: dict = {}
    table_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action_id: str = ""


def _track_operation(log: BitableOperationLogCommand | None) -> None:
    if log is None:
        return
    task = asyncio.create_task(
        record_op(
            user_id=log.user_id,
            user_name=log.user_name,
            action=log.action,
            result=log.result,
            table_id=log.table_id,
            record_id=log.record_id,
            fields=log.fields,
            error_message=log.error_message,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _log_confirm_result(
    *,
    operation: str,
    record_id: str = "",
    result: str,
    error_message: str = "",
) -> None:
    if result == "success":
        logger.info(operation, record_id=record_id)
    else:
        logger.error(operation, record_id=record_id, error=error_message)


@router.post("/confirm")
async def confirm_update(req: ConfirmRequest) -> dict[str, Any]:
    """Execute the bitable update and return a result card dict."""
    result = await _bitable_operation_use_case.confirm_update(
        BitableConfirmCommand(
            record_id=req.record_id,
            fields=req.fields,
            table_id=req.table_id,
            user_id=req.user_id,
            user_name=req.user_name,
            action_id=req.action_id,
        ),
        bitable=bitable_service,
        pending_lookup=get_pending_op,
        renderer=require_tool_card_renderer(),
        config=build_user_interaction_core_config(),
    )
    _track_operation(result.operation_log)
    if result.operation_log is not None:
        _log_confirm_result(
            operation=(
                "bitable_update_confirmed"
                if result.operation_log.result == "success"
                else "bitable_update_failed"
            ),
            record_id=result.operation_log.record_id,
            result=result.operation_log.result,
            error_message=result.operation_log.error_message,
        )
    return result.card


class RejectRequest(BaseModel):
    action_type: str = ""
    user_id: str = ""
    user_name: str = ""
    fields: dict = {}
    table_id: str = ""
    record_id: str = ""


@router.post("/reject")
async def reject_operation(req: RejectRequest) -> dict[str, Any]:
    """Record rejection and return a cancelled card dict."""
    result = await _bitable_operation_use_case.reject_operation(
        BitableRejectCommand(
            action_type=req.action_type,
            user_id=req.user_id,
            user_name=req.user_name,
            fields=req.fields,
            table_id=req.table_id,
            record_id=req.record_id,
        ),
        renderer=require_tool_card_renderer(),
        denial_tracker=(
            get_denial_tracker() if req.action_type and req.user_id else None
        ),
    )
    _track_operation(result.operation_log)
    if result.denial_error:
        logger.warning("denial_tracking_failed", error=result.denial_error)
    return result.card


@router.post("/create")
async def create_record(req: CreateRequest) -> dict[str, Any]:
    """Create a new bitable record and return a result card dict."""
    result = await _bitable_operation_use_case.create_record(
        BitableCreateCommand(
            fields=req.fields,
            table_id=req.table_id,
            user_id=req.user_id,
            user_name=req.user_name,
            action_id=req.action_id,
        ),
        bitable=bitable_service,
        pending_lookup=get_pending_op,
        renderer=require_tool_card_renderer(),
        config=build_user_interaction_core_config(),
    )
    _track_operation(result.operation_log)
    if result.operation_log is not None:
        _log_confirm_result(
            operation=(
                "bitable_record_created"
                if result.operation_log.result == "success"
                else "bitable_create_failed"
            ),
            record_id=result.operation_log.record_id,
            result=result.operation_log.result,
            error_message=result.operation_log.error_message,
        )
    return result.card
