"""Unit tests for execution-link domain policy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shared.control_plane.domain.execution_links import (
    ExecutionLinkConsistencyPolicy,
    ExecutionLinkMismatchError,
    ExecutionLinks,
)
from shared.control_plane.domain.services import ControlPlaneDomainService
from shared.control_plane.models import AgentRun, AgentRunStatus, WorkItem


def test_execution_link_policy_implements_domain_service_contract() -> None:
    policy = ExecutionLinkConsistencyPolicy()

    assert isinstance(policy, ControlPlaneDomainService)
    assert policy.service_name == "ExecutionLinkConsistencyPolicy"


def test_agent_run_implied_links_are_resolved() -> None:
    links = ExecutionLinks.requested(run_id="run_1")
    resolved = links.with_agent_run(
        AgentRun(
            run_id="run_1",
            company_id="cmp_test",
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            work_item_id="work_1",
            goal_id="goal_1",
        )
    )

    assert resolved.as_goal_work_item_tuple() == ("goal_1", "work_1")


def test_work_item_implied_goal_is_resolved() -> None:
    links = ExecutionLinks.requested(work_item_id="work_1")
    resolved = links.with_work_item(
        WorkItem(
            work_item_id="work_1",
            company_id="cmp_test",
            title="Ship feature",
            goal_id="goal_1",
        )
    )

    assert resolved.goal_id == "goal_1"
    assert resolved.work_item_id == "work_1"


def test_agent_run_work_item_mismatch_raises_domain_error() -> None:
    links = ExecutionLinks.requested(run_id="run_1", work_item_id="work_requested")

    with pytest.raises(ExecutionLinkMismatchError) as exc:
        links.with_agent_run(
            AgentRun(
                run_id="run_1",
                company_id="cmp_test",
                agent_id="dev-agent",
                status=AgentRunStatus.RUNNING,
                work_item_id="work_run",
            )
        )

    assert exc.value.target == "work_item"


def test_goal_mismatch_raises_domain_error() -> None:
    links = ExecutionLinks.requested(goal_id="goal_requested")

    with pytest.raises(ExecutionLinkMismatchError) as exc:
        links.with_work_item(
            WorkItem(
                work_item_id="work_1",
                company_id="cmp_test",
                title="Ship feature",
                goal_id="goal_work_item",
            )
        )

    assert exc.value.target == "goal"


def test_execution_links_are_immutable_value_object() -> None:
    links = ExecutionLinks.requested(run_id="run_1")

    with pytest.raises(FrozenInstanceError):
        links.goal_id = "goal_1"  # type: ignore[misc]


def test_execution_link_policy_resolves_persistence_references() -> None:
    policy = ExecutionLinkConsistencyPolicy()
    links = policy.requested_links(run_id="run_1")
    links = policy.resolve_agent_run(
        links,
        AgentRun(
            run_id="run_1",
            company_id="cmp_test",
            agent_id="dev-agent",
            status=AgentRunStatus.RUNNING,
            work_item_id="work_1",
        ),
    )
    links = policy.resolve_work_item(
        links,
        WorkItem(
            work_item_id="work_1",
            company_id="cmp_test",
            title="Ship feature",
            goal_id="goal_1",
        ),
    )

    assert policy.persistence_refs(links) == ("goal_1", "work_1")
