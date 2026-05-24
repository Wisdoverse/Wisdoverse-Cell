"""Execution-link consistency policy for Control Plane records."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..models import AgentRun, WorkItem
from .services import ControlPlaneDomainService


class ExecutionLinkMismatchError(ValueError):
    """Raised when run, work-item, and goal references disagree."""

    def __init__(self, target: str) -> None:
        super().__init__(target)
        self.target = target


@dataclass(frozen=True, slots=True)
class ExecutionLinks:
    """Resolved execution links shared by artifacts and decisions."""

    run_id: str | None = None
    work_item_id: str | None = None
    goal_id: str | None = None

    @classmethod
    def requested(
        cls,
        *,
        run_id: str | None = None,
        work_item_id: str | None = None,
        goal_id: str | None = None,
    ) -> ExecutionLinks:
        return cls(run_id=run_id, work_item_id=work_item_id, goal_id=goal_id)

    def with_agent_run(self, run: AgentRun) -> ExecutionLinks:
        """Resolve links implied by an AgentRun record."""
        resolved = self
        if run.work_item_id:
            if resolved.work_item_id and resolved.work_item_id != run.work_item_id:
                raise ExecutionLinkMismatchError("work_item")
            resolved = replace(resolved, work_item_id=run.work_item_id)
        if run.goal_id:
            if resolved.goal_id and resolved.goal_id != run.goal_id:
                raise ExecutionLinkMismatchError("goal")
            resolved = replace(resolved, goal_id=run.goal_id)
        return resolved

    def with_work_item(self, work_item: WorkItem) -> ExecutionLinks:
        """Resolve links implied by a WorkItem record."""
        if work_item.goal_id:
            if self.goal_id and self.goal_id != work_item.goal_id:
                raise ExecutionLinkMismatchError("goal")
            return replace(self, goal_id=work_item.goal_id)
        return self

    def as_goal_work_item_tuple(self) -> tuple[str | None, str | None]:
        """Return persistence-ready `(goal_id, work_item_id)` values."""
        return self.goal_id, self.work_item_id


class ExecutionLinkConsistencyPolicy(ControlPlaneDomainService):
    """Domain service for execution-link resolution across ledger records."""

    __slots__ = ()

    def requested_links(
        self,
        *,
        run_id: str | None = None,
        work_item_id: str | None = None,
        goal_id: str | None = None,
    ) -> ExecutionLinks:
        """Create the initial execution-link value object from a command."""
        return ExecutionLinks.requested(
            run_id=run_id,
            work_item_id=work_item_id,
            goal_id=goal_id,
        )

    def resolve_agent_run(
        self,
        links: ExecutionLinks,
        run: AgentRun,
    ) -> ExecutionLinks:
        """Resolve links implied by an AgentRun record."""
        return links.with_agent_run(run)

    def resolve_work_item(
        self,
        links: ExecutionLinks,
        work_item: WorkItem,
    ) -> ExecutionLinks:
        """Resolve links implied by a WorkItem record."""
        return links.with_work_item(work_item)

    def persistence_refs(
        self,
        links: ExecutionLinks,
    ) -> tuple[str | None, str | None]:
        """Return persistence-ready `(goal_id, work_item_id)` references."""
        return links.as_goal_work_item_tuple()


__all__ = [
    "ExecutionLinkConsistencyPolicy",
    "ExecutionLinkMismatchError",
    "ExecutionLinks",
]
