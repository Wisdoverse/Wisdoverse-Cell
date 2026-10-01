"""Control Plane-owned compact dedupe and retention operation receipts."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .tables import ControlPlaneBase


class AuditRetentionTombstoneTable(ControlPlaneBase):
    __tablename__ = "control_plane_audit_retention_tombstones"
    audit_event_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    idempotency_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        Index("uq_control_audit_retention_key", "company_id", "idempotency_hash", unique=True),
    )


class RetentionRunTable(ControlPlaneBase):
    __tablename__ = "control_plane_retention_runs"
    company_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    command_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
