"""Repository layer for dev_agent."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.ids import generate_id
from shared.utils.logger import get_logger

from ..models.dev import DevAgentTask, DevAgentWorkflowLog
from ..models.schemas import VALID_TRANSITIONS

logger = get_logger("dev_agent.repository")

_ACTIVE_STATUSES = [
    "executing",
    "security_scanning",
    "mr_creating",
    "mr_created",
    "qa_triggered",
    "reviewing",
]

_IN_PROGRESS_STATUSES = [
    "planning",
    "awaiting_approval",
    *_ACTIVE_STATUSES,
]


class DevTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        allowed = VALID_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    async def create_task(
        self, wp_id: int, task_title: str, risk_level: str = "MEDIUM"
    ) -> DevAgentTask | None:
        """Create task atomically. Returns None if wp_id already exists (idempotent)."""
        stmt = pg_insert(DevAgentTask).values(
            id=generate_id("dev"),
            wp_id=wp_id,
            task_title=task_title,
            risk_level=risk_level,
        ).on_conflict_do_nothing(index_elements=["wp_id"])
        result = await self.session.execute(stmt)
        await self.session.flush()
        if result.rowcount == 0:
            return None  # Already exists
        return await self.get_by_wp_id(wp_id)

    async def get_by_wp_id(self, wp_id: int) -> DevAgentTask | None:
        result = await self.session.execute(
            select(DevAgentTask).where(DevAgentTask.wp_id == wp_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, task_id: str) -> DevAgentTask | None:
        result = await self.session.execute(
            select(DevAgentTask).where(DevAgentTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_by_mr_iid(self, mr_iid: int) -> DevAgentTask | None:
        result = await self.session.execute(
            select(DevAgentTask).where(DevAgentTask.mr_iid == mr_iid)
        )
        return result.scalar_one_or_none()

    async def update_status(self, task_id: str, new_status: str, **kwargs) -> bool:
        task = await self.get_by_id(task_id)
        if not task:
            logger.error("update_status_task_not_found", task_id=task_id, target_status=new_status)
            return False
        if not self._is_valid_transition(task.status, new_status):
            logger.error(
                "invalid_status_transition",
                task_id=task_id,
                from_status=task.status,
                to_status=new_status,
            )
            return False
        task.status = new_status
        task.updated_at = datetime.now(UTC)
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        await self.session.flush()
        return True

    async def list_active_tasks(self) -> list[DevAgentTask]:
        result = await self.session.execute(
            select(DevAgentTask).where(
                DevAgentTask.status.in_(_ACTIVE_STATUSES)
            )
        )
        return list(result.scalars().all())

    async def list_pending_tasks(self, limit: int = 5) -> list[DevAgentTask]:
        result = await self.session.execute(
            select(DevAgentTask)
            .where(DevAgentTask.status == "pending")
            .order_by(DevAgentTask.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_failed_tasks(self, limit: int = 50) -> list[DevAgentTask]:
        result = await self.session.execute(
            select(DevAgentTask)
            .where(DevAgentTask.status == "failed")
            .order_by(DevAgentTask.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_planning_tasks(self, limit: int = 5) -> list[DevAgentTask]:
        """List tasks in 'planning' status (for retry re-entry via reconcile)."""
        result = await self.session.execute(
            select(DevAgentTask)
            .where(DevAgentTask.status == "planning")
            .order_by(DevAgentTask.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_active_workflows(self) -> int:
        result = await self.session.execute(
            select(func.count(DevAgentTask.id)).where(
                DevAgentTask.status.in_(_IN_PROGRESS_STATUSES)
            )
        )
        return result.scalar_one()

    async def expire_stale_pending(self, hours: int = 24) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        result = await self.session.execute(
            update(DevAgentTask)
            .where(DevAgentTask.status == "pending")
            .where(DevAgentTask.created_at < cutoff)
            .values(status="expired", updated_at=datetime.now(UTC))
        )
        await self.session.flush()
        return result.rowcount


class DevWorkflowLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_log(self, task_id: str, **kwargs) -> DevAgentWorkflowLog:
        log = DevAgentWorkflowLog(
            id=generate_id("dwl"), task_id=task_id, **kwargs
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_by_task_id(self, task_id: str) -> DevAgentWorkflowLog | None:
        result = await self.session.execute(
            select(DevAgentWorkflowLog)
            .where(DevAgentWorkflowLog.task_id == task_id)
            .order_by(DevAgentWorkflowLog.created_at.desc())
        )
        return result.scalar_one_or_none()
