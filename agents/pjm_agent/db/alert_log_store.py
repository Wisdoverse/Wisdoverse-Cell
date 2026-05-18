"""SQLAlchemy adapter for PJM alert logging."""

from ..core.alert_ports import PJMAlertLogStore
from .database import DatabaseManager
from .repository import AlertLogRepository


class SqlAlchemyPJMAlertLogStore(PJMAlertLogStore):
    """SQLAlchemy-backed alert log store."""

    def __init__(self, db_manager: DatabaseManager):
        self._db_manager = db_manager

    async def record_alerts(self, alerts: list[dict]) -> None:
        async with self._db_manager.session() as session:
            repo = AlertLogRepository(session)
            for alert in alerts:
                await repo.create(
                    alert_type=alert["type"],
                    target=alert.get("task", ""),
                    message=alert["message"],
                    severity=alert["severity"],
                )
