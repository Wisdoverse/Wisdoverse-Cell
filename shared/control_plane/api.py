"""FastAPI router for the shared control-plane ledger."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import settings
from shared.schemas.event import EventTypes

from .adapter_registry import DEFAULT_ADAPTER_REGISTRY
from .agent_runner import AgentWakeupError, ControlPlaneAgentRunner
from .approval_gate import ApprovalGate, ApprovalRequiredError
from .database import control_plane_db_manager
from .models import (
    AgentInteractionMode,
    AgentKind,
    AgentRole,
    Artifact,
    ArtifactType,
    AuditEvent,
    CompanyContext,
    Decision,
    DecisionStatus,
    Goal,
    GoalStatus,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
)
from .repository import ControlPlaneRepository
from .scheduler import ControlPlaneHeartbeatScheduler

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ApprovalActionRequest(BaseModel):
    resolved_by: str = Field(default="api", min_length=1, max_length=128)


class GoalCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=10_000)
    status: GoalStatus = GoalStatus.DRAFT
    parent_goal_id: str | None = Field(default=None, max_length=48)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    success_metric: str = Field(default="", max_length=2_000)
    target_value: float | None = None
    current_value: float | None = None
    due_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "success_metric", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("parent_goal_id", "owner_agent_id", "owner_user_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def _clean_tags(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class GoalStatusUpdateRequest(BaseModel):
    status: GoalStatus
    current_value: float | None = None
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class WorkItemCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    status: WorkItemStatus = WorkItemStatus.QUEUED
    priority: WorkItemPriority = WorkItemPriority.MEDIUM
    goal_id: str | None = Field(default=None, max_length=48)
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    source: str = Field(default="manual", min_length=1, max_length=64)
    external_ref: str | None = Field(default=None, max_length=256)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    approval_required: bool = False
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "description", "source", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "goal_id",
        "owner_agent_id",
        "owner_user_id",
        "external_ref",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @field_validator("dependencies", mode="before")
    @classmethod
    def _clean_dependencies(cls, value: Any) -> list[str]:
        return _clean_string_list(value)


class WorkItemStatusUpdateRequest(BaseModel):
    status: WorkItemStatus
    owner_agent_id: str | None = Field(default=None, max_length=64)
    owner_user_id: str | None = Field(default=None, max_length=64)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class DecisionCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=256)
    rationale: str = Field(min_length=1, max_length=20_000)
    status: DecisionStatus = DecisionStatus.PROPOSED
    run_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)
    goal_id: str | None = Field(default=None, max_length=48)
    options: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    selected_option: str | None = Field(default=None, max_length=128)
    decided_by: str | None = Field(default=None, max_length=128)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "rationale", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "run_id",
        "work_item_id",
        "goal_id",
        "selected_option",
        "decided_by",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class DecisionStatusUpdateRequest(BaseModel):
    status: DecisionStatus
    selected_option: str | None = Field(default=None, max_length=128)
    decided_by: str | None = Field(default=None, max_length=128)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class ArtifactCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    artifact_type: ArtifactType = ArtifactType.OTHER
    title: str = Field(min_length=1, max_length=256)
    uri: str = Field(min_length=1, max_length=4_000)
    content_hash: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)
    goal_id: str | None = Field(default=None, max_length=48)
    created_by_agent_id: str | None = Field(default=None, max_length=64)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "uri", "created_by", mode="before")
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator(
        "content_hash",
        "run_id",
        "work_item_id",
        "goal_id",
        "created_by_agent_id",
        mode="before",
    )
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AgentDefinitionCreateRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    agent_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    display_name: str = Field(min_length=1, max_length=128)
    agent_kind: AgentKind = AgentKind.ORGANIZATION_ROLE
    interaction_mode: AgentInteractionMode = AgentInteractionMode.ROUTED
    role: str = Field(default="worker", min_length=1, max_length=64)
    title: str = Field(default="", max_length=128)
    domain: str = Field(default="operations", max_length=64)
    reports_to_agent_id: str | None = Field(default=None, max_length=64)
    adapter_type: str = Field(default="builtin", min_length=1, max_length=64)
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    context_sources: list[str] = Field(default_factory=list, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=50)
    responsibilities: list[str] = Field(default_factory=list, max_length=50)
    permissions: list[str] = Field(default_factory=list, max_length=50)
    budget_policy_id: str | None = Field(default=None, max_length=48)
    escalation_policy: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", min_length=1, max_length=32)
    created_by: str = Field(default="api", min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "capabilities",
        "context_sources",
        "responsibilities",
        "permissions",
        mode="before",
    )
    @classmethod
    def _clean_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("must be a list")
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator(
        "display_name",
        "role",
        "title",
        "domain",
        "adapter_type",
        "created_by",
        mode="before",
    )
    @classmethod
    def _clean_string(cls, value: Any) -> str:
        return str(value or "").strip()

    @model_validator(mode="after")
    def _validate_agent_contract(self) -> "AgentDefinitionCreateRequest":
        if (
            self.agent_kind
            not in {AgentKind.ORGANIZATION_ROLE, AgentKind.INTEGRATION_GATEWAY}
            and self.interaction_mode == AgentInteractionMode.DIRECT
        ):
            raise ValueError(
                "only organization_role or integration_gateway agents may use direct interaction"
            )
        if self.agent_kind == AgentKind.ORGANIZATION_ROLE and not self.context_sources:
            self.context_sources = ["control_plane"]
        return self

    @field_validator("reports_to_agent_id", mode="before")
    @classmethod
    def _clean_optional_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


class AgentStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=32)
    actor_id: str = Field(default="api", min_length=1, max_length=128)


class AgentWakeupRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    input: dict[str, Any] = Field(default_factory=dict)
    actor_id: str = Field(default="api", min_length=1, max_length=128)
    trace_id: str | None = Field(default=None, max_length=96)
    goal_id: str | None = Field(default=None, max_length=48)
    work_item_id: str | None = Field(default=None, max_length=48)


class HeartbeatRunRequest(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=48)
    limit: int = Field(default=500, ge=1, le=500)


def _clean_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _timeline_sort_key(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _row_to_dict(row: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for attr_ref in row.__mapper__.column_attrs:
        attr = attr_ref.key
        key = "metadata" if attr == "metadata_json" else attr
        data[key] = _serialize(getattr(row, attr))
    return data


def create_control_plane_router(
    *,
    session_provider: SessionProvider | None = None,
) -> APIRouter:
    provider = session_provider or control_plane_db_manager.session
    router = APIRouter(prefix="/api/v1/control-plane", tags=["control-plane"])

    async def get_session():
        async with provider() as session:
            yield session

    def resolve_company(company_id: str | None) -> str:
        return company_id or settings.control_plane_company_id

    async def ensure_company(
        repo: ControlPlaneRepository,
        company_id: str,
    ) -> None:
        if await repo.get_company(company_id) is not None:
            return
        await repo.create_company(
            CompanyContext(
                company_id=company_id,
                name="Wisdoverse Cell",
                mission="AI-native company operations",
            )
        )

    async def validate_execution_links(
        repo: ControlPlaneRepository,
        *,
        company_id: str,
        run_id: str | None = None,
        work_item_id: str | None = None,
        goal_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        resolved_goal_id = goal_id
        resolved_work_item_id = work_item_id
        if run_id:
            run = await repo.get_agent_run(run_id)
            if run is None or run.company_id != company_id:
                raise HTTPException(status_code=400, detail="run_not_found")
            if run.work_item_id:
                if resolved_work_item_id and resolved_work_item_id != run.work_item_id:
                    raise HTTPException(status_code=400, detail="link_mismatch")
                resolved_work_item_id = run.work_item_id
            if run.goal_id:
                if resolved_goal_id and resolved_goal_id != run.goal_id:
                    raise HTTPException(status_code=400, detail="link_mismatch")
                resolved_goal_id = run.goal_id
        if resolved_work_item_id:
            work_item = await repo.get_work_item(resolved_work_item_id)
            if work_item is None or work_item.company_id != company_id:
                raise HTTPException(status_code=400, detail="work_item_not_found")
            if work_item.goal_id:
                if resolved_goal_id and resolved_goal_id != work_item.goal_id:
                    raise HTTPException(status_code=400, detail="link_mismatch")
                resolved_goal_id = work_item.goal_id
        if resolved_goal_id:
            goal = await repo.get_goal(resolved_goal_id)
            if goal is None or goal.company_id != company_id:
                raise HTTPException(status_code=400, detail="goal_not_found")
        return resolved_goal_id, resolved_work_item_id

    @router.get("/goals")
    async def list_goals(
        company_id: str | None = None,
        status: GoalStatus | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_goals(
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )
        return {"goals": [_row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/goals",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_goal(
        body: GoalCreateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        await ensure_company(repo, company_id)
        if body.parent_goal_id:
            parent = await repo.get_goal(body.parent_goal_id)
            if parent is None or parent.company_id != company_id:
                raise HTTPException(status_code=400, detail="parent_goal_not_found")

        row = await repo.create_goal(
            Goal(
                company_id=company_id,
                title=body.title,
                description=body.description,
                status=body.status,
                parent_goal_id=body.parent_goal_id,
                owner_agent_id=body.owner_agent_id,
                owner_user_id=body.owner_user_id,
                success_metric=body.success_metric,
                target_value=body.target_value,
                current_value=body.current_value,
                due_at=body.due_at,
                tags=body.tags,
                metadata=body.metadata,
            )
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.GOAL_CREATED,
                target_type="goal",
                target_id=row.goal_id,
                actor_type="user",
                actor_id=body.created_by,
                detail={
                    "goal_id": row.goal_id,
                    "status": row.status,
                    "parent_goal_id": row.parent_goal_id,
                    "owner_agent_id": row.owner_agent_id,
                    "owner_user_id": row.owner_user_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/goals/{goal_id}")
    async def get_goal(
        goal_id: str,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        row = await ControlPlaneRepository(session).get_goal(goal_id)
        if row is None or row.company_id != resolve_company(company_id):
            raise HTTPException(status_code=404, detail="goal_not_found")
        return _row_to_dict(row)

    @router.patch("/goals/{goal_id}/status")
    async def update_goal_status(
        goal_id: str,
        body: GoalStatusUpdateRequest,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        resolved_company_id = resolve_company(company_id)
        existing = await repo.get_goal(goal_id)
        if existing is None or existing.company_id != resolved_company_id:
            raise HTTPException(status_code=404, detail="goal_not_found")
        row = await repo.update_goal_status(
            goal_id,
            status=body.status.value,
            current_value=body.current_value,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="goal_not_found")
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.GOAL_UPDATED,
                target_type="goal",
                target_id=row.goal_id,
                actor_type="user",
                actor_id=body.actor_id,
                detail={
                    "status": row.status,
                    "current_value": row.current_value,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/work-items")
    async def list_work_items(
        company_id: str | None = None,
        status: WorkItemStatus | None = None,
        priority: WorkItemPriority | None = None,
        goal_id: str | None = None,
        owner_agent_id: str | None = None,
        owner_user_id: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_work_items(
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            priority=priority.value if priority else None,
            goal_id=goal_id,
            owner_agent_id=owner_agent_id,
            owner_user_id=owner_user_id,
            search=search,
            limit=limit,
        )
        return {"work_items": [_row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/work-items",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_work_item(
        body: WorkItemCreateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        await ensure_company(repo, company_id)
        if body.goal_id:
            goal = await repo.get_goal(body.goal_id)
            if goal is None or goal.company_id != company_id:
                raise HTTPException(status_code=400, detail="goal_not_found")
        for dependency_id in body.dependencies:
            dependency = await repo.get_work_item(dependency_id)
            if dependency is None or dependency.company_id != company_id:
                raise HTTPException(status_code=400, detail="dependency_not_found")

        row = await repo.create_work_item(
            WorkItem(
                company_id=company_id,
                title=body.title,
                description=body.description,
                status=body.status,
                priority=body.priority,
                goal_id=body.goal_id,
                owner_agent_id=body.owner_agent_id,
                owner_user_id=body.owner_user_id,
                source=body.source,
                external_ref=body.external_ref,
                dependencies=body.dependencies,
                approval_required=body.approval_required,
                metadata=body.metadata,
            )
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.WORK_ITEM_CREATED,
                target_type="work_item",
                target_id=row.work_item_id,
                actor_type="user",
                actor_id=body.created_by,
                work_item_id=row.work_item_id,
                detail={
                    "work_item_id": row.work_item_id,
                    "status": row.status,
                    "priority": row.priority,
                    "goal_id": row.goal_id,
                    "owner_agent_id": row.owner_agent_id,
                    "owner_user_id": row.owner_user_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/work-items/{work_item_id}")
    async def get_work_item(
        work_item_id: str,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        row = await ControlPlaneRepository(session).get_work_item(work_item_id)
        if row is None or row.company_id != resolve_company(company_id):
            raise HTTPException(status_code=404, detail="work_item_not_found")
        return _row_to_dict(row)

    @router.patch("/work-items/{work_item_id}/status")
    async def update_work_item_status(
        work_item_id: str,
        body: WorkItemStatusUpdateRequest,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        resolved_company_id = resolve_company(company_id)
        existing = await repo.get_work_item(work_item_id)
        if existing is None or existing.company_id != resolved_company_id:
            raise HTTPException(status_code=404, detail="work_item_not_found")
        row = await repo.update_work_item_status(
            work_item_id,
            status=body.status.value,
            owner_agent_id=body.owner_agent_id,
            owner_user_id=body.owner_user_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="work_item_not_found")
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.WORK_ITEM_UPDATED,
                target_type="work_item",
                target_id=row.work_item_id,
                actor_type="user",
                actor_id=body.actor_id,
                work_item_id=row.work_item_id,
                detail={
                    "status": row.status,
                    "owner_agent_id": row.owner_agent_id,
                    "owner_user_id": row.owner_user_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/decisions")
    async def list_decisions(
        company_id: str | None = None,
        status: DecisionStatus | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_decisions(
            company_id=resolve_company(company_id),
            status=status.value if status else None,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {"decisions": [_row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/decisions",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_decision(
        body: DecisionCreateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        await ensure_company(repo, company_id)
        goal_id, work_item_id = await validate_execution_links(
            repo,
            company_id=company_id,
            run_id=body.run_id,
            work_item_id=body.work_item_id,
            goal_id=body.goal_id,
        )
        row = await repo.create_decision(
            Decision(
                company_id=company_id,
                title=body.title,
                rationale=body.rationale,
                status=body.status,
                run_id=body.run_id,
                work_item_id=work_item_id,
                goal_id=goal_id,
                options=body.options,
                selected_option=body.selected_option,
                decided_by=body.decided_by,
                metadata=body.metadata,
            )
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.DECISION_CREATED,
                target_type="decision",
                target_id=row.decision_id,
                actor_type="user",
                actor_id=body.created_by,
                run_id=row.run_id,
                work_item_id=row.work_item_id,
                detail={
                    "decision_id": row.decision_id,
                    "status": row.status,
                    "goal_id": row.goal_id,
                    "work_item_id": row.work_item_id,
                    "run_id": row.run_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/decisions/{decision_id}")
    async def get_decision(
        decision_id: str,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        row = await ControlPlaneRepository(session).get_decision(decision_id)
        if row is None or row.company_id != resolve_company(company_id):
            raise HTTPException(status_code=404, detail="decision_not_found")
        return _row_to_dict(row)

    @router.patch("/decisions/{decision_id}/status")
    async def update_decision_status(
        decision_id: str,
        body: DecisionStatusUpdateRequest,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        resolved_company_id = resolve_company(company_id)
        existing = await repo.get_decision(decision_id)
        if existing is None or existing.company_id != resolved_company_id:
            raise HTTPException(status_code=404, detail="decision_not_found")
        row = await repo.update_decision_status(
            decision_id,
            status=body.status.value,
            selected_option=body.selected_option,
            decided_by=body.decided_by,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="decision_not_found")
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.DECISION_UPDATED,
                target_type="decision",
                target_id=row.decision_id,
                actor_type="user",
                actor_id=body.actor_id,
                run_id=row.run_id,
                work_item_id=row.work_item_id,
                detail={
                    "status": row.status,
                    "selected_option": row.selected_option,
                    "decided_by": row.decided_by,
                    "goal_id": row.goal_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/artifacts")
    async def list_artifacts(
        company_id: str | None = None,
        artifact_type: ArtifactType | None = None,
        run_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        created_by_agent_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_artifacts(
            company_id=resolve_company(company_id),
            artifact_type=artifact_type.value if artifact_type else None,
            run_id=run_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            created_by_agent_id=created_by_agent_id,
            limit=limit,
        )
        return {"artifacts": [_row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/artifacts",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_artifact(
        body: ArtifactCreateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        await ensure_company(repo, company_id)
        goal_id, work_item_id = await validate_execution_links(
            repo,
            company_id=company_id,
            run_id=body.run_id,
            work_item_id=body.work_item_id,
            goal_id=body.goal_id,
        )
        row = await repo.create_artifact(
            Artifact(
                company_id=company_id,
                artifact_type=body.artifact_type,
                title=body.title,
                uri=body.uri,
                content_hash=body.content_hash,
                run_id=body.run_id,
                work_item_id=work_item_id,
                goal_id=goal_id,
                created_by_agent_id=body.created_by_agent_id,
                metadata=body.metadata,
            )
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.ARTIFACT_CREATED,
                target_type="artifact",
                target_id=row.artifact_id,
                actor_type="user",
                actor_id=body.created_by,
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
        return _row_to_dict(row)

    @router.get("/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: str,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        row = await ControlPlaneRepository(session).get_artifact(artifact_id)
        if row is None or row.company_id != resolve_company(company_id):
            raise HTTPException(status_code=404, detail="artifact_not_found")
        return _row_to_dict(row)

    @router.get("/runs")
    async def list_runs(
        company_id: str | None = None,
        status: str | None = None,
        agent_id: str | None = None,
        trace_id: str | None = None,
        goal_id: str | None = None,
        work_item_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_agent_runs(
            company_id=resolve_company(company_id),
            status=status,
            agent_id=agent_id,
            trace_id=trace_id,
            goal_id=goal_id,
            work_item_id=work_item_id,
            limit=limit,
        )
        return {"runs": [_row_to_dict(row) for row in rows]}

    @router.get("/agents")
    async def list_agents(
        company_id: str | None = None,
        status: str | None = None,
        agent_kind: AgentKind | None = None,
        interaction_mode: AgentInteractionMode | None = None,
        adapter_type: str | None = None,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_agent_roles(
            company_id=resolve_company(company_id),
            status=status,
            agent_kind=agent_kind.value if agent_kind else None,
            interaction_mode=interaction_mode.value if interaction_mode else None,
            adapter_type=adapter_type,
            search=search,
            limit=limit,
        )
        return {"agents": [_row_to_dict(row) for row in rows], "total": len(rows)}

    @router.post(
        "/agents",
        status_code=http_status.HTTP_201_CREATED,
    )
    async def create_agent(
        body: AgentDefinitionCreateRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        await ensure_company(repo, company_id)
        existing = await repo.get_agent_role(
            company_id=company_id,
            agent_id=body.agent_id,
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="agent_already_exists")
        if not DEFAULT_ADAPTER_REGISTRY.is_registered(body.adapter_type):
            raise HTTPException(status_code=400, detail="unsupported_adapter_type")

        row = await repo.create_agent_role(
            AgentRole(
                company_id=company_id,
                agent_id=body.agent_id,
                display_name=body.display_name,
                agent_kind=body.agent_kind,
                interaction_mode=body.interaction_mode,
                role=body.role,
                title=body.title,
                domain=body.domain,
                reports_to_agent_id=body.reports_to_agent_id,
                adapter_type=body.adapter_type,
                adapter_config=body.adapter_config,
                context_sources=body.context_sources,
                capabilities=body.capabilities,
                responsibilities=body.responsibilities,
                permissions=body.permissions,
                budget_policy_id=body.budget_policy_id,
                escalation_policy=body.escalation_policy,
                status=body.status,
                created_by=body.created_by,
                metadata=body.metadata,
            )
        )
        await repo.append_audit_event(
            AuditEvent(
                company_id=company_id,
                action=EventTypes.AGENT_ROLE_CREATED,
                target_type="agent_role",
                target_id=row.agent_id,
                actor_type="user",
                actor_id=body.created_by,
                detail={
                    "agent_id": row.agent_id,
                    "role_id": row.role_id,
                    "agent_kind": row.agent_kind,
                    "interaction_mode": row.interaction_mode,
                    "role": row.role,
                    "adapter_type": row.adapter_type,
                    "reports_to_agent_id": row.reports_to_agent_id,
                },
            )
        )
        return _row_to_dict(row)

    @router.get("/agents/{agent_id}")
    async def get_agent(
        agent_id: str,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        row = await repo.get_agent_role(
            company_id=resolve_company(company_id),
            agent_id=agent_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        return _row_to_dict(row)

    @router.patch("/agents/{agent_id}/status")
    async def update_agent_status(
        agent_id: str,
        body: AgentStatusUpdateRequest,
        company_id: str | None = None,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        resolved_company_id = resolve_company(company_id)
        row = await repo.update_agent_role_status(
            company_id=resolved_company_id,
            agent_id=agent_id,
            status=body.status.strip(),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        await repo.append_audit_event(
            AuditEvent(
                company_id=resolved_company_id,
                action=EventTypes.AGENT_ROLE_STATUS_UPDATED,
                target_type="agent_role",
                target_id=row.agent_id,
                actor_type="user",
                actor_id=body.actor_id,
                detail={"status": row.status},
            )
        )
        return _row_to_dict(row)

    @router.post("/agents/{agent_id}/wake")
    async def wake_agent(
        agent_id: str,
        body: AgentWakeupRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        row = await repo.get_agent_role(
            company_id=resolve_company(body.company_id),
            agent_id=agent_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="agent_not_found")
        try:
            result = await ControlPlaneAgentRunner(repo).wake(
                row,
                input_payload=body.input,
                actor_id=body.actor_id,
                trace_id=body.trace_id,
                goal_id=body.goal_id,
                work_item_id=body.work_item_id,
            )
        except AgentWakeupError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        run = await repo.get_agent_run(result.run_id)
        return {
            "run": _row_to_dict(run) if run is not None else {"run_id": result.run_id},
            "output": result.output,
        }

    @router.post("/scheduler/heartbeats/run-once")
    async def run_heartbeat_scheduler_once(
        body: HeartbeatRunRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        company_id = resolve_company(body.company_id)
        if await repo.get_company(company_id) is None:
            raise HTTPException(status_code=404, detail="company_not_found")

        results = await ControlPlaneHeartbeatScheduler(repo).run_due_once(
            company_id=company_id,
            limit=body.limit,
        )
        return {
            "company_id": company_id,
            "results": [asdict(item) for item in results],
            "total": len(results),
        }

    @router.get("/runs/{run_id}")
    async def get_run(
        run_id: str,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        row = await repo.get_agent_run(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return _row_to_dict(row)

    @router.get("/approvals")
    async def list_approvals(
        company_id: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_approvals(
            company_id=resolve_company(company_id),
            status=status,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )
        return {"approvals": [_row_to_dict(row) for row in rows]}

    @router.post("/approvals/{approval_id}/approve")
    async def approve(
        approval_id: str,
        body: ApprovalActionRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        try:
            decision = await ApprovalGate(repo).approve(
                approval_id,
                resolved_by=body.resolved_by,
            )
        except ApprovalRequiredError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return decision.__dict__

    @router.post("/approvals/{approval_id}/reject")
    async def reject(
        approval_id: str,
        body: ApprovalActionRequest,
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        try:
            decision = await ApprovalGate(repo).reject(
                approval_id,
                resolved_by=body.resolved_by,
            )
        except ApprovalRequiredError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return decision.__dict__

    @router.get("/budgets/usage")
    async def list_budget_usage(
        company_id: str | None = None,
        budget_id: str | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_budget_usage(
            company_id=resolve_company(company_id),
            budget_id=budget_id,
            run_id=run_id,
            trace_id=trace_id,
            limit=limit,
        )
        return {"usage": [_row_to_dict(row) for row in rows]}

    @router.get("/audit-events")
    async def list_audit_events(
        company_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ):
        repo = ControlPlaneRepository(session)
        rows = await repo.list_audit_events(
            company_id=resolve_company(company_id),
            trace_id=trace_id,
            run_id=run_id,
            target_type=target_type,
            target_id=target_id,
            limit=limit,
        )
        return {"audit_events": [_row_to_dict(row) for row in rows]}

    @router.get("/timeline")
    async def get_timeline(
        company_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        session: AsyncSession = Depends(get_session),
    ):
        if not trace_id and not run_id:
            raise HTTPException(status_code=400, detail="trace_id_or_run_id_required")

        repo = ControlPlaneRepository(session)
        resolved_company_id = resolve_company(company_id)
        runs = []
        if run_id:
            run = await repo.get_agent_run(run_id)
            if run is not None and run.company_id == resolved_company_id:
                runs = [run]
        elif trace_id:
            runs = await repo.list_agent_runs(
                company_id=resolved_company_id,
                trace_id=trace_id,
                limit=limit,
            )
        run_ids = [row.run_id for row in runs]
        audits = await repo.list_audit_events(
            company_id=resolved_company_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )
        approvals = await repo.list_approvals(
            company_id=resolved_company_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )
        budget_usage = await repo.list_budget_usage(
            company_id=resolved_company_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )
        decisions = await repo.list_decisions(
            company_id=resolved_company_id,
            run_id=run_id,
            run_ids=run_ids if not run_id else None,
            limit=limit,
        )
        artifacts = await repo.list_artifacts(
            company_id=resolved_company_id,
            run_id=run_id,
            run_ids=run_ids if not run_id else None,
            limit=limit,
        )

        items = [
            {
                "type": "audit_event",
                "at": row.created_at,
                "data": _row_to_dict(row),
            }
            for row in audits
        ]
        items.extend(
            {
                "type": "agent_run",
                "at": row.completed_at or row.started_at,
                "data": _row_to_dict(row),
            }
            for row in runs
        )
        items.extend(
            {
                "type": "approval",
                "at": row.resolved_at or row.created_at,
                "data": _row_to_dict(row),
            }
            for row in approvals
        )
        items.extend(
            {
                "type": "budget_usage",
                "at": row.created_at,
                "data": _row_to_dict(row),
            }
            for row in budget_usage
        )
        items.extend(
            {
                "type": "decision",
                "at": row.updated_at or row.created_at,
                "data": _row_to_dict(row),
            }
            for row in decisions
        )
        items.extend(
            {
                "type": "artifact",
                "at": row.created_at,
                "data": _row_to_dict(row),
            }
            for row in artifacts
        )
        items.sort(key=lambda item: _timeline_sort_key(item["at"]), reverse=True)
        return {
            "timeline": [
                {**item, "at": _serialize(item["at"])}
                for item in items[:limit]
            ]
        }

    return router
