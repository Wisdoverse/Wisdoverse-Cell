"""pjm_agent owns its native executor receipts and database session."""

from shared.infra.native_executor_store import (
    SqlAlchemyNativeExecutorLedger,
    executor_ledger_table,
)

from .database import db_manager

executor_table = executor_ledger_table("pjm_executor_requests")
executor_ledger = SqlAlchemyNativeExecutorLedger(db_manager.session, executor_table)
EXECUTOR_ACTIONS = frozenset(["config", "get_decompose", "retry_decompose"])
