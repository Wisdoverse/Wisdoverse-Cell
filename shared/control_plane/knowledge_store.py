"""SQLAlchemy adapter for company knowledge pointers and tombstones."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .domain.knowledge import KnowledgeRecord, KnowledgeTombstone
from .knowledge_models import KnowledgeTable, KnowledgeTombstoneTable
from .knowledge_ports import KnowledgeStore
from .models import Artifact, AuditEvent
from .tables import AgentRoleTable, ArtifactTable, CompanyContextTable


class SqlAlchemyKnowledgeStore(KnowledgeStore):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_artifact(self, artifact_id: str) -> Artifact | None:
        result = await self._session.execute(
            select(ArtifactTable).where(ArtifactTable.artifact_id == artifact_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return Artifact.model_validate(
            {
                "artifact_id": row.artifact_id,
                "company_id": row.company_id,
                "artifact_type": row.artifact_type,
                "title": row.title,
                "uri": row.uri,
                "content_hash": row.content_hash,
                "run_id": row.run_id,
                "work_item_id": row.work_item_id,
                "goal_id": row.goal_id,
                "created_by_agent_id": row.created_by_agent_id,
                "metadata": row.metadata_json,
                "created_at": row.created_at,
            }
        )

    async def company_has_roles(self, company_id: str, role_ids: tuple[str, ...]) -> bool:
        if not role_ids:
            return True
        result = await self._session.execute(
            select(AgentRoleTable.role_id).where(
                AgentRoleTable.company_id == company_id,
                AgentRoleTable.role_id.in_(role_ids),
            )
        )
        return set(result.scalars().all()) == set(role_ids)

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await SqlAlchemyControlPlaneAuditEventStore(self._session).append_audit_event(event)

    async def get_knowledge(self, knowledge_id: str, *, company_id: str) -> KnowledgeRecord | None:
        result = await self._session.execute(
            select(KnowledgeTable).where(
                KnowledgeTable.knowledge_id == knowledge_id,
                KnowledgeTable.company_id == company_id,
            )
        )
        row = result.scalar_one_or_none()
        return _record(row) if row is not None else None

    async def create_knowledge(self, record: KnowledgeRecord) -> KnowledgeRecord:
        # Serialize creation with retention before checking permanent deletion.
        await self._session.scalar(
            select(CompanyContextTable)
            .where(CompanyContextTable.company_id == record.company_id)
            .with_for_update()
        )
        if await self._session.get(KnowledgeTombstoneTable, record.knowledge_id) is not None:
            raise ValueError("knowledge_id_permanently_deleted")
        row = KnowledgeTable(**record.model_dump())
        self._session.add(row)
        await self._session.flush()
        return _record(row)

    async def revise_knowledge(
        self, record: KnowledgeRecord, *, expected_version: int
    ) -> KnowledgeRecord | None:
        values = record.model_dump(
            exclude={
                "knowledge_id",
                "company_id",
                "source_artifact_id",
                "source_company_id",
                "owner_actor_id",
                "created_at",
            }
        )
        result = await self._session.execute(
            update(KnowledgeTable)
            .where(
                KnowledgeTable.knowledge_id == record.knowledge_id,
                KnowledgeTable.company_id == record.company_id,
                KnowledgeTable.version == expected_version,
                KnowledgeTable.deleted_at.is_(None),
            )
            .values(**values)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            return None
        await self._session.flush()
        return await self.get_knowledge(record.knowledge_id, company_id=record.company_id)

    async def delete_knowledge(
        self, record: KnowledgeRecord, tombstone: KnowledgeTombstone
    ) -> bool:
        values = {
            "deleted_at": record.deleted_at,
            "deleted_by_actor_id": record.deleted_by_actor_id,
        }
        result = await self._session.execute(
            update(KnowledgeTable)
            .where(
                KnowledgeTable.knowledge_id == record.knowledge_id,
                KnowledgeTable.company_id == record.company_id,
                KnowledgeTable.version == record.version,
                KnowledgeTable.deleted_at.is_(None),
            )
            .values(**values)
        )
        if cast(CursorResult[Any], result).rowcount != 1:
            return False
        self._session.add(KnowledgeTombstoneTable(**tombstone.model_dump()))
        await self._session.flush()
        return True


def _record(row: KnowledgeTable) -> KnowledgeRecord:
    return KnowledgeRecord.model_validate(
        {
            "knowledge_id": row.knowledge_id,
            "company_id": row.company_id,
            "source_artifact_id": row.source_artifact_id,
            "source_company_id": row.source_company_id,
            "owner_actor_id": row.owner_actor_id,
            "reader_role_ids": tuple(row.reader_role_ids or ()),
            "version": row.version,
            "retention_until": _utc(row.retention_until),
            "created_at": _utc(row.created_at),
            "updated_at": _utc(row.updated_at),
            "deleted_at": _utc(row.deleted_at),
            "deleted_by_actor_id": row.deleted_by_actor_id,
        }
    )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
