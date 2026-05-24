"""Control plane domain layer.

Holds entities, value objects, aggregates, invariants, and lifecycle
policies for the control plane ledger. Must not import from infrastructure
(e.g. SQLAlchemy table modules, repository.py session helpers) outside of
the ports it consumes.

See docs/architecture/architecture-principles.md §1.
"""

from .agent_prompt_config import (
    AGENT_PROMPT_MAX_LENGTH,
    AgentPromptConfig,
    AgentPromptConfigUpdated,
    InvalidAgentPromptConfigError,
    clean_system_prompt,
    clean_updated_by,
)
from .agent_role import (
    RUNNABLE_STATUSES,
    AgentRole,
    AgentRoleStatus,
    AgentRoleStatusChanged,
    InvalidAgentRoleStatusError,
    InvalidAgentRoleTransitionError,
)
from .agent_wakeup_adapter import AgentWakeupAdapterConfig
from .aggregate_catalog import (
    CONTROL_PLANE_AGGREGATES,
    ControlPlaneAggregateDefinition,
    aggregate_module_paths,
    aggregate_record_names,
    aggregate_test_paths,
)
from .approval_request import (
    ApprovalRequest,
    ApprovalStatusChanged,
    InvalidApprovalTransitionError,
    approval_status_is_approved,
)
from .approval_resolution import ApprovalResolutionEffect, ApprovalResolutionPolicy
from .artifact import (
    Artifact,
    ArtifactCreated,
    InvalidArtifactError,
    artifact_type_value,
)
from .audit_event import (
    AuditEvent,
    InvalidAuditEventError,
    clean_audit_actor_id,
    clean_audit_actor_type,
    clean_audit_detail,
    clean_audit_text,
    clean_optional_audit_text,
)
from .budget_amount import BudgetAmount, BudgetWarningThreshold
from .budget_policy import (
    BUDGET_POLICY_STATUS_ACTIVE,
    BUDGET_POLICY_STATUS_ARCHIVED,
    BUDGET_POLICY_STATUS_PAUSED,
    BUDGET_POLICY_STATUSES,
    BudgetPolicy,
    BudgetPolicyConflictError,
    BudgetPolicyConflictPolicy,
    BudgetPolicyCreated,
    BudgetPolicyStatus,
    BudgetPolicyUpdated,
    InvalidBudgetPolicyError,
    InvalidBudgetPolicyStatusError,
    InvalidBudgetPolicyTransitionError,
    budget_policy_status,
    is_active_budget_policy_status,
    is_budget_policy_status,
    normalize_budget_policy_status,
)
from .budget_usage import (
    BudgetUsage,
    BudgetUsageRecorded,
    InvalidBudgetUsageError,
    budget_token_count,
    clean_budget_usage_model,
)
from .company_context import (
    CompanyContext,
    CompanyContextCreated,
    CompanyContextUpdated,
    InvalidCompanyContextError,
    clean_company_mission,
    clean_company_name,
)
from .decision import (
    Decision,
    DecisionStatusChanged,
    InvalidDecisionTransitionError,
)
from .events import ControlPlaneDomainEvent
from .execution_links import (
    ExecutionLinkConsistencyPolicy,
    ExecutionLinkMismatchError,
    ExecutionLinks,
)
from .goal import (
    Goal,
    GoalStatusChanged,
    InvalidGoalTransitionError,
    goal_current_value_for_transition,
)
from .metadata import ControlPlaneMetadata, InvalidControlPlaneMetadataError
from .services import ControlPlaneDomainService
from .state_machine import (
    ControlPlaneStateMachine,
    InvalidControlPlaneStateMachineError,
)
from .work_item import (
    WORK_ITEM_CLOSE_STATUSES,
    InvalidWorkItemTransitionError,
    WorkItem,
    WorkItemStatusChanged,
    is_work_item_close_status,
    work_item_status_from_agent_run_status,
)

__all__ = [
    "BUDGET_POLICY_STATUS_ACTIVE",
    "BUDGET_POLICY_STATUS_ARCHIVED",
    "BUDGET_POLICY_STATUS_PAUSED",
    "BUDGET_POLICY_STATUSES",
    "BudgetPolicy",
    "BudgetPolicyConflictError",
    "BudgetPolicyConflictPolicy",
    "BudgetPolicyCreated",
    "BudgetPolicyStatus",
    "BudgetPolicyUpdated",
    "InvalidBudgetPolicyError",
    "InvalidBudgetPolicyStatusError",
    "InvalidBudgetPolicyTransitionError",
    "budget_policy_status",
    "is_active_budget_policy_status",
    "is_budget_policy_status",
    "normalize_budget_policy_status",
    "BudgetUsage",
    "BudgetUsageRecorded",
    "InvalidBudgetUsageError",
    "budget_token_count",
    "clean_budget_usage_model",
    "CompanyContext",
    "CompanyContextCreated",
    "CompanyContextUpdated",
    "InvalidCompanyContextError",
    "clean_company_mission",
    "clean_company_name",
    "ApprovalRequest",
    "ApprovalResolutionEffect",
    "ApprovalResolutionPolicy",
    "AgentRole",
    "AgentRoleStatus",
    "AgentRoleStatusChanged",
    "InvalidAgentRoleStatusError",
    "InvalidAgentRoleTransitionError",
    "RUNNABLE_STATUSES",
    "AGENT_PROMPT_MAX_LENGTH",
    "AgentPromptConfig",
    "AgentPromptConfigUpdated",
    "InvalidAgentPromptConfigError",
    "clean_system_prompt",
    "clean_updated_by",
    "CONTROL_PLANE_AGGREGATES",
    "ControlPlaneAggregateDefinition",
    "aggregate_module_paths",
    "aggregate_record_names",
    "aggregate_test_paths",
    "AgentWakeupAdapterConfig",
    "ApprovalStatusChanged",
    "InvalidApprovalTransitionError",
    "approval_status_is_approved",
    "Artifact",
    "ArtifactCreated",
    "InvalidArtifactError",
    "artifact_type_value",
    "AuditEvent",
    "InvalidAuditEventError",
    "clean_audit_actor_id",
    "clean_audit_actor_type",
    "clean_audit_detail",
    "clean_audit_text",
    "clean_optional_audit_text",
    "BudgetAmount",
    "BudgetWarningThreshold",
    "Decision",
    "DecisionStatusChanged",
    "InvalidDecisionTransitionError",
    "ExecutionLinkMismatchError",
    "ExecutionLinkConsistencyPolicy",
    "ExecutionLinks",
    "ControlPlaneDomainEvent",
    "Goal",
    "GoalStatusChanged",
    "InvalidGoalTransitionError",
    "goal_current_value_for_transition",
    "ControlPlaneMetadata",
    "InvalidControlPlaneMetadataError",
    "ControlPlaneDomainService",
    "ControlPlaneStateMachine",
    "InvalidControlPlaneStateMachineError",
    "WORK_ITEM_CLOSE_STATUSES",
    "InvalidWorkItemTransitionError",
    "WorkItem",
    "WorkItemStatusChanged",
    "is_work_item_close_status",
    "work_item_status_from_agent_run_status",
]
