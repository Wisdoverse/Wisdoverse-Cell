"""Domain-record mappers for control-plane application use cases."""
from __future__ import annotations

from .models import Artifact as ArtifactModel
from .models import CompanyContext, Decision, Goal, WorkItem
from .tables import (
    ArtifactTable,
    CompanyContextTable,
    DecisionTable,
    GoalTable,
    WorkItemTable,
)


def company_record(row: CompanyContextTable) -> CompanyContext:
    """Convert a company ORM row into its domain model."""
    return CompanyContext(
        company_id=row.company_id,
        name=row.name,
        mission=row.mission,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def goal_record(row: GoalTable) -> Goal:
    """Convert a goal ORM row into its domain model."""
    return Goal(
        goal_id=row.goal_id,
        company_id=row.company_id,
        title=row.title,
        description=row.description,
        status=row.status,
        parent_goal_id=row.parent_goal_id,
        owner_agent_id=row.owner_agent_id,
        owner_user_id=row.owner_user_id,
        success_metric=row.success_metric,
        target_value=row.target_value,
        current_value=row.current_value,
        due_at=row.due_at,
        tags=list(row.tags or []),
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def work_item_record(row: WorkItemTable) -> WorkItem:
    """Convert a work-item ORM row into its domain model."""
    return WorkItem(
        work_item_id=row.work_item_id,
        company_id=row.company_id,
        title=row.title,
        description=row.description,
        status=row.status,
        priority=row.priority,
        goal_id=row.goal_id,
        owner_agent_id=row.owner_agent_id,
        owner_user_id=row.owner_user_id,
        source=row.source,
        external_ref=row.external_ref,
        dependencies=list(row.dependencies or []),
        approval_required=row.approval_required,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def decision_record(row: DecisionTable) -> Decision:
    """Convert a decision ORM row into its domain model."""
    return Decision(
        decision_id=row.decision_id,
        company_id=row.company_id,
        title=row.title,
        rationale=row.rationale,
        status=row.status,
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        goal_id=row.goal_id,
        options=list(row.options or []),
        selected_option=row.selected_option,
        decided_by=row.decided_by,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def artifact_record(row: ArtifactTable) -> ArtifactModel:
    """Convert an artifact ORM row into its domain model."""
    return ArtifactModel(
        artifact_id=row.artifact_id,
        company_id=row.company_id,
        artifact_type=row.artifact_type,
        title=row.title,
        uri=row.uri,
        content_hash=row.content_hash,
        run_id=row.run_id,
        work_item_id=row.work_item_id,
        goal_id=row.goal_id,
        created_by_agent_id=row.created_by_agent_id,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
    )
