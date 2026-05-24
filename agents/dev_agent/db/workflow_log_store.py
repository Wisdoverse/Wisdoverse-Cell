"""SQLAlchemy adapter for Dev workflow logs."""

from shared.core.identifiers import DevTaskId

from ..core.repositories import DevWorkflowLogRepositoryPort, DevWorkflowLogSnapshot
from .repository import DevWorkflowLogRepository


class SqlAlchemyDevWorkflowLogStore(DevWorkflowLogRepositoryPort):
    """Session-scoped workflow log store."""

    def __init__(self, session):
        self._repo = DevWorkflowLogRepository(session)

    async def create_log(self, task_id: DevTaskId, **kwargs):
        return DevWorkflowLogSnapshot.from_record(
            await self._repo.create_log(DevTaskId(str(task_id)), **kwargs)
        )

    async def get_by_task_id(self, task_id: DevTaskId):
        row = await self._repo.get_by_task_id(DevTaskId(str(task_id)))
        if row is None:
            return None
        return DevWorkflowLogSnapshot.from_record(row)
