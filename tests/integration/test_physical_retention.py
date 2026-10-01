"""PostgreSQL acceptance for company-scoped physical retention and replay guards."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.control_plane.api import create_control_plane_router
from shared.control_plane.audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from shared.control_plane.domain.knowledge import KnowledgeRecord
from shared.control_plane.domain.physical_retention import RetentionCommand
from shared.control_plane.knowledge_models import KnowledgeTable, KnowledgeTombstoneTable
from shared.control_plane.knowledge_store import SqlAlchemyKnowledgeStore
from shared.control_plane.models import AuditEvent
from shared.control_plane.retention_models import (
    AuditRetentionTombstoneTable,
    RetentionRunTable,
)
from shared.control_plane.retention_store import SqlAlchemyRetentionStore
from shared.control_plane.tables import (
    ArtifactTable,
    AuditEventTable,
    CompanyContextTable,
    ControlPlaneEventOutboxTable,
    control_plane_metadata,
)

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@asynccontextmanager
async def _postgres_session() -> AsyncIterator[AsyncSession]:
    if not DATABASE_URL.startswith(("postgresql+asyncpg://", "postgresql://")):
        pytest.skip("TEST_DATABASE_URL must provide disposable PostgreSQL")
    schema = "physical_retention_test_" + uuid4().hex
    admin = create_async_engine(DATABASE_URL)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
        async with sessions() as session:
            yield session
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


def _operator_token(monkeypatch, *, company_id: str, scopes: list[str]) -> str:
    token = f"physical-retention-{uuid4().hex}"
    monkeypatch.setattr(settings, "control_plane_operators_json", json.dumps([{
        "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        "actor_id": "retention-operator",
        "companies": [company_id],
        "scopes": scopes,
        "role_ids": [],
    }]))
    return token


def _app(session: AsyncSession) -> FastAPI:
    @asynccontextmanager
    async def session_provider():
        yield session

    app = FastAPI()
    app.include_router(create_control_plane_router(session_provider=session_provider))
    return app


async def _seed_company(session: AsyncSession, company_id: str) -> None:
    session.add(CompanyContextTable(company_id=company_id, name=company_id, mission="test"))
    await session.flush()


def _audit(
    *, event_id: str, company_id: str, created_at: datetime, key: str | None = None,
    action: str = "test.recorded",
) -> AuditEventTable:
    return AuditEventTable(
        audit_event_id=event_id,
        company_id=company_id,
        action=action,
        target_type="test",
        target_id=event_id,
        actor_type="system",
        actor_id="test",
        idempotency_key=key,
        detail={"safe": True},
        created_at=created_at,
    )


async def test_preview_is_company_scoped_and_has_no_persistent_effects(monkeypatch):
    async with _postgres_session() as session:
        company_id = "cmp_retention_preview"
        await _seed_company(session, company_id)
        await _seed_company(session, "cmp_foreign")
        old = datetime.now(UTC) - timedelta(days=100)
        session.add_all([
            _audit(event_id="audit_preview_1", company_id=company_id, created_at=old),
            _audit(event_id="audit_preview_foreign", company_id="cmp_foreign", created_at=old),
        ])
        await session.flush()
        await session.commit()

        monkeypatch.setattr(settings, "control_plane_retention_enabled", False)
        token = _operator_token(monkeypatch, company_id=company_id, scopes=["audit:retention"])
        app = _app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/control-plane/retention",
                headers={"X-Control-Plane-Operator-Token": token},
                json={"company_id": company_id, "dry_run": True, "batch_size": 10},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["eligible_audit_events"] == 1
        assert body["purged_audit_events"] == 0
        assert await session.scalar(select(func.count()).select_from(AuditEventTable)) == 2
        assert await session.scalar(select(func.count()).select_from(AuditRetentionTombstoneTable)) == 0
        assert await session.scalar(select(func.count()).select_from(RetentionRunTable)) == 0

        monkeypatch.setattr(settings, "control_plane_retention_enabled", True)
        apply_headers = {
            "X-Control-Plane-Operator-Token": token,
            "Idempotency-Key": "preview-api-apply-1",
        }
        payload = {"company_id": company_id, "dry_run": False, "batch_size": 10}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            applied = await client.post(
                "/api/v1/control-plane/retention", headers=apply_headers, json=payload
            )
            replayed = await client.post(
                "/api/v1/control-plane/retention", headers=apply_headers, json=payload
            )
            changed = await client.post(
                "/api/v1/control-plane/retention", headers=apply_headers,
                json={**payload, "batch_size": 5},
            )
        assert applied.status_code == 200, applied.text
        assert replayed.status_code == 200, replayed.text
        assert replayed.json() == applied.json()
        assert changed.status_code == 409
        assert await session.get(AuditEventTable, "audit_preview_1") is None
        assert await session.get(AuditEventTable, "audit_preview_foreign") is not None
        assert await session.scalar(select(func.count()).select_from(RetentionRunTable)) == 1


async def test_apply_batches_replays_exact_receipt_and_rejects_changed_request():
    async with _postgres_session() as session:
        company_id = "cmp_retention_batch"
        now = datetime(2026, 10, 1, 12, tzinfo=UTC)
        cutoff = now - timedelta(days=90)
        await _seed_company(session, company_id)
        await _seed_company(session, "cmp_foreign")
        session.add_all([
            _audit(event_id="audit_old", company_id=company_id,
                   created_at=cutoff - timedelta(microseconds=1), key="old-key"),
            _audit(event_id="audit_old_b", company_id=company_id,
                   created_at=cutoff - timedelta(microseconds=1), key="old-key-b"),
            _audit(event_id="audit_boundary", company_id=company_id,
                   created_at=cutoff, key="boundary-key"),
            _audit(event_id="audit_foreign", company_id="cmp_foreign",
                   created_at=cutoff - timedelta(days=1), key="foreign-key"),
        ])
        await session.flush()
        command = RetentionCommand(company_id=company_id, dry_run=False, batch_size=1)
        store = SqlAlchemyRetentionStore(session)
        receipt = await store.apply(command, request_id="retention-request-1", now=now, cutoff=cutoff)
        await session.commit()

        assert receipt.eligible_audit_events == 1
        assert receipt.purged_audit_events == 1
        assert await session.get(AuditEventTable, "audit_old") is None
        assert await session.get(AuditEventTable, "audit_old_b") is not None
        assert await session.get(AuditEventTable, "audit_boundary") is not None
        assert await session.get(AuditEventTable, "audit_foreign") is not None
        compact = await session.get(AuditRetentionTombstoneTable, "audit_old")
        assert compact is not None
        assert compact.idempotency_hash
        assert "old-key" not in json.dumps(compact.receipt)

        replay = await SqlAlchemyRetentionStore(session).apply(
            command, request_id="retention-request-1", now=now + timedelta(minutes=1),
            cutoff=cutoff + timedelta(minutes=1),
        )
        assert replay == receipt
        with pytest.raises(ValueError, match="retention_request_conflict"):
            await SqlAlchemyRetentionStore(session).apply(
                command.model_copy(update={"batch_size": 5}), request_id="retention-request-1",
                now=now, cutoff=cutoff,
            )
        next_batch = await SqlAlchemyRetentionStore(session).apply(
            command, request_id="retention-request-2", now=now, cutoff=cutoff
        )
        await session.commit()
        assert next_batch.purged_audit_events == 1
        assert await session.get(AuditEventTable, "audit_old_b") is None


async def test_pending_and_artifact_pinned_audits_survive_then_published_outbox_is_removed():
    async with _postgres_session() as session:
        company_id = "cmp_retention_pins"
        cutoff = datetime.now(UTC) - timedelta(days=90)
        now = datetime.now(UTC)
        await _seed_company(session, company_id)
        await _seed_company(session, "cmp_foreign")
        session.add_all([
            _audit(event_id="audit_pending", company_id=company_id,
                   created_at=cutoff - timedelta(days=2)),
            _audit(event_id="audit_pinned", company_id=company_id,
                   created_at=cutoff - timedelta(days=2)),
            _audit(event_id="audit_published", company_id=company_id,
                   created_at=cutoff - timedelta(days=2)),
            ArtifactTable(
                artifact_id="artifact_pin", company_id=company_id, artifact_type="report",
                title="Evidence", uri="s3://synthetic/evidence",
                metadata_json={"evidence": {"audit_events": ["audit_pinned"]}},
            ),
            ControlPlaneEventOutboxTable(
                event_id="event_pending", event_type="test.event", source_agent="test",
                payload={"audit_event_id": "audit_pending"}, schema_version="1.0",
                correlation_id="audit_pending", status="pending", attempts=0,
            ),
            ControlPlaneEventOutboxTable(
                event_id="event_published", event_type="test.event", source_agent="test",
                payload={"audit_event_id": "audit_published"}, schema_version="1.0",
                correlation_id="audit_published", status="published", attempts=1,
            ),
        ])
        await session.flush()
        command = RetentionCommand(company_id=company_id, dry_run=False, batch_size=10)
        receipt = await SqlAlchemyRetentionStore(session).apply(
            command, request_id="pin-request", now=now, cutoff=cutoff
        )
        await session.commit()

        assert receipt.eligible_audit_events == 1
        assert receipt.purged_published_outbox_events == 1
        assert await session.get(AuditEventTable, "audit_pending") is not None
        assert await session.get(AuditEventTable, "audit_pinned") is not None
        assert await session.get(AuditEventTable, "audit_published") is None
        assert await session.get(ControlPlaneEventOutboxTable, "event_pending") is not None
        assert await session.get(ControlPlaneEventOutboxTable, "event_published") is None
        assert await session.get(ArtifactTable, "artifact_pin") is not None


async def test_compact_tombstone_blocks_duplicate_audit_and_outbox_republication():
    async with _postgres_session() as session:
        company_id = "cmp_retention_dedupe"
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=90)
        await _seed_company(session, company_id)
        await _seed_company(session, "cmp_foreign")
        session.add(_audit(
            event_id="audit_compact", company_id=company_id,
            created_at=cutoff - timedelta(days=1), key="stable-idempotency-key",
            action="work_item.created",
        ))
        await session.flush()
        await SqlAlchemyRetentionStore(session).apply(
            RetentionCommand(company_id=company_id, dry_run=False),
            request_id="compact-request", now=now, cutoff=cutoff,
        )
        await session.commit()

        event = AuditEvent(
            company_id=company_id,
            action="work_item.created",
            target_type="work_item",
            target_id="work_item_x",
            actor_type="system",
            actor_id="new-actor",
            idempotency_key="stable-idempotency-key",
            detail={"domain_event": "work_item.created"},
        )
        returned = await SqlAlchemyControlPlaneAuditEventStore(session).append_audit_event(event)
        await session.commit()
        assert returned.audit_event_id == "audit_compact"
        assert returned.actor_id == "retention"
        assert await session.get(AuditEventTable, "audit_compact") is None
        assert await session.scalar(select(func.count()).select_from(AuditRetentionTombstoneTable)) == 1
        assert await session.scalar(select(func.count()).select_from(ControlPlaneEventOutboxTable)) == 0


async def test_concurrent_purge_and_duplicate_append_preserve_one_idempotent_result():
    async with _postgres_session() as session:
        company_id = "cmp_retention_race"
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=90)
        await _seed_company(session, company_id)
        session.add(_audit(
            event_id="audit_race", company_id=company_id,
            created_at=cutoff - timedelta(days=1), key="race-key",
            action="work_item.created",
        ))
        await session.commit()
        sessions = async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)
        barrier = asyncio.Barrier(2)

        async def purge():
            async with sessions() as concurrent_session:
                await barrier.wait()
                result = await SqlAlchemyRetentionStore(concurrent_session).apply(
                    RetentionCommand(company_id=company_id, dry_run=False),
                    request_id="race-request", now=now, cutoff=cutoff,
                )
                await concurrent_session.commit()
                return result

        async def append_duplicate():
            async with sessions() as concurrent_session:
                await barrier.wait()
                result = await SqlAlchemyControlPlaneAuditEventStore(
                    concurrent_session
                ).append_audit_event(AuditEvent(
                    company_id=company_id,
                    action="work_item.created",
                    target_type="work_item",
                    target_id="work_item_race",
                    actor_type="system",
                    actor_id="retry",
                    idempotency_key="race-key",
                    detail={"domain_event": "work_item.created"},
                ))
                await concurrent_session.commit()
                return result

        receipt, returned = await asyncio.wait_for(
            asyncio.gather(purge(), append_duplicate()), timeout=10
        )
        assert receipt.purged_audit_events == 1
        assert returned.audit_event_id == "audit_race"
        assert await session.scalar(select(func.count()).select_from(AuditEventTable)) == 0
        assert await session.scalar(
            select(func.count()).select_from(AuditRetentionTombstoneTable)
        ) == 1
        assert await session.scalar(
            select(func.count()).select_from(ControlPlaneEventOutboxTable)
        ) == 0


async def test_expired_knowledge_pointer_is_purged_with_permanent_tombstone_and_artifact_kept():
    async with _postgres_session() as session:
        company_id = "cmp_retention_knowledge"
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=90)
        await _seed_company(session, company_id)
        await _seed_company(session, "cmp_foreign")
        session.add(ArtifactTable(
            artifact_id="artifact_knowledge", company_id=company_id,
            artifact_type="report", title="Knowledge source", uri="s3://synthetic/source",
        ))
        await session.flush()
        session.add(KnowledgeTable(
            knowledge_id="knowledge_expired", company_id=company_id,
            source_artifact_id="artifact_knowledge", source_company_id=company_id,
            owner_actor_id="owner", reader_role_ids=[], version=3,
            retention_until=now - timedelta(seconds=1), created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=120),
        ))
        session.add(KnowledgeTable(
            knowledge_id="knowledge_foreign", company_id="cmp_foreign",
            source_artifact_id="artifact_knowledge", source_company_id=company_id,
            owner_actor_id="owner", reader_role_ids=[], version=1,
            retention_until=now - timedelta(seconds=1), created_at=now, updated_at=now,
        ))
        await session.flush()
        receipt = await SqlAlchemyRetentionStore(session).apply(
            RetentionCommand(company_id=company_id, dry_run=False),
            request_id="knowledge-request", now=now, cutoff=cutoff,
        )
        await session.commit()

        assert receipt.expired_knowledge == 1
        assert receipt.purged_knowledge == 1
        assert await session.get(KnowledgeTable, "knowledge_expired") is None
        assert await session.get(KnowledgeTable, "knowledge_foreign") is not None
        tombstone = await session.get(KnowledgeTombstoneTable, "knowledge_expired")
        assert tombstone is not None
        assert tombstone.actor_id == "retention"
        assert tombstone.version == 3
        assert await session.get(ArtifactTable, "artifact_knowledge") is not None


async def test_knowledge_create_waits_for_retention_and_cannot_resurrect_purged_id():
    async with _postgres_session() as session:
        company_id = "cmp_retention_knowledge_race"
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=90)
        await _seed_company(session, company_id)
        session.add(ArtifactTable(
            artifact_id="artifact_knowledge_race", company_id=company_id,
            artifact_type="report", title="Knowledge source", uri="s3://synthetic/source",
        ))
        await session.flush()
        session.add(KnowledgeTable(
            knowledge_id="knowledge_race", company_id=company_id,
            source_artifact_id="artifact_knowledge_race", source_company_id=company_id,
            owner_actor_id="owner", reader_role_ids=[], version=2,
            retention_until=now - timedelta(seconds=1), created_at=now - timedelta(days=120),
            updated_at=now - timedelta(days=120),
        ))
        await session.commit()

        command = RetentionCommand(company_id=company_id, dry_run=False)
        receipt = await SqlAlchemyRetentionStore(session).apply(
            command, request_id="knowledge-race-request", now=now, cutoff=cutoff
        )
        assert receipt.purged_knowledge == 1

        sessions = async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)
        create_started = asyncio.Event()

        async def create_same_id():
            async with sessions() as concurrent_session:
                create_started.set()
                record = KnowledgeRecord(
                    knowledge_id="knowledge_race",
                    company_id=company_id,
                    source_artifact_id="artifact_knowledge_race",
                    source_company_id=company_id,
                    owner_actor_id="owner",
                    version=1,
                )
                with pytest.raises(ValueError, match="knowledge_id_permanently_deleted"):
                    await SqlAlchemyKnowledgeStore(concurrent_session).create_knowledge(record)
                await concurrent_session.rollback()

        creator = asyncio.create_task(create_same_id())
        await asyncio.wait_for(create_started.wait(), timeout=2)
        await asyncio.sleep(0.1)
        assert not creator.done(), "knowledge create should wait on the retention company lock"

        await session.commit()
        await asyncio.wait_for(creator, timeout=5)
        assert await session.get(KnowledgeTable, "knowledge_race") is None
        assert await session.get(KnowledgeTombstoneTable, "knowledge_race") is not None
