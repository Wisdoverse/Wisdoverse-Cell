"""dev_agent owns its native executor receipts and database session."""

from shared.infra.native_executor_store import (
    SqlAlchemyNativeExecutorLedger,
    executor_ledger_table,
)

from .database import db_manager

executor_table = executor_ledger_table("dev_agent_executor_requests")
executor_ledger = SqlAlchemyNativeExecutorLedger(db_manager.session, executor_table)
EXECUTOR_ACTIONS = frozenset(
    [
        "get_task_status",
        "list_active_workflows",
        "list_failed",
        "retry_task",
        "cancel_workflow",
        "approve_workflow",
    ]
)
