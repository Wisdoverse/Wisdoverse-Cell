"""Canonical Control Plane aggregate inventory.

The Control Plane publishes Pydantic records at the API/persistence
boundary, while aggregate behavior lives in this domain package. This
catalog keeps the aggregate-root inventory domain-owned so docs and
architecture guards do not drift from the actual aggregate modules.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ControlPlaneAggregateDefinition:
    """Module and test ownership for one Control Plane aggregate root."""

    aggregate_name: str
    record_name: str
    module_path: str
    test_path: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("aggregate_name", self.aggregate_name),
            ("record_name", self.record_name),
            ("module_path", self.module_path),
            ("test_path", self.test_path),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        for field_name, value in (
            ("module_path", self.module_path),
            ("test_path", self.test_path),
        ):
            if value.startswith("/") or "\\" in value:
                raise ValueError(f"{field_name} must be a repo-relative POSIX path")


CONTROL_PLANE_AGGREGATES: tuple[ControlPlaneAggregateDefinition, ...] = (
    ControlPlaneAggregateDefinition(
        aggregate_name="CompanyContext",
        record_name="CompanyContext",
        module_path="shared/control_plane/domain/company_context.py",
        test_path="shared/control_plane/tests/test_company_context_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="Goal",
        record_name="Goal",
        module_path="shared/control_plane/domain/goal.py",
        test_path="shared/control_plane/tests/test_goal_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="AgentRole",
        record_name="AgentRole",
        module_path="shared/control_plane/domain/agent_role.py",
        test_path="shared/control_plane/tests/test_agent_role_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="WorkItem",
        record_name="WorkItem",
        module_path="shared/control_plane/domain/work_item.py",
        test_path="shared/control_plane/tests/test_work_item_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="AgentRun",
        record_name="AgentRun",
        module_path="shared/control_plane/domain/agent_run.py",
        test_path="shared/control_plane/tests/test_agent_run_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="Decision",
        record_name="Decision",
        module_path="shared/control_plane/domain/decision.py",
        test_path="shared/control_plane/tests/test_decision_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="ApprovalRequest",
        record_name="ApprovalRequest",
        module_path="shared/control_plane/domain/approval_request.py",
        test_path="shared/control_plane/tests/test_approval_request_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="BudgetPolicy",
        record_name="BudgetPolicy",
        module_path="shared/control_plane/domain/budget_policy.py",
        test_path="shared/control_plane/tests/test_budget_policy_domain.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="BudgetUsage",
        record_name="BudgetUsage",
        module_path="shared/control_plane/domain/budget_usage.py",
        test_path="shared/control_plane/tests/test_budget_usage_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="Artifact",
        record_name="Artifact",
        module_path="shared/control_plane/domain/artifact.py",
        test_path="shared/control_plane/tests/test_artifact_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="AuditEvent",
        record_name="AuditEvent",
        module_path="shared/control_plane/domain/audit_event.py",
        test_path="shared/control_plane/tests/test_audit_event_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="EvolutionProposal",
        record_name="EvolutionProposal",
        module_path="shared/control_plane/domain/evolution_proposal.py",
        test_path="shared/control_plane/tests/test_evolution_proposal_aggregate.py",
    ),
    ControlPlaneAggregateDefinition(
        aggregate_name="AgentPromptConfig",
        record_name="AgentPromptConfig",
        module_path="shared/control_plane/domain/agent_prompt_config.py",
        test_path="shared/control_plane/tests/test_agent_prompt_config_aggregate.py",
    ),
)


def aggregate_record_names() -> tuple[str, ...]:
    """Return the published record names with aggregate wrappers."""
    return tuple(definition.record_name for definition in CONTROL_PLANE_AGGREGATES)


def aggregate_module_paths() -> tuple[str, ...]:
    """Return repo-relative module paths for Control Plane aggregates."""
    return tuple(definition.module_path for definition in CONTROL_PLANE_AGGREGATES)


def aggregate_test_paths() -> tuple[str, ...]:
    """Return repo-relative unit-test paths for Control Plane aggregates."""
    return tuple(definition.test_path for definition in CONTROL_PLANE_AGGREGATES)


__all__ = [
    "CONTROL_PLANE_AGGREGATES",
    "ControlPlaneAggregateDefinition",
    "aggregate_module_paths",
    "aggregate_record_names",
    "aggregate_test_paths",
]
