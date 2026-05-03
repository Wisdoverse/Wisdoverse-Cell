"""Repository - pjm_agent"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.utils.logger import get_logger

from ..models.pm import AlertLog, DecompositionRecord, PMConfigCache

logger = get_logger("pjm_agent.repository")


class AlertLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, alert_type: str, target: str, message: str, severity: str = "warning"
    ) -> AlertLog:
        log = AlertLog(alert_type=alert_type, target=target, message=message, severity=severity)
        self.session.add(log)
        await self.session.flush()
        return log

    async def get_recent(self, alert_type: str | None = None, limit: int = 20) -> list[AlertLog]:
        query = select(AlertLog).order_by(AlertLog.created_at.desc()).limit(limit)
        if alert_type:
            query = query.where(AlertLog.alert_type == alert_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PMConfigCacheRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, config_type: str) -> Optional[dict[str, Any]]:
        result = await self.session.execute(
            select(PMConfigCache).where(PMConfigCache.config_type == config_type)
        )
        cache = result.scalar_one_or_none()
        if cache and cache.config_data:
            return json.loads(cache.config_data)
        return None

    async def set(self, config_type: str, data: dict[str, Any]) -> None:
        result = await self.session.execute(
            select(PMConfigCache).where(PMConfigCache.config_type == config_type)
        )
        cache = result.scalar_one_or_none()
        if cache:
            cache.config_data = json.dumps(data, ensure_ascii=False)
            cache.updated_at = datetime.now(UTC)
        else:
            cache = PMConfigCache(
                config_type=config_type, config_data=json.dumps(data, ensure_ascii=False)
            )
            self.session.add(cache)
        await self.session.flush()


class DecompositionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, wp_id: int, project_id: int, decompose_result: dict, assignee_id: int | None = None
    ) -> DecompositionRecord:
        record = DecompositionRecord(
            wp_id=wp_id,
            project_id=project_id,
            assignee_id=assignee_id,
            decompose_result=decompose_result,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_by_wp_id(self, wp_id: int) -> DecompositionRecord | None:
        result = await self.session.execute(
            select(DecompositionRecord).where(DecompositionRecord.wp_id == wp_id)
        )
        return result.scalar_one_or_none()

    async def update_status(self, wp_id: int, status: str, approved_by: str | None = None) -> bool:
        record = await self.get_by_wp_id(wp_id)
        if not record:
            return False
        record.status = status
        record.updated_at = datetime.now(UTC)
        if approved_by:
            record.approved_by = approved_by
            record.approved_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def get_stale_pending(self, older_than_hours: int = 24) -> list[DecompositionRecord]:
        """Return decomposition records with status='pending' older than the given hours."""
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = await self.session.execute(
            select(DecompositionRecord)
            .where(DecompositionRecord.status == "pending")
            .where(DecompositionRecord.created_at < cutoff)
        )
        return list(result.scalars().all())

    async def delete_by_wp_id(self, wp_id: int) -> bool:
        record = await self.get_by_wp_id(wp_id)
        if not record:
            return False
        await self.session.delete(record)
        await self.session.flush()
        return True
