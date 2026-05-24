"""Postgres-backed CoordinatorStateStore adapter (DDD-018, ADR-0008).

Production-grade adapter satisfying the in-memory state store's
contract per ADR-0008. The schema lives in three tables added by
``migrations/versions/20260523_coordinator_durable_state.py``:
``coordinator_agent_state``, ``coordinator_workflow_state``,
``coordinator_pending_decision``.

Wired in `service/agent.py` when ``COORDINATOR_DURABLE_STATE=true``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.ids import IDPrefix, generate_id

from ..core.domain.state_records import (
    CoordinatorAgentStateRecord,
    CoordinatorDecisionRecord,
)
from ..core.domain.workflow_state import CoordinatorWorkflowState as WorkflowStateAggregate
from ..core.models import Decision
from .models import WorkflowState
from .state_tables import (
    CoordinatorAgentState,
    CoordinatorPendingDecision,
    CoordinatorWorkflowState,
)


class PostgresCoordinatorStateStore:
    """Session-scoped Postgres adapter for coordinator state.

    Matches the in-memory adapter shape so consumers swap with no
    interface change.
    """

    PENDING_DECISIONS_LIMIT: int = 100

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_agent_states(self) -> dict[str, CoordinatorAgentStateRecord]:
        result = await self._session.execute(select(CoordinatorAgentState))
        rows = result.scalars().all()
        return {str(row.agent_id): _row_to_agent_state(row) for row in rows}

    async def update_agent_state(
        self,
        agent_id: str,
        *,
        status: str = "idle",
        current_task: str | None = None,
        error: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(CoordinatorAgentState)
            .values(
                agent_id=agent_id,
                status=status,
                current_task=current_task,
                last_output_at=now,
                error=error,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[CoordinatorAgentState.agent_id],
                set_={
                    "status": status,
                    "current_task": current_task,
                    "last_output_at": now,
                    "error": error,
                    "updated_at": now,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_pending_decisions(self) -> list[CoordinatorDecisionRecord]:
        result = await self._session.execute(
            select(CoordinatorPendingDecision)
            .where(CoordinatorPendingDecision.resolved_at.is_(None))
            .order_by(CoordinatorPendingDecision.created_at.asc())
        )
        rows = result.scalars().all()
        return [_row_to_decision_record(row) for row in rows]

    async def persist(self, decisions: list[Decision]) -> None:
        """Persist coordinator decisions to Postgres + update agent state.

        Append/trim semantics match the in-memory adapter
        (`PENDING_DECISIONS_LIMIT` retained newest); older rows are
        deleted to bound table growth.
        """
        now = datetime.now(UTC)
        for decision in decisions:
            row = CoordinatorPendingDecision(
                decision_id=generate_id(IDPrefix.DECISION),
                workflow_id=getattr(decision, "workflow_id", None),
                reasoning=getattr(decision, "reasoning", "") or "",
                action=decision.action,
                target_agent=decision.target_agent,
                task_id=getattr(decision, "task_id", None),
                outcome=None,
                created_at=now,
                resolved_at=None,
                retry_count=0,
            )
            self._session.add(row)
            await self.update_agent_state(
                decision.target_agent,
                status="working",
                current_task=getattr(decision, "task_id", None),
            )
        await self._session.flush()
        await self._trim_pending_decisions()

    async def _trim_pending_decisions(self) -> None:
        """Keep only the newest PENDING_DECISIONS_LIMIT pending rows."""
        result = await self._session.execute(
            select(CoordinatorPendingDecision.decision_id)
            .where(CoordinatorPendingDecision.resolved_at.is_(None))
            .order_by(CoordinatorPendingDecision.created_at.desc())
            .offset(self.PENDING_DECISIONS_LIMIT)
        )
        stale_ids = [row[0] for row in result.all()]
        if not stale_ids:
            return
        await self._session.execute(
            delete(CoordinatorPendingDecision).where(
                CoordinatorPendingDecision.decision_id.in_(stale_ids)
            )
        )
        await self._session.flush()

    async def get_workflow_states(self) -> dict[str, WorkflowState]:
        result = await self._session.execute(select(CoordinatorWorkflowState))
        return {row.workflow_id: _row_to_workflow_state(row) for row in result.scalars().all()}

    async def upsert_workflow_state(self, state: WorkflowState) -> None:
        workflow = WorkflowStateAggregate.from_record(state)
        record = workflow.to_record_kwargs()
        now = datetime.now(UTC)
        stmt = (
            pg_insert(CoordinatorWorkflowState)
            .values(
                workflow_id=record["workflow_id"],
                type=record["type"],
                status=record["status"],
                current_phase=record["current_phase"],
                agents_involved=record["agents_involved"],
                context=record["context"],
                created_at=record["created_at"] or now,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[CoordinatorWorkflowState.workflow_id],
                set_={
                    "type": record["type"],
                    "status": record["status"],
                    "current_phase": record["current_phase"],
                    "agents_involved": record["agents_involved"],
                    "context": record["context"],
                    "updated_at": now,
                },
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()


def _row_to_agent_state(row: CoordinatorAgentState) -> CoordinatorAgentStateRecord:
    return CoordinatorAgentStateRecord.create(
        agent_id=row.agent_id,
        status=row.status,
        current_task=row.current_task,
        last_output_at=row.last_output_at,
        error=row.error,
    )


def _row_to_decision_record(row: CoordinatorPendingDecision) -> CoordinatorDecisionRecord:
    return CoordinatorDecisionRecord.create(
        decision_id=row.decision_id,
        workflow_id=row.workflow_id,
        reasoning=row.reasoning,
        action=row.action,
        target_agent=row.target_agent,
        created_at=row.created_at,
        outcome=row.outcome,
        task_id=row.task_id,
    )


def _row_to_workflow_state(row: CoordinatorWorkflowState) -> WorkflowState:
    return WorkflowState(
        workflow_id=row.workflow_id,
        type=row.type,
        status=row.status,  # type: ignore[arg-type]
        current_phase=row.current_phase,
        agents_involved=list(row.agents_involved or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
        context=dict(row.context or {}),
    )
