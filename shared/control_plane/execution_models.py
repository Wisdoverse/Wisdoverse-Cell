"""Durable dispatch intents and cost reservations owned by the control plane."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .tables import ControlPlaneBase


class ExecutionLeaseTable(ControlPlaneBase):
    __tablename__ = "control_plane_execution_leases"
    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), index=True
    )
    resource_id: Mapped[str] = mapped_column(String(128), index=True)
    intent_hash: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str] = mapped_column(String(48), unique=True)
    owner_id: Mapped[str] = mapped_column(String(48))
    state: Mapped[str] = mapped_column(String(32), index=True)
    control_action: Mapped[str] = mapped_column(String(16), default="resume")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "state IN ('running','recovery_required','succeeded','failed')",
            name="ck_execution_state",
        ),
        CheckConstraint(
            "control_action IN ('pause','resume','terminate')", name="ck_execution_control"
        ),
        Index("ix_execution_resource_state", "company_id", "resource_id", "state"),
    )


class ExecutionReservationTable(ControlPlaneBase):
    __tablename__ = "control_plane_execution_reservations"
    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("control_plane_execution_leases.execution_id"), primary_key=True
    )
    budget_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_budget_policies.budget_id"), primary_key=True
    )
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    state: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("amount_usd >= 0", name="ck_execution_reservation_amount"),
        CheckConstraint("state IN ('reserved','settled')", name="ck_execution_reservation_state"),
        UniqueConstraint("execution_id", "budget_id", name="uq_execution_budget"),
    )
