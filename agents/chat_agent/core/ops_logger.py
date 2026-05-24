"""Thin helper to record card operations from any module."""
from typing import Protocol

from shared.observability.privacy import hash_identifier
from shared.utils.logger import get_logger

from .domain.card_operation import CardOperationLogEntry

logger = get_logger("chat_agent.ops")


class CardOperationLogStore(Protocol):
    async def record(
        self,
        *,
        entry: CardOperationLogEntry,
    ) -> None:
        """Persist a card-operation log entry."""


_operation_log_store: CardOperationLogStore | None = None


def configure_operation_log_store(store: CardOperationLogStore | None) -> None:
    """Configure the operation-log store at the service/app entry point."""
    global _operation_log_store
    _operation_log_store = store


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
        if _operation_log_store is None:
            raise RuntimeError("operation log store is not configured")
        entry = CardOperationLogEntry.recorded(
            user_id=user_id,
            user_name=user_name,
            action=action,
            result=result,
            table_id=table_id,
            record_id=record_id,
            fields=fields,
            error_message=error_message,
        )
        await _operation_log_store.record(entry=entry)
        for event in entry.pull_events():
            logger.info(
                "op_recorded",
                action=event.action,
                user_hash=hash_identifier(event.user_id),
                result_status=event.result.value,
            )
    except Exception as e:
        logger.error("op_record_failed", action=action, error=str(e))
