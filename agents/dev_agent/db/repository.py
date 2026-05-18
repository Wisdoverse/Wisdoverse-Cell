"""Repository layer for dev_agent."""
import inspect
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.ids import generate_id
from shared.schemas.event import Event
from shared.utils.logger import get_logger

from ..core.task_lifecycle import ACTIVE_STATUSES, IN_PROGRESS_STATUSES, can_transition
from ..models.dev import DevAgentEventOutbox, DevAgentTask, DevAgentWorkflowLog

logger = get_logger("dev_agent.repository")


class DevTaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        if not can_transition(task.status, new_status):
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

    async def mark_polled(self, task_id: str, *, polled_at: datetime) -> bool:
        task = await self.get_by_id(task_id)
        if not task:
            logger.error("mark_polled_task_not_found", task_id=task_id)
            return False
        task.last_polled_at = polled_at
        task.updated_at = polled_at
        await self.session.flush()
        return True

    async def list_active_tasks(self) -> list[DevAgentTask]:
        result = await self.session.execute(
            select(DevAgentTask).where(
                DevAgentTask.status.in_(ACTIVE_STATUSES)
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
                DevAgentTask.status.in_(IN_PROGRESS_STATUSES)
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


class DevEventOutboxRepository:
    """Dev integration-event outbox data access."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: Event) -> DevAgentEventOutbox:
        """Store an integration event in the local transaction outbox."""
        payload = event.model_dump(mode="json")
        row = DevAgentEventOutbox(
            event_id=event.event_id,
            event_type=event.event_type,
            source_agent=event.source_agent,
            payload=payload["payload"],
            schema_version=event.schema_version,
            trace_id=payload["metadata"].get("trace_id"),
            correlation_id=payload["metadata"].get("correlation_id"),
            retry_count=payload["metadata"].get("retry_count", 0),
            status="pending",
            attempts=0,
        )
        add_result = self.session.add(row)
        if inspect.isawaitable(add_result):
            await add_result
        flush_result = self.session.flush()
        if inspect.isawaitable(flush_result):
            await flush_result
        return row

    async def list_pending(self, limit: int = 100) -> list[DevAgentEventOutbox]:
        """List pending events for retry dispatch."""
        result = await self.session.execute(
            select(DevAgentEventOutbox)
            .where(DevAgentEventOutbox.status == "pending")
            .order_by(DevAgentEventOutbox.created_at, DevAgentEventOutbox.event_id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: str) -> None:
        """Mark an outbox row as published."""
        await self.session.execute(
            update(DevAgentEventOutbox)
            .where(DevAgentEventOutbox.event_id == event_id)
            .values(
                status="published",
                attempts=DevAgentEventOutbox.attempts + 1,
                published_at=datetime.now(UTC),
                last_error=None,
            )
        )

    async def mark_failed(self, event_id: str, error: str) -> None:
        """Record a publish failure without removing the pending event."""
        await self.session.execute(
            update(DevAgentEventOutbox)
            .where(DevAgentEventOutbox.event_id == event_id)
            .values(
                status="pending",
                attempts=DevAgentEventOutbox.attempts + 1,
                last_error=error[:1000],
            )
        )
