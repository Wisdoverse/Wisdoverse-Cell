"""SQLAlchemy mappings for company-scoped knowledge pointers."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .tables import ControlPlaneBase


def _now() -> datetime:
    return datetime.now(UTC)


class KnowledgeTable(ControlPlaneBase):
    __tablename__ = "control_plane_knowledge"

    knowledge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False
    )
    source_artifact_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_artifacts.artifact_id"), nullable=False
    )
    source_company_id: Mapped[str] = mapped_column(String(48), nullable=False)
    owner_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reader_role_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_control_knowledge_company_access", "company_id", "deleted_at", "retention_until"),
    )


class KnowledgeTombstoneTable(ControlPlaneBase):
    __tablename__ = "control_plane_knowledge_tombstones"

    knowledge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
