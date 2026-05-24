"""Coordinator scratchpad consistency policy tests."""

from services.orchestration.coordinator.core.domain.scratchpad import (
    CoordinatorScratchpadConsistencyPolicy,
    CoordinatorScratchpadProjectionPlan,
)
from services.orchestration.coordinator.core.models import Decision


def test_scratchpad_projection_plan_materializes_decisions() -> None:
    decision = Decision(
        target_agent="dev-agent",
        action="dispatch_task",
        task_id="task_1",
        instruction="Implement",
    )

    plan = CoordinatorScratchpadProjectionPlan.from_decisions([decision])

    assert plan.requires_projection_update is True
    assert plan.decisions == (decision,)
    assert plan.decisions_for_projection() == [decision]


def test_scratchpad_projection_plan_skips_empty_updates() -> None:
    plan = CoordinatorScratchpadProjectionPlan.from_decisions([])

    assert plan.requires_projection_update is False
    assert plan.can_schedule_compaction(
        compaction_requested=True,
        decisions_persisted=False,
        projection_updated=False,
    ) is True


def test_scratchpad_policy_requires_persisted_projection_before_compaction() -> None:
    decision = Decision(
        target_agent="qa-agent",
        action="run_acceptance",
        task_id="task_2",
        instruction="Run QA",
    )
    policy = CoordinatorScratchpadConsistencyPolicy()
    plan = policy.plan_after_decision_synthesis([decision])

    assert policy.can_compact(
        plan,
        compaction_requested=True,
        decisions_persisted=False,
        projection_updated=False,
    ) is False
    assert policy.can_compact(
        plan,
        compaction_requested=True,
        decisions_persisted=True,
        projection_updated=False,
    ) is False
    assert policy.can_compact(
        plan,
        compaction_requested=True,
        decisions_persisted=True,
        projection_updated=True,
    ) is True
