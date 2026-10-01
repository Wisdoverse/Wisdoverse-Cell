"""SQLAlchemy adapter for immutable proposal evaluation reports."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.identifiers import EvolutionProposalId

from .audit_event_store import SqlAlchemyControlPlaneAuditEventStore
from .evolution_evaluation_models import (
    EvolutionEvaluationReport,
    EvolutionEvaluationReportTable,
    evaluation_report_record,
)
from .evolution_evaluation_ports import ControlPlaneEvolutionEvaluationStore
from .evolution_proposal_store import SqlAlchemyControlPlaneEvolutionProposalStore
from .models import AuditEvent, EvolutionProposal


class SqlAlchemyControlPlaneEvolutionEvaluationStore(ControlPlaneEvolutionEvaluationStore):
    """Session-scoped append-only evaluation report adapter."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._proposals = SqlAlchemyControlPlaneEvolutionProposalStore(session)
        self._audits = SqlAlchemyControlPlaneAuditEventStore(session)

    async def get_evolution_proposal(self, proposal_id: str) -> EvolutionProposal | None:
        return await self._proposals.get_evolution_proposal(EvolutionProposalId(proposal_id))

    async def create_evaluation_report(
        self, report: EvolutionEvaluationReport
    ) -> EvolutionEvaluationReport:
        row = EvolutionEvaluationReportTable(**report.model_dump())
        self._session.add(row)
        await self._session.flush()
        return evaluation_report_record(row)

    async def list_evaluation_reports(
        self, *, company_id: str, proposal_id: str
    ) -> list[EvolutionEvaluationReport]:
        result = await self._session.execute(
            select(EvolutionEvaluationReportTable)
            .where(
                EvolutionEvaluationReportTable.company_id == company_id,
                EvolutionEvaluationReportTable.proposal_id == proposal_id,
            )
            .order_by(EvolutionEvaluationReportTable.created_at.desc())
        )
        return [evaluation_report_record(row) for row in result.scalars().all()]

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return await self._audits.append_audit_event(event)
