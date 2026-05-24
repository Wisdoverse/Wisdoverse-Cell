"""Domain policy for Coordinator scratchpad consistency."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CoordinatorScratchpadProjectionPlan:
    """Derived scratchpad projection to apply after decision persistence.

    The decision store is the consistency source. The scratchpad is a
    rebuildable reasoning projection, so it must not record decisions before
    the decision-state mutation succeeds.
    """

    decisions: tuple[Any, ...]

    @classmethod
    def from_decisions(
        cls,
        decisions: Iterable[Any],
    ) -> "CoordinatorScratchpadProjectionPlan":
        return cls(decisions=tuple(decisions))

    @property
    def requires_projection_update(self) -> bool:
        return bool(self.decisions)

    def decisions_for_projection(self) -> list[Any]:
        return list(self.decisions)

    def can_schedule_compaction(
        self,
        *,
        compaction_requested: bool,
        decisions_persisted: bool,
        projection_updated: bool,
    ) -> bool:
        if not compaction_requested:
            return False
        if not self.requires_projection_update:
            return True
        return decisions_persisted and projection_updated


class CoordinatorScratchpadConsistencyPolicy:
    """Domain service for scratchpad projection ordering."""

    def plan_after_decision_synthesis(
        self,
        decisions: Iterable[Any],
    ) -> CoordinatorScratchpadProjectionPlan:
        return CoordinatorScratchpadProjectionPlan.from_decisions(decisions)

    def can_compact(
        self,
        plan: CoordinatorScratchpadProjectionPlan,
        *,
        compaction_requested: bool,
        decisions_persisted: bool,
        projection_updated: bool,
    ) -> bool:
        return plan.can_schedule_compaction(
            compaction_requested=compaction_requested,
            decisions_persisted=decisions_persisted,
            projection_updated=projection_updated,
        )


__all__ = [
    "CoordinatorScratchpadConsistencyPolicy",
    "CoordinatorScratchpadProjectionPlan",
]
