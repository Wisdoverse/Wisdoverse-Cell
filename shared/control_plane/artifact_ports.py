"""Ports for control-plane artifact persistence."""
from __future__ import annotations

from typing import Any, Protocol

from .models import Artifact, AuditEvent, CompanyContext


class ControlPlaneArtifactStore(Protocol):
    """Persistence operations required by artifact use cases."""

    async def create_company(self, company: CompanyContext) -> Any:
        """Create a control-plane company context."""

    async def get_company(self, company_id: str) -> Any | None:
        """Return a company context if it exists."""

    async def get_agent_run(self, run_id: str) -> Any | None:
        """Return one agent run for linkage validation."""

    async def get_goal(self, goal_id: str) -> Any | None:
        """Return one goal for linkage validation."""

    async def get_work_item(self, work_item_id: str) -> Any | None:
        """Return one work item for linkage validation."""

    async def create_artifact(self, artifact: Artifact) -> Any:
        """Create an artifact."""

    async def get_artifact(self, artifact_id: str) -> Any | None:
        """Return one artifact."""

    async def list_artifacts(
        self,
        *,
        company_id: str,
        artifact_type: str | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = 50,
    ) -> list[Any]:
        """Return artifacts for one company."""

    async def append_audit_event(self, event: AuditEvent) -> Any:
        """Append a control-plane audit event."""
