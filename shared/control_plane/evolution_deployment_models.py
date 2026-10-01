"""Durable desired releases and receiver acknowledgements."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .tables import ControlPlaneBase


class EvolutionDeploymentTable(ControlPlaneBase):
    __tablename__ = "control_plane_evolution_deployments"
    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), index=True
    )
    proposal_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_evolution_proposals.proposal_id"), unique=True
    )
    evaluation_report_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_evolution_evaluations.evaluation_report_id")
    )
    state: Mapped[str] = mapped_column(String(32))
    desired_action: Mapped[str] = mapped_column(String(16))
    command: Mapped[dict[str, Any]] = mapped_column(JSON)
    acknowledgement: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
