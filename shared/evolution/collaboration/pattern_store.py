"""
PatternStore — async repository for collaboration patterns.

Uses SQLAlchemy async sessions to persist CollaborationPattern data
in the evolution_collaboration_patterns table.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.evolution.collaboration.models import CollaborationPattern, PatternStatus
from shared.evolution.db.tables import EvolutionCollaborationPatternTable


class PatternStore:
    """Async repository for collaboration pattern CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_pattern(
        self, pattern: CollaborationPattern
    ) -> EvolutionCollaborationPatternTable:
        """Persist a new collaboration pattern."""
        row = EvolutionCollaborationPatternTable(
            pattern_id=pattern.pattern_id,
            name=pattern.name,
            status=pattern.status.value,
            trigger_event=pattern.trigger_event,
            trigger_condition=pattern.trigger_condition,
            steps=[s.model_dump() for s in pattern.steps],
            shadow_results=pattern.shadow_results,
            production_results=pattern.production_results,
            human_approval=pattern.human_approval,
            approved_by=pattern.approved_by,
            approved_at=pattern.approved_at,
            created_at=pattern.created_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get_pattern(
        self, pattern_id: str
    ) -> EvolutionCollaborationPatternTable | None:
        """Retrieve a single pattern by its pattern_id."""
        stmt = select(EvolutionCollaborationPatternTable).where(
            EvolutionCollaborationPatternTable.pattern_id == pattern_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_matching(
        self, event_type: str, status: str
    ) -> list[EvolutionCollaborationPatternTable]:
        """Find patterns matching a trigger event type and status."""
        stmt = select(EvolutionCollaborationPatternTable).where(
            EvolutionCollaborationPatternTable.trigger_event == event_type,
            EvolutionCollaborationPatternTable.status == status,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self, pattern_id: str, new_status: PatternStatus
    ) -> None:
        """Update the status of a pattern."""
        stmt = (
            update(EvolutionCollaborationPatternTable)
            .where(EvolutionCollaborationPatternTable.pattern_id == pattern_id)
            .values(status=new_status.value, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def add_shadow_result(
        self, pattern_id: str, result: dict[str, Any]
    ) -> None:
        """Append a shadow run result to the pattern's shadow_results JSON array."""
        row = await self.get_pattern(pattern_id)
        if row is None:
            msg = f"Pattern {pattern_id} not found"
            raise ValueError(msg)
        existing: list[dict[str, Any]] = list(row.shadow_results or [])
        existing.append(result)
        stmt = (
            update(EvolutionCollaborationPatternTable)
            .where(EvolutionCollaborationPatternTable.pattern_id == pattern_id)
            .values(shadow_results=existing, updated_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def approve_pattern(self, pattern_id: str, approved_by: str) -> None:
        """Approve a pattern: set status=active, human_approval=True, and record approver."""
        now = datetime.now(UTC)
        stmt = (
            update(EvolutionCollaborationPatternTable)
            .where(EvolutionCollaborationPatternTable.pattern_id == pattern_id)
            .values(
                status=PatternStatus.ACTIVE.value,
                human_approval=True,
                approved_by=approved_by,
                approved_at=now,
                updated_at=now,
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_all_patterns(
        self, status: str | None = None
    ) -> list[EvolutionCollaborationPatternTable]:
        """List all patterns, optionally filtered by status."""
        stmt = select(EvolutionCollaborationPatternTable)
        if status is not None:
            stmt = stmt.where(
                EvolutionCollaborationPatternTable.status == status
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
