"""Application use cases for control-plane artifacts."""
from __future__ import annotations

from typing import Any

from shared.schemas.event import EventTypes

from .artifact_ports import ControlPlaneArtifactStore
from .models import Artifact, ArtifactType, AuditEvent, CompanyContext


class ArtifactGoalNotFoundError(Exception):
    """Raised when the linked goal is missing or belongs to another company."""


class ArtifactLinkMismatchError(Exception):
    """Raised when linked run, work item, and goal references disagree."""


class ArtifactNotFoundError(Exception):
    """Raised when an artifact cannot be found in the target company."""


class ArtifactRunNotFoundError(Exception):
    """Raised when the linked run is missing or belongs to another company."""


class ArtifactWorkItemNotFoundError(Exception):
    """Raised when the linked work item is missing or belongs to another company."""


async def list_artifacts(
    store: ControlPlaneArtifactStore,
    *,
    company_id: str,
    artifact_type: str | None = None,
    run_id: str | None = None,
    goal_id: str | None = None,
    work_item_id: str | None = None,
    created_by_agent_id: str | None = None,
    limit: int = 50,
) -> list[Any]:
    """List artifacts for one company."""
    return await store.list_artifacts(
        company_id=company_id,
        artifact_type=artifact_type,
        run_id=run_id,
        goal_id=goal_id,
        work_item_id=work_item_id,
        created_by_agent_id=created_by_agent_id,
        limit=limit,
    )


async def get_artifact(
    store: ControlPlaneArtifactStore,
    *,
    company_id: str,
    artifact_id: str,
) -> Any:
    """Return one artifact in a company or raise not found."""
    row = await store.get_artifact(artifact_id)
    if row is None or row.company_id != company_id:
        raise ArtifactNotFoundError(artifact_id)
    return row


async def create_artifact_with_audit(
    store: ControlPlaneArtifactStore,
    artifact: Artifact,
    *,
    created_by: str,
) -> Any:
    """Create an artifact, validate execution links, and record its audit event."""
    await _ensure_company(store, artifact.company_id)
    goal_id, work_item_id = await _validate_execution_links(
        store,
        company_id=artifact.company_id,
        run_id=artifact.run_id,
        work_item_id=artifact.work_item_id,
        goal_id=artifact.goal_id,
    )

    row = await store.create_artifact(
        artifact.model_copy(
            update={
                "goal_id": goal_id,
                "work_item_id": work_item_id,
            }
        )
    )
    await store.append_audit_event(
        AuditEvent(
            company_id=artifact.company_id,
            action=EventTypes.ARTIFACT_CREATED,
            target_type="artifact",
            target_id=row.artifact_id,
            actor_type="user",
            actor_id=created_by,
            run_id=row.run_id,
            work_item_id=row.work_item_id,
            detail={
                "artifact_id": row.artifact_id,
                "artifact_type": row.artifact_type,
                "goal_id": row.goal_id,
                "work_item_id": row.work_item_id,
                "run_id": row.run_id,
                "created_by_agent_id": row.created_by_agent_id,
            },
        )
    )
    return row


def enum_value(value: ArtifactType | str | None) -> str | None:
    """Return a persistence-ready enum value."""
    if value is None:
        return None
    if isinstance(value, ArtifactType):
        return value.value
    return value


async def _ensure_company(
    store: ControlPlaneArtifactStore,
    company_id: str,
) -> None:
    if await store.get_company(company_id) is not None:
        return
    await store.create_company(
        CompanyContext(
            company_id=company_id,
            name="Wisdoverse Cell",
            mission="AI-native company operations",
        )
    )


async def _validate_execution_links(
    store: ControlPlaneArtifactStore,
    *,
    company_id: str,
    run_id: str | None = None,
    work_item_id: str | None = None,
    goal_id: str | None = None,
) -> tuple[str | None, str | None]:
    resolved_goal_id = goal_id
    resolved_work_item_id = work_item_id
    if run_id:
        run = await store.get_agent_run(run_id)
        if run is None or run.company_id != company_id:
            raise ArtifactRunNotFoundError(run_id)
        if run.work_item_id:
            if resolved_work_item_id and resolved_work_item_id != run.work_item_id:
                raise ArtifactLinkMismatchError("work_item")
            resolved_work_item_id = run.work_item_id
        if run.goal_id:
            if resolved_goal_id and resolved_goal_id != run.goal_id:
                raise ArtifactLinkMismatchError("goal")
            resolved_goal_id = run.goal_id
    if resolved_work_item_id:
        work_item = await store.get_work_item(resolved_work_item_id)
        if work_item is None or work_item.company_id != company_id:
            raise ArtifactWorkItemNotFoundError(resolved_work_item_id)
        if work_item.goal_id:
            if resolved_goal_id and resolved_goal_id != work_item.goal_id:
                raise ArtifactLinkMismatchError("goal")
            resolved_goal_id = work_item.goal_id
    if resolved_goal_id:
        goal = await store.get_goal(resolved_goal_id)
        if goal is None or goal.company_id != company_id:
            raise ArtifactGoalNotFoundError(resolved_goal_id)
    return resolved_goal_id, resolved_work_item_id
