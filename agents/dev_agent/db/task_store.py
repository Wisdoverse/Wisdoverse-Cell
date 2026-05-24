"""SQLAlchemy adapter for Dev task persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import DevTaskId, WorkPackageId

from ..core.domain.lifecycle.task_lifecycle import TaskStatus
from ..core.domain.task_values import RiskLevel, risk_level_value
from ..core.repositories import DevTaskRepositoryPort
from .repository import DevTaskRepository


class SqlAlchemyDevTaskStore(DevTaskRepositoryPort):
    """SQLAlchemy-backed Dev task store."""

    def __init__(self, session: AsyncSession):
        self._tasks = DevTaskRepository(session)

    async def create_task(
        self,
        wp_id: WorkPackageId,
        task_title: str,
        risk_level: RiskLevel | str = RiskLevel.MEDIUM,
    ):
        return await self._tasks.create_task(
            wp_id=WorkPackageId(int(wp_id)),
            task_title=task_title,
            risk_level=risk_level_value(risk_level),
        )

    async def get_by_wp_id(self, wp_id: WorkPackageId):
        return await self._tasks.get_by_wp_id(WorkPackageId(int(wp_id)))

    async def get_by_id(self, task_id: DevTaskId):
        return await self._tasks.get_by_id(DevTaskId(str(task_id)))

    async def get_by_mr_iid(self, mr_iid: int):
        return await self._tasks.get_by_mr_iid(mr_iid)

    async def update_status(
        self,
        task_id: DevTaskId,
        new_status: TaskStatus,
        **kwargs,
    ) -> bool:
        return await self._tasks.update_status(
            DevTaskId(str(task_id)),
            TaskStatus(str(new_status)),
            **kwargs,
        )

    async def mark_polled(self, task_id: DevTaskId, *, polled_at) -> bool:
        return await self._tasks.mark_polled(
            DevTaskId(str(task_id)),
            polled_at=polled_at,
        )

    async def list_active_tasks(self):
        return await self._tasks.list_active_tasks()

    async def list_pending_tasks(self, limit: int = 5):
        return await self._tasks.list_pending_tasks(limit=limit)

    async def list_planning_tasks(self, limit: int = 5):
        return await self._tasks.list_planning_tasks(limit=limit)

    async def list_failed_tasks(self, limit: int = 50):
        return await self._tasks.list_failed_tasks(limit=limit)

    async def count_active_workflows(self) -> int:
        return await self._tasks.count_active_workflows()

    async def expire_stale_pending(self, hours: int = 24) -> int:
        return await self._tasks.expire_stale_pending(hours=hours)
