"""Immutable business outcome review records."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .tables import ControlPlaneBase


class OutcomeAcceptanceTable(ControlPlaneBase):
    __tablename__ = "control_plane_outcome_acceptances"
    acceptance_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), index=True
    )
    work_item_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_work_items.work_item_id"), index=True
    )
    artifact_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_artifacts.artifact_id")
    )
    run_id: Mapped[str] = mapped_column(String(48), ForeignKey("control_plane_agent_runs.run_id"))
    artifact_hash: Mapped[str] = mapped_column(String(128))
    verdict: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
