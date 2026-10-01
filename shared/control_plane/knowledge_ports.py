"""Ports for the company knowledge lifecycle."""

from __future__ import annotations

from typing import Protocol

from .domain.knowledge import KnowledgeRecord, KnowledgeTombstone
from .models import Artifact, AuditEvent


class KnowledgeStore(Protocol):
    async def get_artifact(self, artifact_id: str) -> Artifact | None: ...
    async def company_has_roles(self, company_id: str, role_ids: tuple[str, ...]) -> bool: ...
    async def get_knowledge(
        self, knowledge_id: str, *, company_id: str
    ) -> KnowledgeRecord | None: ...
    async def create_knowledge(self, record: KnowledgeRecord) -> KnowledgeRecord: ...
    async def revise_knowledge(
        self, record: KnowledgeRecord, *, expected_version: int
    ) -> KnowledgeRecord | None: ...
    async def delete_knowledge(
        self, record: KnowledgeRecord, tombstone: KnowledgeTombstone
    ) -> bool: ...
    async def append_audit_event(self, event: AuditEvent) -> AuditEvent: ...


class KnowledgeEmbeddingPort(Protocol):
    """Optional future embedding boundary; no vector implementation is implied."""

    async def index_reference(
        self, *, company_id: str, knowledge_id: str, artifact_uri: str
    ) -> None: ...
    async def remove_reference(self, *, company_id: str, knowledge_id: str) -> None: ...
