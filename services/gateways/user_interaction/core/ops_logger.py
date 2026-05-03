"""Thin helper to record card operations from any module."""
import json

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from ..db.database import db_manager
from ..db.repository import CardOperationRepository

logger = get_logger("chat_agent.ops")


def _extract_assignee(fields: dict) -> str:
    dri = fields.get("DRI (负责人)")
    if isinstance(dri, list) and dri:
        first = dri[0]
        if isinstance(first, dict):
            return first.get("name", "") or first.get("text", "")
    return ""


async def record_op(
    user_id: str,
    user_name: str,
    action: str,
    result: str = "success",
    table_id: str = "",
    record_id: str = "",
    fields: dict | None = None,
    error_message: str = "",
):
    """Record a card operation. Fire-and-forget — never raises."""
    try:
        assignee = _extract_assignee(fields) if fields else ""
        snapshot = json.dumps(fields, ensure_ascii=False) if fields else "{}"
        async with db_manager.session() as session:
            repo = CardOperationRepository(session)
            await repo.record(
                user_id=user_id,
                user_name=user_name,
                action=action,
                result=result,
                table_id=table_id,
                record_id=record_id,
                assignee_name=assignee,
                fields_snapshot=snapshot,
                error_message=error_message,
            )
        logger.info(
            "op_recorded",
            action=action,
            user_hash=hash_identifier(user_id),
            result=result,
        )
    except Exception as e:
        logger.error("op_record_failed", action=action, error=str(e))
