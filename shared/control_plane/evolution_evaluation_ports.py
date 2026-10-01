"""Ports for immutable proposal evaluation report persistence."""

from __future__ import annotations

from typing import Protocol

from shared.control_plane.models import AuditEvent, EvolutionProposal

from .evolution_evaluation_models import EvolutionEvaluationReport


class ControlPlaneEvolutionEvaluationStore(Protocol):
    """Persistence operations for proposal-linked evaluation reports."""

    async def get_evolution_proposal(self, proposal_id: str) -> EvolutionProposal | None:
        """Return the proposal associated with the evaluation request."""

    async def create_evaluation_report(
        self, report: EvolutionEvaluationReport
    ) -> EvolutionEvaluationReport:
        """Append a report; existing reports cannot be updated."""

    async def list_evaluation_reports(
        self, *, company_id: str, proposal_id: str
    ) -> list[EvolutionEvaluationReport]:
        """Return reports for one proposal in one company."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append the proposal/report linkage to the company audit trail."""
