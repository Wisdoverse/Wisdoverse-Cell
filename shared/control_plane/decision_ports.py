"""Ports for control-plane decision persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import AgentRunId, CompanyId, DecisionId, GoalId, WorkItemId

from .models import AgentRun, AuditEvent, CompanyContext, Decision, Goal, WorkItem


class ControlPlaneDecisionStore(Protocol):
    """Persistence operations required by decision use cases.

    Identifier parameters use the typed `NewType` wrappers from
    `shared.core.identifiers` (DDD-007 adoption).
    """

    async def create_company(self, company: CompanyContext) -> CompanyContext:
        """Create a control-plane company context."""

    async def get_company(self, company_id: CompanyId) -> CompanyContext | None:
        """Return a company context if it exists."""

    async def get_agent_run(self, run_id: AgentRunId) -> AgentRun | None:
        """Return one agent run for linkage validation."""

    async def get_goal(self, goal_id: GoalId) -> Goal | None:
        """Return one goal for linkage validation."""

    async def get_work_item(self, work_item_id: WorkItemId) -> WorkItem | None:
        """Return one work item for linkage validation."""

    async def create_decision(self, decision: Decision) -> Decision:
        """Create a decision."""

    async def get_decision(self, decision_id: DecisionId) -> Decision | None:
        """Return one decision by typed identifier."""

    async def list_decisions(
        self,
        *,
        company_id: CompanyId,
        status: str | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = 50,
    ) -> list[Decision]:
        """Return decisions for one company."""

    async def update_decision_status(
        self,
        decision_id: DecisionId,
        *,
        status: str,
        selected_option: str | None = None,
        decided_by: str | None = None,
    ) -> Decision | None:
        """Update one decision status by typed identifier."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
