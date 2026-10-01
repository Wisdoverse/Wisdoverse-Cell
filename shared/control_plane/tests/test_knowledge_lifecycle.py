"""Tests for scoped, reference-only company knowledge."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shared.control_plane.domain.knowledge import KnowledgeRecord
from shared.control_plane.knowledge_models import KnowledgeTable, KnowledgeTombstoneTable
from shared.control_plane.knowledge_store import SqlAlchemyKnowledgeStore
from shared.control_plane.knowledge_use_cases import (
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeOwnerRequiredError,
    KnowledgeProvenanceImmutableError,
    KnowledgeReadForbiddenError,
    KnowledgeSourceArtifactError,
    delete_knowledge,
    publish_knowledge,
    read_knowledge,
)
from shared.control_plane.models import Artifact, AuditEvent
from shared.control_plane.tables import (
    AgentRoleTable,
    ArtifactTable,
    CompanyContextTable,
    control_plane_metadata,
)


class MemoryKnowledgeStore:
    def __init__(self):
        self.artifacts: dict[str, Artifact] = {}
        self.records: dict[str, KnowledgeRecord] = {}
        self.tombstones = []
        self.roles = {"role_reader", "role_a", "role_b", "role_auditor"}
        self.audit_events: list[AuditEvent] = []

    async def get_artifact(self, artifact_id):
        return self.artifacts.get(artifact_id)

    async def company_has_roles(self, company_id, role_ids):
        return set(role_ids) <= self.roles

    async def append_audit_event(self, event):
        self.audit_events.append(event)
        return event

    async def get_knowledge(self, knowledge_id, *, company_id):
        row = self.records.get(knowledge_id)
        return row if row is not None and row.company_id == company_id else None

    async def create_knowledge(self, record):
        self.records[record.knowledge_id] = record
        return record

    async def revise_knowledge(self, record, *, expected_version):
        current = self.records.get(record.knowledge_id)
        if current is None or current.version != expected_version or current.deleted_at is not None:
            return None
        self.records[record.knowledge_id] = record
        return record

    async def delete_knowledge(self, record, tombstone):
        current = self.records.get(record.knowledge_id)
        if current is None or current.version != record.version or current.deleted_at is not None:
            return False
        self.records[record.knowledge_id] = record
        self.tombstones.append(tombstone)
        return True


def _store() -> MemoryKnowledgeStore:
    store = MemoryKnowledgeStore()
    store.artifacts["art_1"] = Artifact(
        artifact_id="art_1", company_id="cmp_1", title="Evidence", uri="s3://bucket/object"
    )
    return store


@pytest.mark.asyncio
async def test_publish_requires_same_company_artifact_and_stores_only_reference() -> None:
    store = _store()
    with pytest.raises(KnowledgeSourceArtifactError):
        await publish_knowledge(
            store, company_id="cmp_other", source_artifact_id="art_1", actor_id="owner"
        )

    with pytest.raises(Exception, match="reader_role_company_mismatch"):
        await publish_knowledge(
            store,
            company_id="cmp_1",
            source_artifact_id="art_1",
            actor_id="owner",
            reader_role_ids=("role_other_company",),
        )

    record = await publish_knowledge(
        store,
        company_id="cmp_1",
        source_artifact_id="art_1",
        actor_id="owner",
        reader_role_ids=("role_reader",),
    )
    assert record.source_artifact_id == "art_1"
    assert record.source_company_id == record.company_id == "cmp_1"
    assert record.reader_role_ids == ("role_reader",)
    assert "content" not in record.model_dump()
    assert record.version == 1
    assert store.audit_events[0].action == "knowledge.published"


@pytest.mark.asyncio
async def test_revise_uses_optimistic_version_and_keeps_provenance_immutable() -> None:
    store = _store()
    created = await publish_knowledge(
        store, company_id="cmp_1", source_artifact_id="art_1", actor_id="owner"
    )
    revised = await publish_knowledge(
        store,
        company_id="cmp_1",
        source_artifact_id="art_1",
        actor_id="owner",
        knowledge_id=created.knowledge_id,
        expected_version=1,
        reader_role_ids=("role_a",),
    )
    assert revised.version == 2
    with pytest.raises(KnowledgeOwnerRequiredError):
        await publish_knowledge(
            store,
            company_id="cmp_1",
            source_artifact_id="art_1",
            actor_id="other_writer",
            knowledge_id=created.knowledge_id,
            expected_version=2,
            reader_role_ids=("role_b",),
        )
    with pytest.raises(KnowledgeConflictError):
        await publish_knowledge(
            store,
            company_id="cmp_1",
            source_artifact_id="art_1",
            actor_id="owner",
            knowledge_id=created.knowledge_id,
            expected_version=1,
            reader_role_ids=("role_b",),
        )
    store.artifacts["art_2"] = Artifact(
        artifact_id="art_2", company_id="cmp_1", title="Other", uri="urn:other"
    )
    with pytest.raises(KnowledgeProvenanceImmutableError):
        await publish_knowledge(
            store,
            company_id="cmp_1",
            source_artifact_id="art_2",
            actor_id="owner",
            knowledge_id=created.knowledge_id,
            expected_version=2,
        )


@pytest.mark.asyncio
async def test_read_requires_owner_or_explicit_role_and_company_scope() -> None:
    store = _store()
    record = await publish_knowledge(
        store,
        company_id="cmp_1",
        source_artifact_id="art_1",
        actor_id="owner",
        reader_role_ids=("role_reader",),
    )
    with pytest.raises(KnowledgeReadForbiddenError):
        await read_knowledge(
            store,
            knowledge_id=record.knowledge_id,
            company_id="cmp_1",
            actor_id="stranger",
            actor_role_ids=frozenset(),
        )
    assert (
        await read_knowledge(
            store,
            knowledge_id=record.knowledge_id,
            company_id="cmp_1",
            actor_id="reader",
            actor_role_ids=frozenset({"role_reader"}),
        )
        == record
    )
    with pytest.raises(KnowledgeNotFoundError):
        await read_knowledge(
            store,
            knowledge_id=record.knowledge_id,
            company_id="cmp_other",
            actor_id="owner",
            actor_role_ids=frozenset(),
        )


@pytest.mark.asyncio
async def test_expired_and_deleted_records_are_inaccessible_and_delete_is_owner_only() -> None:
    store = _store()
    expired = await publish_knowledge(
        store,
        company_id="cmp_1",
        source_artifact_id="art_1",
        actor_id="owner",
        retention_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    with pytest.raises(KnowledgeNotFoundError):
        await read_knowledge(
            store,
            knowledge_id=expired.knowledge_id,
            company_id="cmp_1",
            actor_id="owner",
            actor_role_ids=frozenset(),
        )

    live = await publish_knowledge(
        store, company_id="cmp_1", source_artifact_id="art_1", actor_id="owner"
    )
    with pytest.raises(KnowledgeOwnerRequiredError):
        await delete_knowledge(
            store, knowledge_id=live.knowledge_id, company_id="cmp_1", actor_id="someone_else"
        )
    tombstone = await delete_knowledge(
        store, knowledge_id=live.knowledge_id, company_id="cmp_1", actor_id="owner"
    )
    assert tombstone.actor_id == "owner"
    assert len(store.tombstones) == 1
    assert store.audit_events[-1].action == "knowledge.deleted"
    with pytest.raises(KnowledgeNotFoundError):
        await read_knowledge(
            store,
            knowledge_id=live.knowledge_id,
            company_id="cmp_1",
            actor_id="owner",
            actor_role_ids=frozenset(),
        )


def test_record_requires_paired_delete_audit_fields_and_timezone_retention_is_checked_in_use_case() -> (
    None
):
    with pytest.raises(ValueError):
        KnowledgeRecord(
            knowledge_id="knw_1",
            company_id="cmp_1",
            source_artifact_id="art_1",
            source_company_id="cmp_1",
            owner_actor_id="owner",
            version=1,
            deleted_at=datetime.now(UTC),
        )
    with pytest.raises(ValueError, match="timezone"):
        import asyncio

        asyncio.run(
            publish_knowledge(
                _store(),
                company_id="cmp_1",
                source_artifact_id="art_1",
                actor_id="owner",
                retention_until=datetime(2030, 1, 1),
            )
        )


@pytest.mark.asyncio
async def test_sqlalchemy_store_persists_versions_and_append_only_tombstone() -> None:
    pytest.importorskip("aiosqlite")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(CompanyContextTable(company_id="cmp_1", name="Cell", mission=""))
            session.add(
                AgentRoleTable(
                    role_id="role_reader",
                    company_id="cmp_1",
                    agent_id="reader-agent",
                    display_name="Reader",
                    role="reader",
                )
            )
            session.add(
                ArtifactTable(
                    artifact_id="art_1",
                    company_id="cmp_1",
                    artifact_type="report",
                    title="Evidence",
                    uri="s3://bucket/object",
                    metadata_json={},
                )
            )
            await session.flush()
            store = SqlAlchemyKnowledgeStore(session)
            created = await publish_knowledge(
                store,
                company_id="cmp_1",
                source_artifact_id="art_1",
                actor_id="owner",
                reader_role_ids=("role_reader",),
                retention_until=datetime.now(UTC) + timedelta(days=5),
            )
            assert await store.get_knowledge(created.knowledge_id, company_id="cmp_1") == created
            revised = await publish_knowledge(
                store,
                company_id="cmp_1",
                source_artifact_id="art_1",
                actor_id="owner",
                knowledge_id=created.knowledge_id,
                expected_version=1,
                reader_role_ids=("role_reader",),
                retention_until=datetime.now(UTC) + timedelta(days=10),
            )
            assert revised.version == 2
            assert (
                revised.retention_until is not None and revised.retention_until.tzinfo is not None
            )
            tombstone = await delete_knowledge(
                store, knowledge_id=revised.knowledge_id, company_id="cmp_1", actor_id="owner"
            )
            assert tombstone.version == 2
            await session.commit()
            persisted = await session.get(KnowledgeTable, created.knowledge_id)
            assert persisted is not None and persisted.deleted_at is not None
            assert await session.get(KnowledgeTombstoneTable, created.knowledge_id) is not None
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(control_plane_metadata.drop_all)
        await engine.dispose()
