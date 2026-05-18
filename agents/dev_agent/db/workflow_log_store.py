"""SQLAlchemy adapter for Dev workflow logs."""

from ..core.repositories import DevWorkflowLogRepositoryPort
from .repository import DevWorkflowLogRepository


class SqlAlchemyDevWorkflowLogStore(DevWorkflowLogRepositoryPort):
    """Session-scoped workflow log store."""

    def __init__(self, session):
        self._repo = DevWorkflowLogRepository(session)

    async def create_log(self, task_id: str, **kwargs):
        return await self._repo.create_log(task_id, **kwargs)

    async def get_by_task_id(self, task_id: str):
        return await self._repo.get_by_task_id(task_id)
