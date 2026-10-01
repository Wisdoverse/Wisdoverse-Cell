"""Validated, reference-only company knowledge records."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _now() -> datetime:
    return datetime.now(UTC)


class KnowledgeError(ValueError):
    """Raised when a knowledge lifecycle transition is invalid."""


class KnowledgeRecord(BaseModel):
    """A scoped pointer to an artifact; knowledge content is never copied here."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    knowledge_id: str = Field(min_length=1, max_length=64)
    company_id: str = Field(min_length=1, max_length=48)
    source_artifact_id: str = Field(min_length=1, max_length=48)
    source_company_id: str = Field(min_length=1, max_length=48)
    owner_actor_id: str = Field(min_length=1, max_length=128)
    reader_role_ids: tuple[str, ...] = Field(default=(), max_length=100)
    version: int = Field(ge=1)
    retention_until: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    deleted_at: datetime | None = None
    deleted_by_actor_id: str | None = Field(default=None, max_length=128)

    @field_validator("reader_role_ids")
    @classmethod
    def _clean_roles(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        roles = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
        if len(roles) != len(values):
            raise ValueError("reader roles must be non-empty unique IDs")
        if any(len(role) > 64 for role in roles):
            raise ValueError("reader role ID is too long")
        return roles

    @model_validator(mode="after")
    def _deletion_fields_pair(self) -> "KnowledgeRecord":
        if (self.deleted_at is None) != (self.deleted_by_actor_id is None):
            raise ValueError("delete timestamp and actor must be supplied together")
        return self

    def is_accessible(self, *, now: datetime | None = None) -> bool:
        instant = now or _now()
        retention = self.retention_until
        if retention is not None and retention.tzinfo is None:
            retention = retention.replace(tzinfo=UTC)
        return self.deleted_at is None and (retention is None or retention > instant)

    def revise(
        self,
        *,
        expected_version: int,
        reader_role_ids: tuple[str, ...],
        retention_until: datetime | None,
        now: datetime | None = None,
    ) -> "KnowledgeRecord":
        if not self.is_accessible(now=now):
            raise KnowledgeError("knowledge_not_accessible")
        if expected_version != self.version:
            raise KnowledgeError("knowledge_version_conflict")
        return KnowledgeRecord.model_validate(
            {
                **self.model_dump(),
                "reader_role_ids": reader_role_ids,
                "retention_until": retention_until,
                "version": self.version + 1,
                "updated_at": now or _now(),
            }
        )

    def tombstone(self, *, actor_id: str, now: datetime | None = None) -> "KnowledgeRecord":
        if not self.is_accessible(now=now):
            raise KnowledgeError("knowledge_not_accessible")
        if actor_id != self.owner_actor_id:
            raise KnowledgeError("knowledge_owner_required")
        return KnowledgeRecord.model_validate(
            {**self.model_dump(), "deleted_at": now or _now(), "deleted_by_actor_id": actor_id}
        )


class KnowledgeTombstone(BaseModel):
    """Immutable audit evidence for a knowledge deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)
    knowledge_id: str = Field(min_length=1, max_length=64)
    company_id: str = Field(min_length=1, max_length=48)
    actor_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    deleted_at: datetime = Field(default_factory=_now)
