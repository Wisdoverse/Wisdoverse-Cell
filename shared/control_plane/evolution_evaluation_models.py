"""Immutable persisted report model and SQLAlchemy mapping for evaluations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, event
from sqlalchemy.orm import Mapped, mapped_column

from shared.core.ids import generate_id

from .tables import ControlPlaneBase


def _now() -> datetime:
    return datetime.now(UTC)


class EvolutionEvaluationReport(BaseModel):
    """Read contract for one fixed-case proposal evaluation comparison."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_report_id: str
    company_id: str
    proposal_id: str
    baseline_skill_version_id: str
    candidate_skill_version_id: str
    dataset_revision: str
    baseline_batch_hash: str
    candidate_batch_hash: str
    baseline_batch: dict[str, Any]
    candidate_batch: dict[str, Any]
    policy: dict[str, Any]
    comparison_report: dict[str, Any]
    evaluator_version: str
    created_at: datetime = Field(default_factory=_now)


class EvolutionEvaluationReportTable(ControlPlaneBase):
    """Append-only snapshot linking a proposal to immutable evaluation evidence."""

    __tablename__ = "control_plane_evolution_evaluations"

    evaluation_report_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_companies.company_id"), nullable=False
    )
    proposal_id: Mapped[str] = mapped_column(
        String(48), ForeignKey("control_plane_evolution_proposals.proposal_id"), nullable=False
    )
    baseline_skill_version_id: Mapped[str] = mapped_column(String(200), nullable=False)
    candidate_skill_version_id: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_revision: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_batch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_batch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_batch: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidate_batch: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    comparison_report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    __table_args__ = (
        Index(
            "ix_control_evaluations_company_proposal_created",
            "company_id",
            "proposal_id",
            "created_at",
        ),
    )


@event.listens_for(EvolutionEvaluationReportTable, "before_update")
def _reject_evaluation_report_update(mapper: Any, connection: Any, target: Any) -> None:
    """Keep evaluation evidence append-only through SQLAlchemy ORM writes."""

    raise ValueError("evolution evaluation reports are immutable")


@event.listens_for(EvolutionEvaluationReportTable, "before_delete")
def _reject_evaluation_report_delete(mapper: Any, connection: Any, target: Any) -> None:
    """Keep evaluation evidence append-only through SQLAlchemy ORM writes."""

    raise ValueError("evolution evaluation reports cannot be deleted")


def evaluation_report_record(row: EvolutionEvaluationReportTable) -> EvolutionEvaluationReport:
    """Map a persisted row to the immutable report contract."""

    return EvolutionEvaluationReport(
        evaluation_report_id=row.evaluation_report_id,
        company_id=row.company_id,
        proposal_id=row.proposal_id,
        baseline_skill_version_id=row.baseline_skill_version_id,
        candidate_skill_version_id=row.candidate_skill_version_id,
        dataset_revision=row.dataset_revision,
        baseline_batch_hash=row.baseline_batch_hash,
        candidate_batch_hash=row.candidate_batch_hash,
        baseline_batch=dict(row.baseline_batch),
        candidate_batch=dict(row.candidate_batch),
        policy=dict(row.policy),
        comparison_report=dict(row.comparison_report),
        evaluator_version=row.evaluator_version,
        created_at=row.created_at,
    )


def new_evaluation_report_id() -> str:
    """Generate a stable-prefix ID for one persisted report."""

    return generate_id("evr")


__all__ = [
    "EvolutionEvaluationReport",
    "EvolutionEvaluationReportTable",
    "evaluation_report_record",
    "new_evaluation_report_id",
]
