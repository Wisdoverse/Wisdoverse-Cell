"""Ports for control-plane artifact persistence."""
from __future__ import annotations

from typing import Protocol

from shared.core.identifiers import AgentRunId, ArtifactId, CompanyId, GoalId, WorkItemId

from .models import AgentRun, Artifact, AuditEvent, CompanyContext, Goal, WorkItem


class ControlPlaneArtifactStore(Protocol):
    """Persistence operations required by artifact use cases.

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

    async def create_artifact(self, artifact: Artifact) -> Artifact:
        """Create an artifact."""

    async def get_artifact(self, artifact_id: ArtifactId) -> Artifact | None:
        """Return one artifact by typed identifier."""

    async def list_artifacts(
        self,
        *,
        company_id: CompanyId,
        artifact_type: str | None = None,
        run_id: str | None = None,
        run_ids: list[str] | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Artifact]:
        """Return artifacts for one company."""

    async def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Append a control-plane audit event."""
