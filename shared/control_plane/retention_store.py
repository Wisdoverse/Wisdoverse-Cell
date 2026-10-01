"""Atomic physical cleanup with replay guards, pending delivery and evidence pins."""

import hashlib
import json
from datetime import datetime
from typing import Any
from typing import cast as type_cast

from sqlalchemy import Text, cast, delete, exists, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from .domain.physical_retention import RetentionCommand, RetentionReceipt, idempotency_digest
from .domain_records import audit_event_record
from .knowledge_models import KnowledgeTable, KnowledgeTombstoneTable
from .retention_models import AuditRetentionTombstoneTable, RetentionRunTable
from .tables import (
    ArtifactTable,
    AuditEventTable,
    CompanyContextTable,
    ControlPlaneEventOutboxTable,
)


class SqlAlchemyRetentionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def apply(
        self, command: RetentionCommand, *, request_id: str | None, now: datetime, cutoff: datetime
    ) -> RetentionReceipt:
        company = await self._session.scalar(
            select(CompanyContextTable)
            .where(CompanyContextTable.company_id == command.company_id)
            .with_for_update()
        )
        if company is None:
            raise ValueError("retention_company_not_found")
        if not command.dry_run:
            previous = await self._session.get(RetentionRunTable, (command.company_id, request_id))
            if previous is not None:
                if previous.command_hash != command.digest:
                    raise ValueError("retention_request_conflict")
                return RetentionReceipt.model_validate(previous.receipt)
        pending = exists(
            select(ControlPlaneEventOutboxTable.event_id).where(
                ControlPlaneEventOutboxTable.correlation_id == AuditEventTable.audit_event_id,
                ControlPlaneEventOutboxTable.status != "published",
            )
        )
        if self._session.get_bind().dialect.name == "postgresql":
            from sqlalchemy import func

            evidence_pin = cast(
                ArtifactTable.metadata_json["evidence"]["audit_events"], JSONB
            ).contains(func.jsonb_build_array(AuditEventTable.audit_event_id))
        else:
            evidence_pin = cast(ArtifactTable.metadata_json, Text).contains(
                literal('"') + AuditEventTable.audit_event_id + literal('"')
            )
        pinned = exists(
            select(ArtifactTable.artifact_id).where(
                ArtifactTable.company_id == command.company_id, evidence_pin
            )
        )
        candidates = list(
            (
                await self._session.scalars(
                    select(AuditEventTable)
                    .where(
                        AuditEventTable.company_id == command.company_id,
                        AuditEventTable.created_at < cutoff,
                        ~pending,
                        ~pinned,
                    )
                    .order_by(AuditEventTable.created_at, AuditEventTable.audit_event_id)
                    .limit(command.batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        knowledge = list(
            (
                await self._session.scalars(
                    select(KnowledgeTable)
                    .where(
                        KnowledgeTable.company_id == command.company_id,
                        (
                            (KnowledgeTable.retention_until < now)
                            | (KnowledgeTable.deleted_at < cutoff)
                        ),
                    )
                    .order_by(KnowledgeTable.knowledge_id)
                    .limit(command.batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        outbox_count = 0
        if not command.dry_run:
            for row in candidates:
                record = audit_event_record(row)
                compact = record.model_dump(
                    mode="json", exclude={"actor_id", "detail", "idempotency_key"}
                )
                compact.update(
                    actor_id="retention",
                    detail={
                        "retention_tombstone": True,
                        "detail_sha256": hashlib.sha256(
                            json.dumps(record.detail, sort_keys=True).encode()
                        ).hexdigest(),
                    },
                )
                self._session.add(
                    AuditRetentionTombstoneTable(
                        audit_event_id=row.audit_event_id,
                        company_id=command.company_id,
                        idempotency_hash=idempotency_digest(command.company_id, row.idempotency_key)
                        if row.idempotency_key
                        else None,
                        receipt=compact,
                        purged_at=now,
                    )
                )
                removed = await self._session.execute(
                    delete(ControlPlaneEventOutboxTable).where(
                        ControlPlaneEventOutboxTable.correlation_id == row.audit_event_id,
                        ControlPlaneEventOutboxTable.status == "published",
                    )
                )
                outbox_count += type_cast(CursorResult[Any], removed).rowcount
                await self._session.delete(row)
            for knowledge_row in knowledge:
                if (
                    await self._session.get(KnowledgeTombstoneTable, knowledge_row.knowledge_id)
                    is None
                ):
                    self._session.add(
                        KnowledgeTombstoneTable(
                            knowledge_id=knowledge_row.knowledge_id,
                            company_id=command.company_id,
                            actor_id="retention",
                            version=knowledge_row.version,
                            deleted_at=now,
                        )
                    )
                await self._session.delete(knowledge_row)
        receipt = RetentionReceipt(
            company_id=command.company_id,
            dry_run=command.dry_run,
            audit_cutoff=cutoff,
            eligible_audit_events=len(candidates),
            purged_audit_events=0 if command.dry_run else len(candidates),
            purged_published_outbox_events=outbox_count,
            expired_knowledge=len(knowledge),
            purged_knowledge=0 if command.dry_run else len(knowledge),
        )
        if not command.dry_run:
            self._session.add(
                RetentionRunTable(
                    company_id=command.company_id,
                    request_id=request_id,
                    command_hash=command.digest,
                    receipt=receipt.model_dump(mode="json"),
                    created_at=now,
                )
            )
        await self._session.flush()
        return receipt
