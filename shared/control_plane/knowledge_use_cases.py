"""Company-scoped application operations for reference-only knowledge."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from .domain.knowledge import KnowledgeError, KnowledgeRecord, KnowledgeTombstone
from .knowledge_ports import KnowledgeStore
from .models import AuditEvent


class KnowledgeNotFoundError(Exception):
    """Knowledge is absent, expired, deleted, or outside the requested company."""


class KnowledgeConflictError(Exception):
    """The expected knowledge version no longer matches persisted state."""


class KnowledgeSourceArtifactError(Exception):
    """The source artifact is missing or belongs to a different company."""


class KnowledgeOwnerRequiredError(Exception):
    """Only the owner may delete a knowledge pointer."""


class KnowledgeRoleNotFoundError(Exception):
    """A granted reader role does not belong to the target company."""


class KnowledgeProvenanceImmutableError(Exception):
    """A published pointer cannot be retargeted to another artifact."""


class KnowledgeReadForbiddenError(Exception):
    """The actor is not the owner or an explicitly granted reader role."""


async def publish_knowledge(
    store: KnowledgeStore,
    *,
    company_id: str,
    source_artifact_id: str,
    actor_id: str,
    reader_role_ids: tuple[str, ...] = (),
    retention_until: datetime | None = None,
    knowledge_id: str | None = None,
    expected_version: int | None = None,
) -> KnowledgeRecord:
    """Create a knowledge pointer or publish its next access-policy version."""
    artifact = await store.get_artifact(source_artifact_id)
    if artifact is None or artifact.company_id != company_id:
        raise KnowledgeSourceArtifactError(source_artifact_id)
    if retention_until is not None and retention_until.tzinfo is None:
        raise ValueError("retention_until must include a timezone")
    if knowledge_id is None:
        if expected_version not in (None, 0):
            raise KnowledgeConflictError("new knowledge must start at version 1")
        if not await store.company_has_roles(company_id, reader_role_ids):
            raise KnowledgeRoleNotFoundError("reader_role_company_mismatch")
        created = await store.create_knowledge(
            KnowledgeRecord(
                knowledge_id=f"knw_{uuid4().hex}",
                company_id=company_id,
                source_artifact_id=source_artifact_id,
                source_company_id=artifact.company_id,
                owner_actor_id=actor_id,
                reader_role_ids=reader_role_ids,
                version=1,
                retention_until=retention_until,
            )
        )
        await _append_audit(
            store,
            company_id=company_id,
            actor_id=actor_id,
            action="knowledge.published",
            record=created,
        )
        return created

    if expected_version is None:
        raise KnowledgeConflictError("expected_version_required")
    current = await store.get_knowledge(knowledge_id, company_id=company_id)
    if current is None:
        raise KnowledgeNotFoundError(knowledge_id)
    if current.owner_actor_id != actor_id:
        raise KnowledgeOwnerRequiredError(knowledge_id)
    if (current.source_artifact_id, current.source_company_id) != (
        source_artifact_id,
        artifact.company_id,
    ):
        raise KnowledgeProvenanceImmutableError(knowledge_id)
    if not await store.company_has_roles(company_id, reader_role_ids):
        raise KnowledgeRoleNotFoundError("reader_role_company_mismatch")
    try:
        revised = current.revise(
            expected_version=expected_version,
            reader_role_ids=reader_role_ids,
            retention_until=retention_until,
        )
    except KnowledgeError as exc:
        if str(exc) == "knowledge_version_conflict":
            raise KnowledgeConflictError(knowledge_id) from exc
        raise KnowledgeNotFoundError(knowledge_id) from exc
    saved = await store.revise_knowledge(revised, expected_version=expected_version)
    if saved is None:
        raise KnowledgeConflictError(knowledge_id)
    await _append_audit(
        store, company_id=company_id, actor_id=actor_id, action="knowledge.revised", record=saved
    )
    return saved


async def read_knowledge(
    store: KnowledgeStore,
    *,
    knowledge_id: str,
    company_id: str,
    actor_id: str,
    actor_role_ids: frozenset[str],
    actor_scopes: frozenset[str] = frozenset(),
) -> KnowledgeRecord:
    record = await store.get_knowledge(knowledge_id, company_id=company_id)
    if record is None or not record.is_accessible():
        raise KnowledgeNotFoundError(knowledge_id)
    if (
        actor_id != record.owner_actor_id
        and not (set(record.reader_role_ids) & set(actor_role_ids))
        and "*" not in actor_scopes
    ):
        raise KnowledgeReadForbiddenError(knowledge_id)
    return record


async def delete_knowledge(
    store: KnowledgeStore,
    *,
    knowledge_id: str,
    company_id: str,
    actor_id: str,
) -> KnowledgeTombstone:
    record = await store.get_knowledge(knowledge_id, company_id=company_id)
    if record is None:
        raise KnowledgeNotFoundError(knowledge_id)
    try:
        deleted = record.tombstone(actor_id=actor_id)
    except KnowledgeError as exc:
        if str(exc) == "knowledge_owner_required":
            raise KnowledgeOwnerRequiredError(knowledge_id) from exc
        raise KnowledgeNotFoundError(knowledge_id) from exc
    assert deleted.deleted_at is not None
    tombstone = KnowledgeTombstone(
        knowledge_id=record.knowledge_id,
        company_id=company_id,
        actor_id=actor_id,
        version=record.version,
        deleted_at=deleted.deleted_at,
    )
    if not await store.delete_knowledge(deleted, tombstone):
        raise KnowledgeConflictError(knowledge_id)
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action="knowledge.deleted",
            target_type="knowledge",
            target_id=knowledge_id,
            actor_type="operator",
            actor_id=actor_id,
            detail={"version": tombstone.version, "source_artifact_id": record.source_artifact_id},
        )
    )
    return tombstone


async def _append_audit(
    store: KnowledgeStore, *, company_id: str, actor_id: str, action: str, record: KnowledgeRecord
) -> None:
    await store.append_audit_event(
        AuditEvent(
            company_id=company_id,
            action=action,
            target_type="knowledge",
            target_id=record.knowledge_id,
            actor_type="operator",
            actor_id=actor_id,
            detail={
                "version": record.version,
                "source_artifact_id": record.source_artifact_id,
                "reader_role_count": len(record.reader_role_ids),
            },
        )
    )
