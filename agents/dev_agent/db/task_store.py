"""SQLAlchemy adapter for Dev task persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.repositories import DevTaskRepositoryPort
from .repository import DevTaskRepository


class SqlAlchemyDevTaskStore(DevTaskRepositoryPort):
    """SQLAlchemy-backed Dev task store."""

    def __init__(self, session: AsyncSession):
        self._tasks = DevTaskRepository(session)

    async def create_task(
        self,
        wp_id: int,
        task_title: str,
        risk_level: str = "MEDIUM",
    ):
        return await self._tasks.create_task(
            wp_id=wp_id,
            task_title=task_title,
            risk_level=risk_level,
        )

    async def get_by_wp_id(self, wp_id: int):
        return await self._tasks.get_by_wp_id(wp_id)

    async def get_by_id(self, task_id: str):
        return await self._tasks.get_by_id(task_id)

    async def get_by_mr_iid(self, mr_iid: int):
        return await self._tasks.get_by_mr_iid(mr_iid)

    async def update_status(self, task_id: str, new_status: str, **kwargs) -> bool:
        return await self._tasks.update_status(task_id, new_status, **kwargs)

    async def mark_polled(self, task_id: str, *, polled_at) -> bool:
        return await self._tasks.mark_polled(task_id, polled_at=polled_at)

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
